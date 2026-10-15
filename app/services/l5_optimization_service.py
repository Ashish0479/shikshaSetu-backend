"""Layer 5 advisory staffing scenario generation.

This module is deliberately independent from the L1-L4 calculations.  It
accepts their persisted outputs, validates an internal input shape, and
returns reviewable scenarios; it never performs a transfer or posting.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ortools.sat.python import cp_model


class L5ConfigurationError(ValueError):
    """Raised when enabled policy rules are incomplete or invalid."""


class L5InputError(ValueError):
    """Raised when cleaned records cannot be mapped safely to L5 inputs."""


@dataclass(frozen=True)
class ConstraintRule:
    rule_id: str
    name: str
    hard: bool
    enabled: bool
    parameters: Dict[str, Any]
    description: str
    policy_reference: Optional[str]
    version: str
    effective_date: Optional[str] = None


class ConstraintRegistry:
    """Versioned, explicit policy configuration for L5."""

    REQUIRED_PARAMETERS = {
        "max_distance": ("max_distance_km",),
        "source_minimum_staffing": ("minimum_staffing",),
        "source_school_minimum_staffing": ("minimum_staffing",),
        "rural_remote_protection": ("protected_categories",),
    }

    def __init__(self, rules: Optional[Sequence[Dict[str, Any]]] = None, version: str = "unconfigured"):
        self.version = version
        self.rules = [
            ConstraintRule(**rule) for rule in (rules or [])
        ]
        self.validate()

    def validate(self) -> None:
        for rule in self.rules:
            if not rule.rule_id or not rule.version:
                raise L5ConfigurationError("Every constraint must have a rule_id and version.")
            if rule.enabled and rule.hard and not rule.policy_reference:
                raise L5ConfigurationError(
                    f"Enabled hard rule '{rule.rule_id}' requires policy_reference."
                )
            required = self.REQUIRED_PARAMETERS.get(rule.rule_id, ())
            if rule.enabled:
                missing = [key for key in required if key not in rule.parameters]
                if missing:
                    raise L5ConfigurationError(
                        f"Enabled rule '{rule.rule_id}' is missing parameters: {', '.join(missing)}."
                    )
                if rule.rule_id == "max_distance" and float(rule.parameters["max_distance_km"]) < 0:
                    raise L5ConfigurationError("max_distance_km must be non-negative.")

    def enabled(self, rule_id: str) -> Optional[ConstraintRule]:
        return next((rule for rule in self.rules if rule.rule_id == rule_id and rule.enabled), None)

    def as_dicts(self) -> List[Dict[str, Any]]:
        return [rule.__dict__.copy() for rule in self.rules]


@dataclass
class L5Input:
    teachers: List[Dict[str, Any]]
    schools: List[Dict[str, Any]]
    demands: Dict[Tuple[str, str], int]
    limitations: List[str]
    l4_available: bool


class L5InputAdapter:
    """Maps cleaned L1-L2 records and optional L3/L4 results into L5 input."""

    @staticmethod
    def _text(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @classmethod
    def adapt(
        cls,
        clean_data: Dict[str, List[Dict[str, Any]]],
        l3_analysis: Optional[Dict[str, Any]] = None,
        l4_analysis: Optional[Dict[str, Any]] = None,
    ) -> L5Input:
        teachers = [
            dict(row) for row in (clean_data.get("teachers", []) or clean_data.get("teacher", []))
        ]
        schools = clean_data.get("schools", []) or clean_data.get("school", [])
        qualification_rows = (l3_analysis or {}).get("qualification_analysis", {}).get("records", [])
        qualification_by_id = {
            cls._text(row.get("Teacher_ID")): row.get("qualification_match")
            for row in qualification_rows
            if cls._text(row.get("Teacher_ID"))
        }
        for teacher in teachers:
            match = qualification_by_id.get(cls._text(teacher.get("Teacher_ID")))
            if match:
                teacher["_l3_qualification_match"] = match
        if not isinstance(teachers, list) or not isinstance(schools, list):
            raise L5InputError("Teachers and schools must be lists of records.")

        teacher_ids: set[str] = set()
        for teacher in teachers:
            teacher_id = cls._text(teacher.get("Teacher_ID"))
            school_id = cls._text(teacher.get("School_Code"))
            if not teacher_id or not school_id:
                raise L5InputError("Every teacher must have Teacher_ID and School_Code.")
            if teacher_id in teacher_ids:
                raise L5InputError(f"Duplicate Teacher_ID '{teacher_id}'.")
            teacher_ids.add(teacher_id)

        school_ids: set[str] = set()
        for school in schools:
            school_id = cls._text(school.get("School_Code"))
            if not school_id:
                raise L5InputError("Every school must have School_Code.")
            if school_id in school_ids:
                raise L5InputError(f"Duplicate School_Code '{school_id}'.")
            school_ids.add(school_id)

        demands: Dict[Tuple[str, str], int] = {}
        for school in schools:
            school_id = cls._text(school.get("School_Code"))
            subject_demands = school.get("Subject_Demand") or school.get("subject_demand")
            if isinstance(subject_demands, dict):
                for subject, value in subject_demands.items():
                    demands[(school_id, cls._text(subject).lower())] = cls._nonnegative_int(value)
            elif school.get("Required_Teachers") is not None:
                demands[(school_id, "__all__")] = cls._nonnegative_int(school["Required_Teachers"])

        ptr_rows = (l3_analysis or {}).get("ptr_analysis", {}).get("schools", [])
        for row in ptr_rows:
            school_id = cls._text(row.get("school_code") or row.get("School_Code"))
            if school_id and (school_id, "__all__") not in demands:
                shortage = cls._nonnegative_int(math.ceil(float(row.get("shortage", 0) or 0)))
                current = sum(cls._text(t.get("School_Code")) == school_id for t in teachers)
                demands[(school_id, "__all__")] = current + shortage

        limitations = []
        if not l4_analysis:
            limitations.append("L4 future-risk inputs were unavailable; optimization uses current staffing only.")
        if not demands:
            limitations.append("No explicit school demand was available; no shortage-reduction objective can be applied.")
        return L5Input(teachers, schools, demands, limitations, bool(l4_analysis))

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            number = int(math.ceil(float(value)))
        except (TypeError, ValueError):
            raise L5InputError(f"Invalid non-negative demand value: {value!r}.")
        if number < 0:
            raise L5InputError(f"Demand cannot be negative: {value!r}.")
        return number


class L5OptimizationService:
    """Builds and solves CP-SAT staffing scenarios using staged objectives."""

    SCALE = 1000

    @staticmethod
    def _coordinates(record: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        try:
            lat, lon = float(record.get("Latitude")), float(record.get("Longitude"))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return None
            return lat, lon
        except (TypeError, ValueError):
            return None

    @classmethod
    def _distance(cls, source: Dict[str, Any], destination: Dict[str, Any]) -> Optional[float]:
        first, second = cls._coordinates(source), cls._coordinates(destination)
        if not first or not second:
            return None
        lat1, lon1, lat2, lon2 = map(math.radians, (*first, *second))
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 6371.0088 * 2 * math.asin(math.sqrt(a))

    @staticmethod
    def _eligible(teacher: Dict[str, Any], subject: str) -> bool:
        if str(teacher.get("_l3_qualification_match", "")).upper() == "MISMATCH":
            return False
        if subject == "__all__":
            return True
        allowed = teacher.get("Eligible_Subjects") or teacher.get("eligible_subjects")
        if isinstance(allowed, str):
            allowed = [part.strip() for part in allowed.split(",")]
        if isinstance(allowed, list):
            return subject.lower() in {str(item).strip().lower() for item in allowed}
        return str(teacher.get("Subject", "")).strip().lower() == subject.lower()

    @staticmethod
    def _category(record: Dict[str, Any]) -> str:
        return str(record.get("School_Type") or record.get("Category") or "").strip().lower()

    @classmethod
    def _prepare(
        cls, data: L5Input, registry: ConstraintRegistry
    ) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str], int], Dict[Tuple[int, str], Optional[float]], List[str]]:
        schools = {str(row["School_Code"]): row for row in data.schools}
        if any(school_id not in schools for school_id, _ in data.demands):
            raise L5InputError("Demand references a school missing from the cleaned school records.")
        max_distance = registry.enabled("max_distance")
        protected = registry.enabled("rural_remote_protection")
        distances: Dict[Tuple[int, str], Optional[float]] = {}
        pairs: List[Dict[str, Any]] = []
        exclusions: List[str] = []
        for index, teacher in enumerate(data.teachers):
            source = str(teacher["School_Code"])
            for destination in schools:
                distance = cls._distance(schools.get(source, teacher), schools[destination])
                distances[(index, destination)] = distance
                is_current = source == destination
                if not is_current:
                    if max_distance and distance is None:
                        exclusions.append(f"{teacher['Teacher_ID']}->{destination}: missing coordinates")
                        continue
                    if max_distance and distance > float(max_distance.parameters["max_distance_km"]):
                        exclusions.append(f"{teacher['Teacher_ID']}->{destination}: exceeds maximum distance")
                        continue
                    if protected and cls._category(schools.get(source, {})) in {
                        str(item).lower() for item in protected.parameters["protected_categories"]
                    }:
                        exclusions.append(f"{teacher['Teacher_ID']}->{destination}: protected source school")
                        continue
                for school_id, subject in data.demands:
                    if school_id == destination and cls._eligible(teacher, subject):
                        pairs.append({"teacher": index, "school": destination, "subject": subject})
        return pairs, data.demands, distances, exclusions

    @classmethod
    def generate_scenarios(
        cls,
        clean_data: Dict[str, List[Dict[str, Any]]],
        registry: ConstraintRegistry,
        l3_analysis: Optional[Dict[str, Any]] = None,
        l4_analysis: Optional[Dict[str, Any]] = None,
        scenario_count: int = 3,
        time_limit_seconds: float = 10.0,
    ) -> Dict[str, Any]:
        if scenario_count < 1:
            raise L5InputError("scenario_count must be at least 1.")
        data = L5InputAdapter.adapt(clean_data, l3_analysis, l4_analysis)
        pairs, demands, distances, exclusions = cls._prepare(data, registry)
        schools = {str(row["School_Code"]): row for row in data.schools}
        model = cp_model.CpModel()
        assignment: Dict[Tuple[int, str], cp_model.IntVar] = {}
        for pair in pairs:
            assignment[(pair["teacher"], pair["school"])] = model.NewBoolVar(
                f"assign_{pair['teacher']}_{pair['school']}"
            )
        for teacher_index in range(len(data.teachers)):
            model.Add(sum(var for (idx, _), var in assignment.items() if idx == teacher_index) <= 1)

        minimum = registry.enabled("source_school_minimum_staffing")
        if minimum:
            minimum_value = int(minimum.parameters["minimum_staffing"])
            for school_id in schools:
                outgoing = [
                    var for (idx, destination), var in assignment.items()
                    if str(data.teachers[idx]["School_Code"]) == school_id and destination != school_id
                ]
                model.Add(sum(outgoing) <= max(
                    0, sum(str(t["School_Code"]) == school_id for t in data.teachers) - minimum_value
                ))

        shortage_vars: Dict[Tuple[str, str], cp_model.IntVar] = {}
        for key, demand in demands.items():
            school_id, subject = key
            matching = [
                var for (idx, destination), var in assignment.items()
                if destination == school_id and (subject == "__all__" or cls._eligible(data.teachers[idx], subject))
            ]
            shortage = model.NewIntVar(0, demand, f"shortage_{school_id}_{subject}")
            model.Add(shortage == demand - sum(matching))
            shortage_vars[key] = shortage

        moved = [
            var for (idx, destination), var in assignment.items()
            if str(data.teachers[idx]["School_Code"]) != destination
        ]
        distance_cost = sum(
            int(round((distances[(idx, destination)] or 0) * cls.SCALE)) * var
            for (idx, destination), var in assignment.items()
            if str(data.teachers[idx]["School_Code"]) != destination
        )
        baseline_shortage = {}
        for key, demand in demands.items():
            school_id, subject = key
            current = sum(
                cls._eligible(t, subject) for t in data.teachers
                if str(t["School_Code"]) == school_id
            )
            baseline_shortage[key] = max(0, demand - current)
        new_shortage_terms = []
        for key, variable in shortage_vars.items():
            if baseline_shortage[key] == 0:
                new_shortage_terms.append(variable)
        objectives = [
            ("shortage", sum(shortage_vars.values())),
            ("new_shortage", sum(new_shortage_terms) if new_shortage_terms else 0),
            ("movement", sum(moved)),
            ("distance", distance_cost),
        ]
        stages = []
        start = time.monotonic()
        stage_status = "OPTIMAL"
        for name, objective in objectives:
            if isinstance(objective, int):
                stages.append({"name": name, "value": 0, "status": "OPTIMAL"})
                continue
            model.Minimize(objective)
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = max(0.01, time_limit_seconds)
            status = solver.Solve(model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                if status == cp_model.INFEASIBLE:
                    return cls._result("INFEASIBLE", [], data, registry, stages, exclusions, start)
                return cls._result("UNKNOWN", [], data, registry, stages, exclusions, start)
            value = int(solver.ObjectiveValue())
            if status == cp_model.FEASIBLE:
                stage_status = "FEASIBLE"
            model.Add(objective == value)
            stages.append({"name": name, "value": value, "status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"})

        scenarios = []
        for _ in range(scenario_count):
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = max(0.01, time_limit_seconds)
            status = solver.Solve(model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break
            plan = []
            for (teacher_index, school_id), variable in assignment.items():
                if solver.Value(variable):
                    teacher = data.teachers[teacher_index]
                    plan.append({
                        "teacher_id": teacher["Teacher_ID"],
                        "source_school_id": teacher["School_Code"],
                        "destination_school_id": school_id,
                        "subject": teacher.get("Subject"),
                        "distance_km": distances[(teacher_index, school_id)],
                    })
            signature = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
            metrics = cls.evaluate_plan(data, plan, demands, baseline_shortage)
            scenarios.append({
                "scenario_id": f"l5-{signature[:12]}",
                "assignment_plan": plan,
                "metrics": metrics,
                "solver_status": "OPTIMAL" if status == cp_model.OPTIMAL and stage_status == "OPTIMAL" else "FEASIBLE",
            })
            selected = [var for var in assignment.values() if solver.Value(var)]
            if selected:
                model.Add(sum(selected) <= len(selected) - 1)
        return cls._result(
            "OPTIMAL" if scenarios and stage_status == "OPTIMAL" else ("FEASIBLE" if scenarios else "INFEASIBLE"),
            scenarios, data, registry, stages, exclusions, start,
        )

    @staticmethod
    def evaluate_plan(data: L5Input, plan: List[Dict[str, Any]], demands: Dict[Tuple[str, str], int], baseline: Dict[Tuple[str, str], int]) -> Dict[str, Any]:
        staffing: Dict[Tuple[str, str], int] = {}
        for teacher in data.teachers:
            key = (str(teacher["School_Code"]), str(teacher.get("Subject", "")).lower())
            staffing[key] = staffing.get(key, 0) + 1
        for move in plan:
            source = str(move["source_school_id"])
            subject = str(move.get("subject") or "").lower()
            staffing[(source, subject)] = staffing.get((source, subject), 0) - 1
            destination = str(move["destination_school_id"])
            staffing[(destination, subject)] = staffing.get((destination, subject), 0) + 1
        shortages = {}
        for (school_id, subject), demand in demands.items():
            actual = sum(value for (sid, _), value in staffing.items() if sid == school_id and (subject == "__all__" or _ == subject))
            shortages[f"{school_id}:{subject}"] = max(0, demand - actual)
        new = sum(max(0, value - baseline.get(tuple(key.split(":", 1)), 0)) for key, value in shortages.items())
        return {
            "remaining_shortages": shortages,
            "newly_created_shortages": new,
            "movement_count": len([item for item in plan if item["source_school_id"] != item["destination_school_id"]]),
            "total_distance_km": round(sum(item["distance_km"] or 0 for item in plan), 3),
        }

    @staticmethod
    def _result(status: str, scenarios: List[Dict[str, Any]], data: L5Input, registry: ConstraintRegistry, stages: List[Dict[str, Any]], exclusions: List[str], started: float) -> Dict[str, Any]:
        return {
            "status": status,
            "scenarios": scenarios,
            "constraint_registry_version": registry.version,
            "constraints": registry.as_dicts(),
            "optimization_stages": stages,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "limitations": data.limitations,
            "exclusions": exclusions,
            "future_risk_inputs_available": data.l4_available,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "advisory_only": True,
        }
