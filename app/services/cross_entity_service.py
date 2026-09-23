"""Cross-Entity Consistency and Referential Integrity Validation Service.

Validates relationships between:
- Teachers <-> Schools
- Enrollment <-> Schools
- Locations <-> Schools
- Teacher District vs School District
- School District vs Location District
- Coordinates consistency
"""

from typing import Dict, Any, List, Optional, Set
from app.utils.helpers import is_null_or_empty, safe_str, validate_school_code


class CrossEntityValidator:
    @classmethod
    def validate_cross_entities(
        cls,
        teachers: Optional[List[Dict[str, Any]]] = None,
        schools: Optional[List[Dict[str, Any]]] = None,
        enrollment: Optional[List[Dict[str, Any]]] = None,
        locations: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Validates referential integrity and consistency across multiple cleaned entity datasets.
        Returns a list of cross-entity validation issues.
        """
        issues: List[Dict[str, Any]] = []

        teachers = teachers or []
        schools = schools or []
        enrollment = enrollment or []
        locations = locations or []

        # Index schools by standardized School_Code
        school_map: Dict[str, Dict[str, Any]] = {}
        for s in schools:
            code = s.get("School_Code")
            if not is_null_or_empty(code):
                std_code, _, _ = validate_school_code(code)
                key = (std_code or str(code)).strip().upper()
                school_map[key] = s

        has_schools = len(school_map) > 0

        # Index locations by standardized School_Code
        location_map: Dict[str, Dict[str, Any]] = {}
        for loc in locations:
            code = loc.get("School_Code")
            if not is_null_or_empty(code):
                std_code, _, _ = validate_school_code(code)
                key = (std_code or str(code)).strip().upper()
                location_map[key] = loc

        # ----------------------------------------------------
        # 1. Teacher -> School Referential Integrity & District Check
        # ----------------------------------------------------
        if has_schools and teachers:
            for idx, tch in enumerate(teachers, start=1):
                t_code = tch.get("School_Code")
                t_id = tch.get("Teacher_ID")
                t_dist = tch.get("District")

                if is_null_or_empty(t_code):
                    continue

                std_t_code, _, _ = validate_school_code(t_code)
                key = (std_t_code or str(t_code)).strip().upper()

                if key not in school_map:
                    issues.append({
                        "entity": "teachers",
                        "row_number": idx,
                        "record_id": t_id,
                        "column": "School_Code",
                        "original_value": str(t_code),
                        "issue_type": "UNMATCHED_TEACHER_SCHOOL",
                        "severity": "WARNING",
                        "message": f"Teacher's School_Code '{t_code}' does not exist in the School Master directory.",
                        "suggested_action": "Verify school code or add the school to the School Master.",
                    })
                else:
                    # Compare Teacher District vs School District
                    school_rec = school_map[key]
                    s_dist = school_rec.get("District")
                    if (
                        not is_null_or_empty(t_dist)
                        and not is_null_or_empty(s_dist)
                        and str(t_dist).strip().lower() != str(s_dist).strip().lower()
                    ):
                        issues.append({
                            "entity": "teachers",
                            "row_number": idx,
                            "record_id": t_id,
                            "column": "District",
                            "original_value": f"Teacher: {t_dist} | School: {s_dist}",
                            "issue_type": "TEACHER_SCHOOL_DISTRICT_MISMATCH",
                            "severity": "WARNING",
                            "message": (
                                f"District mismatch: Teacher is recorded under '{t_dist}', but "
                                f"assigned school '{key}' is located in '{s_dist}'."
                            ),
                            "suggested_action": "Review teacher cadre deployment records. Do not alter teacher district without official verification.",
                        })

        # ----------------------------------------------------
        # 2. Enrollment -> School Referential Integrity
        # ----------------------------------------------------
        if has_schools and enrollment:
            for idx, enr in enumerate(enrollment, start=1):
                e_code = enr.get("School_Code")
                if is_null_or_empty(e_code):
                    continue

                std_e_code, _, _ = validate_school_code(e_code)
                key = (std_e_code or str(e_code)).strip().upper()

                if key not in school_map:
                    issues.append({
                        "entity": "enrollment",
                        "row_number": idx,
                        "record_id": safe_str(enr.get("Student_ID")) or key,
                        "column": "School_Code",
                        "original_value": str(e_code),
                        "issue_type": "UNMATCHED_ENROLLMENT_SCHOOL",
                        "severity": "WARNING",
                        "message": f"Enrollment record references School_Code '{e_code}' which is absent from the School Master.",
                        "suggested_action": "Confirm UDISE school code.",
                    })

        # ----------------------------------------------------
        # 3. Location -> School Referential Integrity & District Check
        # ----------------------------------------------------
        if has_schools and locations:
            for idx, loc in enumerate(locations, start=1):
                l_code = loc.get("School_Code")
                if is_null_or_empty(l_code):
                    continue

                std_l_code, _, _ = validate_school_code(l_code)
                key = (std_l_code or str(l_code)).strip().upper()

                if key not in school_map:
                    issues.append({
                        "entity": "locations",
                        "row_number": idx,
                        "record_id": key,
                        "column": "School_Code",
                        "original_value": str(l_code),
                        "issue_type": "UNMATCHED_LOCATION_SCHOOL",
                        "severity": "WARNING",
                        "message": f"Location coordinates provided for School_Code '{l_code}' which does not exist in School Master.",
                        "suggested_action": "Verify school code in GIS dataset.",
                    })
                else:
                    # Compare School District vs Location District
                    school_rec = school_map[key]
                    s_dist = school_rec.get("District")
                    l_dist = loc.get("District")
                    if (
                        not is_null_or_empty(l_dist)
                        and not is_null_or_empty(s_dist)
                        and str(l_dist).strip().lower() != str(s_dist).strip().lower()
                    ):
                        issues.append({
                            "entity": "locations",
                            "row_number": idx,
                            "record_id": key,
                            "column": "District",
                            "original_value": f"Location: {l_dist} | School: {s_dist}",
                            "issue_type": "SCHOOL_LOCATION_DISTRICT_MISMATCH",
                            "severity": "WARNING",
                            "message": f"GIS Location district '{l_dist}' does not match School Master district '{s_dist}'.",
                            "suggested_action": "Check boundary demarcations and GPS reading.",
                        })

                    # Check coordinates consistency if both provide lat/long
                    s_lat = school_rec.get("Latitude")
                    s_lon = school_rec.get("Longitude")
                    l_lat = loc.get("Latitude")
                    l_lon = loc.get("Longitude")
                    if (
                        not is_null_or_empty(s_lat)
                        and not is_null_or_empty(l_lat)
                        and not is_null_or_empty(s_lon)
                        and not is_null_or_empty(l_lon)
                    ):
                        try:
                            lat_diff = abs(float(s_lat) - float(l_lat))
                            lon_diff = abs(float(s_lon) - float(l_lon))
                            # ~0.05 degrees is ~5.5 km
                            if lat_diff > 0.05 or lon_diff > 0.05:
                                issues.append({
                                    "entity": "locations",
                                    "row_number": idx,
                                    "record_id": key,
                                    "column": "Latitude/Longitude",
                                    "original_value": f"School: ({s_lat}, {s_lon}) | GIS: ({l_lat}, {l_lon})",
                                    "issue_type": "COORDINATE_DISCREPANCY",
                                    "severity": "WARNING",
                                    "message": f"Significant coordinate difference (>5km) between School Master and GIS Location record.",
                                    "suggested_action": "Re-survey GPS coordinate location.",
                                })
                        except (ValueError, TypeError):
                            pass

        return issues
