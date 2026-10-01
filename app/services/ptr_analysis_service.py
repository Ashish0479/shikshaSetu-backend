"""Deterministic school-level PTR and shortage/surplus analysis.

This service consumes cleaned L1-L2 canonical records and calculates the
teacher-to-student ratio without bypassing the validated pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.helpers import is_null_or_empty, safe_str, validate_school_code


class PTRAnalysisService:
    """Calculate teacher availability and shortage/surplus at school level."""

    @staticmethod
    def _normalize_school_key(value: Any) -> Optional[str]:
        if is_null_or_empty(value):
            return None
        standardized, is_valid, _ = validate_school_code(value)
        if standardized:
            return standardized.upper()
        return str(value).strip().upper()

    @staticmethod
    def _coerce_numeric(value: Any) -> float:
        if is_null_or_empty(value):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def analyze_schools(
        cls,
        schools: List[Dict[str, Any]],
        teachers: List[Dict[str, Any]],
        enrollment: List[Dict[str, Any]],
        ptr_threshold: Optional[float] = None,
        status_tolerance: Optional[float] = None,
    ) -> Dict[str, Any]:
        threshold = float(ptr_threshold if ptr_threshold is not None else settings.L3_PTR_THRESHOLD)
        threshold = threshold if threshold > 0 else 35.0
        tolerance = float(status_tolerance if status_tolerance is not None else settings.L3_STATUS_TOLERANCE)
        tolerance = max(tolerance, 0.0)

        teacher_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for teacher in teachers:
            code = cls._normalize_school_key(teacher.get("School_Code"))
            if code:
                teacher_index[code].append(teacher)

        enrollment_index: Dict[str, float] = defaultdict(float)
        subject_index: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in enrollment:
            code = cls._normalize_school_key(row.get("School_Code"))
            if not code:
                continue
            count = cls._coerce_numeric(row.get("Enrollment_Count"))
            if count < 0:
                count = 0.0
            enrollment_index[code] += count

            # student-level records without explicit count are treated as one student
            if is_null_or_empty(row.get("Enrollment_Count")) and not is_null_or_empty(row.get("Student_ID")):
                enrollment_index[code] += 1.0

        results: List[Dict[str, Any]] = []
        subject_wise_ptr: List[Dict[str, Any]] = []

        district_teacher_counts: Dict[str, List[int]] = defaultdict(list)
        for teacher in teachers:
            code = cls._normalize_school_key(teacher.get("School_Code"))
            if code:
                school = next((s for s in schools if cls._normalize_school_key(s.get("School_Code")) == code), None)
                if school:
                    district = safe_str(school.get("District")) or "Unknown"
                    district_teacher_counts[district].append(len(teacher_index.get(code, [])))

        for school in schools:
            school_code = cls._normalize_school_key(school.get("School_Code"))
            if not school_code:
                continue

            teacher_matches = teacher_index.get(school_code, [])
            teacher_count = len(teacher_matches)
            total_students = enrollment_index.get(school_code, 0.0)

            if teacher_count > 0 and total_students > 0:
                ptr = total_students / teacher_count
            elif teacher_count == 0 and total_students > 0:
                ptr = float("inf")
            else:
                ptr = 0.0

            expected_teachers = (total_students / threshold) if total_students > 0 and threshold > 0 else 0.0
            shortage = max(expected_teachers - teacher_count, 0.0)
            surplus = max(teacher_count - expected_teachers, 0.0)

            if shortage > tolerance:
                status = "SHORTAGE"
            elif surplus > tolerance:
                status = "SURPLUS"
            else:
                status = "BALANCED"

            subject_counts: Dict[str, int] = {}
            for teacher in teacher_matches:
                subject = safe_str(teacher.get("Subject"))
                if subject:
                    subject_counts[subject] = subject_counts.get(subject, 0) + 1

            subject_detail = [{"subject": subject, "teacher_count": count} for subject, count in sorted(subject_counts.items())]
            school_result = {
                "school_code": school_code,
                "school_name": safe_str(school.get("School_Name")) or "Unknown",
                "district": safe_str(school.get("District")) or "Unknown",
                "total_students": round(total_students, 2),
                "total_teachers": teacher_count,
                "ptr": round(ptr, 2) if ptr != float("inf") else None,
                "ptr_threshold": threshold,
                "expected_teachers": round(expected_teachers, 2),
                "shortage": round(shortage, 2),
                "surplus": round(surplus, 2),
                "status": status,
                "subject_breakdown": subject_detail,
            }
            results.append(school_result)
            if subject_detail:
                subject_wise_ptr.append({
                    "school_code": school_code,
                    "school_name": school_result["school_name"],
                    "subject_breakdown": subject_detail,
                })

        schools_with_shortage = sum(1 for r in results if r["status"] == "SHORTAGE")
        schools_with_surplus = sum(1 for r in results if r["status"] == "SURPLUS")
        schools_balanced = sum(1 for r in results if r["status"] == "BALANCED")

        return {
            "ptr_threshold": threshold,
            "status_tolerance": tolerance,
            "schools": results,
            "subject_wise_ptr": subject_wise_ptr,
            "summary": {
                "schools_analyzed": len(results),
                "schools_with_shortage": schools_with_shortage,
                "schools_with_surplus": schools_with_surplus,
                "schools_balanced": schools_balanced,
            },
        }
