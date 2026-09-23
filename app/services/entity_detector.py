"""Deterministic Entity Detection and Schema Mapping Service for Multi-Entity Education Data.

Supports:
- Teachers
- Schools
- Students / Enrollment
- Locations
"""

import os
import re
from typing import Dict, List, Tuple, Any, Optional, Set
import pandas as pd

from app.models.canonical_schemas import (
    EntityType,
    ENTITY_CANONICAL_SCHEMAS,
    ENTITY_CRITICAL_COLUMNS,
    ENTITY_ALIAS_MAPS,
)


class EntityDetectionResult:
    def __init__(
        self,
        entity_type: EntityType,
        confidence: float,
        reason: str,
        column_matches: Dict[str, str],
        unmapped_columns: List[str],
        detected_from: str,
    ):
        self.entity_type = entity_type
        self.confidence = round(confidence, 2)
        self.reason = reason
        self.column_matches = column_matches
        self.unmapped_columns = unmapped_columns
        self.detected_from = detected_from

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "column_matches": self.column_matches,
            "unmapped_columns": self.unmapped_columns,
            "detected_from": self.detected_from,
        }


class EntityDetector:
    """Deterministic, rule-based detector for education entities."""

    # Filename / sheet name keywords
    KEYWORDS = {
        EntityType.TEACHER: ["teacher", "tch", "faculty", "staff", "adhyapak"],
        EntityType.SCHOOL: ["school", "sch", "school_master", "vidyalaya", "institution"],
        EntityType.ENROLLMENT: ["enrollment", "enrolment", "student", "enr", "admission", "dakhila"],
        EntityType.LOCATION: ["location", "loc", "geo", "gis", "coordinates", "lat_long", "lat_lon"],
    }

    # Distinctive column signatures that strongly indicate a specific entity
    DISTINCTIVE_COLUMNS = {
        EntityType.TEACHER: {"teacher_id", "teacher_name", "designation", "qualification", "experience_years", "teaching_subject"},
        EntityType.SCHOOL: {"school_type", "classes_offered", "student_capacity", "management", "school_category"},
        EntityType.ENROLLMENT: {"enrollment_count", "academic_year", "class", "section", "student_id", "srn"},
        EntityType.LOCATION: {"latitude", "longitude", "lat", "lon", "lng"},
    }

    @classmethod
    def detect_entity(
        cls,
        columns: List[str],
        filename: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> EntityDetectionResult:
        """Determines entity type using deterministic heuristics without LLMs."""
        norm_cols = [cls._normalize_col_str(c) for c in columns]
        norm_cols_set = set(norm_cols)

        # Check filename and sheet name hints
        fn_hint = (filename or "").lower()
        sheet_hint = (sheet_name or "").lower()

        scores: Dict[EntityType, float] = {
            EntityType.TEACHER: 0.0,
            EntityType.SCHOOL: 0.0,
            EntityType.ENROLLMENT: 0.0,
            EntityType.LOCATION: 0.0,
        }

        reasons: Dict[EntityType, List[str]] = {
            EntityType.TEACHER: [],
            EntityType.SCHOOL: [],
            EntityType.ENROLLMENT: [],
            EntityType.LOCATION: [],
        }

        # 1. Distinctive column presence (Strongest signal)
        for entity, dist_cols in cls.DISTINCTIVE_COLUMNS.items():
            matches = norm_cols_set.intersection(dist_cols)
            if matches:
                weight = len(matches) * 2.0
                scores[entity] += weight
                reasons[entity].append(f"Distinctive columns matched: {', '.join(matches)}")

        # 2. Overall column overlap with alias maps
        for entity, alias_map in ENTITY_ALIAS_MAPS.items():
            matched_aliases = [c for c in norm_cols if c in alias_map]
            canon_cols = ENTITY_CANONICAL_SCHEMAS[entity]
            crit_cols = ENTITY_CRITICAL_COLUMNS[entity]
            
            # Critical columns matched
            crit_matches = 0
            for crit in crit_cols:
                crit_norm = cls._normalize_col_str(crit)
                if any(alias_map.get(c) == crit for c in norm_cols):
                    crit_matches += 1

            # Ratio of matched columns to total canonical columns
            overlap_ratio = len(matched_aliases) / max(1, len(canon_cols))
            scores[entity] += overlap_ratio * 3.0

            # Boost if critical columns matched
            if crit_matches == len(crit_cols):
                scores[entity] += 2.0
                reasons[entity].append("All critical columns matched")
            elif crit_matches > 0:
                scores[entity] += (crit_matches / len(crit_cols)) * 1.0

        # Special discriminator: School vs Location
        # Both may have Latitude/Longitude. If School_Type/Management/School_Name is present, it is SCHOOL, not LOCATION.
        if scores[EntityType.SCHOOL] > 1.5 and scores[EntityType.LOCATION] > 1.0:
            school_specific = {"school_type", "management", "classes_offered", "student_capacity"}
            if norm_cols_set.intersection(school_specific):
                scores[EntityType.LOCATION] = max(0.0, scores[EntityType.LOCATION] - 2.5)

        # 3. Filename & Sheet name bonus
        for entity, kw_list in cls.KEYWORDS.items():
            for kw in kw_list:
                if kw in fn_hint:
                    scores[entity] += 2.0
                    reasons[entity].append(f"Filename contains '{kw}'")
                    break
                if kw in sheet_hint:
                    scores[entity] += 2.0
                    reasons[entity].append(f"Sheet name contains '{kw}'")
                    break

        # Find entity with maximum score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_entity, top_score = sorted_scores[0]
        second_entity, second_score = sorted_scores[1]

        # Determine confidence
        # Baseline threshold to be considered confident
        if top_score < 2.0 or (top_score - second_score < 0.5 and top_score < 4.0):
            return EntityDetectionResult(
                entity_type=EntityType.UNKNOWN,
                confidence=0.0,
                reason="Unable to confidently determine entity type",
                column_matches={},
                unmapped_columns=columns,
                detected_from="ambiguous_schema",
            )

        # Calculate confidence metric bounded [0.5, 1.0]
        confidence = min(1.0, 0.6 + (top_score / 15.0))
        reason_text = "; ".join(reasons[top_entity]) or f"Schema similarity match for {top_entity.value}"

        # Get column mappings for top entity
        mapper = SchemaMapper(top_entity)
        mapping_details = mapper.map_columns(columns)

        return EntityDetectionResult(
            entity_type=top_entity,
            confidence=confidence,
            reason=reason_text,
            column_matches=mapping_details["canonical_renames"],
            unmapped_columns=mapping_details["unmapped_columns"],
            detected_from="schema_and_name_analysis",
        )

    @staticmethod
    def _normalize_col_str(name: str) -> str:
        s = str(name).strip().lower()
        s = re.sub(r"[\s\.-]+", "_", s)
        return s


class SchemaMapper:
    """Maps raw columns to canonical entity schema deterministically."""

    def __init__(self, entity_type: EntityType):
        self.entity_type = entity_type
        self.canonical_columns = ENTITY_CANONICAL_SCHEMAS.get(entity_type, [])
        self.critical_columns = ENTITY_CRITICAL_COLUMNS.get(entity_type, [])
        self.alias_map = ENTITY_ALIAS_MAPS.get(entity_type, {})

    def map_columns(self, raw_columns: List[str]) -> Dict[str, Any]:
        """Maps a list of raw column headers to canonical columns.
        Returns:
            {
                "mappings": [ {raw_column, canonical_column, mapping_reason, confidence, is_mapped} ],
                "canonical_renames": { raw_col: canonical_col },
                "unmapped_columns": [ raw_col, ... ]
            }
        """
        mappings = []
        canonical_renames = {}
        unmapped = []
        used_canonical: Set[str] = set()

        for raw_col in raw_columns:
            cleaned = self._clean_col_str(raw_col)
            mapped_canon = None
            reason = "unmapped"
            conf = 0.0

            # 1. Exact case-sensitive match
            if raw_col in self.canonical_columns and raw_col not in used_canonical:
                mapped_canon = raw_col
                reason = "exact_match"
                conf = 1.0

            # 2. Case-insensitive exact match
            if not mapped_canon:
                for c in self.canonical_columns:
                    if c.lower() == raw_col.strip().lower() and c not in used_canonical:
                        mapped_canon = c
                        reason = "case_insensitive_match"
                        conf = 1.0
                        break

            # 3. Known alias lookup
            if not mapped_canon:
                alias_target = self.alias_map.get(cleaned)
                if alias_target and alias_target in self.canonical_columns and alias_target not in used_canonical:
                    mapped_canon = alias_target
                    reason = "known_alias"
                    conf = 1.0

            if mapped_canon:
                canonical_renames[raw_col] = mapped_canon
                used_canonical.add(mapped_canon)
                mappings.append({
                    "raw_column": raw_col,
                    "canonical_column": mapped_canon,
                    "mapping_reason": reason,
                    "confidence": conf,
                    "is_mapped": True,
                })
            else:
                unmapped.append(raw_col)
                mappings.append({
                    "raw_column": raw_col,
                    "canonical_column": None,
                    "mapping_reason": "unmapped",
                    "confidence": 0.0,
                    "is_mapped": False,
                })

        return {
            "mappings": mappings,
            "canonical_renames": canonical_renames,
            "unmapped_columns": unmapped,
        }

    def apply_mapping_to_dataframe(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str], List[str]]:
        """Renames DataFrame columns according to canonical mapping. Preserves unmapped columns."""
        res = self.map_columns(list(df.columns))
        renames = res["canonical_renames"]
        mapped_df = df.rename(columns=renames)
        return mapped_df, renames, res["unmapped_columns"]

    @staticmethod
    def _clean_col_str(name: str) -> str:
        s = str(name).strip().lower()
        s = re.sub(r"[\s\.-]+", "_", s)
        return s
