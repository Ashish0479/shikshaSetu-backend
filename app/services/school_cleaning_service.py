"""School Master Data Cleaning, Validation, Standardization, and Deduplication Service."""

import re
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict, Counter
from app.utils.helpers import is_null_or_empty, safe_str, validate_school_code
from app.services.standardization_service import StandardizationService, HARYANA_DISTRICTS
from app.models.canonical_schemas import SCHOOL_CANONICAL_COLUMNS, SCHOOL_CRITICAL_COLUMNS


class SchoolCleaningService:
    @staticmethod
    def validate_row(row: Dict[str, Any], row_number: int) -> List[Dict[str, Any]]:
        """Validates a single school record against domain rules."""
        errors: List[Dict[str, Any]] = []
        school_code = safe_str(row.get("School_Code"))

        # 1. Critical Column: School_Code
        if is_null_or_empty(row.get("School_Code")):
            errors.append({
                "entity": "schools",
                "row_number": row_number,
                "record_id": None,
                "column": "School_Code",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Mandatory School_Code is missing.",
                "suggested_action": "Provide 11-digit UDISE school code.",
            })
        else:
            _, is_valid_code, reason = validate_school_code(row.get("School_Code"))
            if not is_valid_code:
                errors.append({
                    "entity": "schools",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "School_Code",
                    "original_value": str(row.get("School_Code")),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "WARNING" if "does not begin with" in (reason or "") else "ERROR",
                    "message": reason or "Invalid school code.",
                    "suggested_action": "Verify 11-digit UDISE code with Haryana state prefix 06.",
                })

        # 2. Critical Column: School_Name
        school_name = row.get("School_Name")
        if is_null_or_empty(school_name):
            errors.append({
                "entity": "schools",
                "row_number": row_number,
                "record_id": school_code,
                "column": "School_Name",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "School Name is missing.",
                "suggested_action": "Enter official institutional school name.",
            })

        # 3. Critical Column: District
        district = row.get("District")
        if is_null_or_empty(district):
            errors.append({
                "entity": "schools",
                "row_number": row_number,
                "record_id": school_code,
                "column": "District",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "School District is missing.",
                "suggested_action": "Specify one of 22 administrative districts of Haryana.",
            })
        elif str(district).strip().title() not in HARYANA_DISTRICTS:
            errors.append({
                "entity": "schools",
                "row_number": row_number,
                "record_id": school_code,
                "column": "District",
                "original_value": str(district),
                "issue_type": "INVALID_DOMAIN",
                "severity": "WARNING",
                "message": f"District '{district}' is not recognized in official Haryana districts list.",
                "suggested_action": "Confirm district spelling or administrative boundaries.",
            })

        # 4. Student Capacity (if present)
        cap_val = row.get("Student_Capacity")
        if not is_null_or_empty(cap_val):
            try:
                cap_num = float(cap_val)
                if cap_num < 0:
                    errors.append({
                        "entity": "schools",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Student_Capacity",
                        "original_value": str(cap_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "ERROR",
                        "message": f"Negative student capacity ({cap_num}) is invalid.",
                        "suggested_action": "Enter a non-negative student enrollment capacity.",
                    })
            except (ValueError, TypeError):
                errors.append({
                    "entity": "schools",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "Student_Capacity",
                    "original_value": str(cap_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Student capacity '{cap_val}' is not numeric.",
                    "suggested_action": "Enter an integer capacity count.",
                })

        # 5. Latitude & Longitude Range Check
        lat_val = row.get("Latitude")
        if not is_null_or_empty(lat_val):
            try:
                lat_num = float(lat_val)
                if lat_num < -90 or lat_num > 90:
                    errors.append({
                        "entity": "schools",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Latitude",
                        "original_value": str(lat_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "ERROR",
                        "message": f"Latitude {lat_num} is outside valid geographic range [-90, 90].",
                        "suggested_action": "Provide valid latitude coordinates.",
                    })
                elif lat_num < 26.5 or lat_num > 31.5:
                    errors.append({
                        "entity": "schools",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Latitude",
                        "original_value": str(lat_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "WARNING",
                        "message": f"Latitude {lat_num} is outside expected Haryana coordinates (~27.6° to 31.0° N).",
                        "suggested_action": "Verify school geographic coordinates.",
                    })
            except (ValueError, TypeError):
                errors.append({
                    "entity": "schools",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "Latitude",
                    "original_value": str(lat_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Latitude value '{lat_val}' is not a valid number.",
                    "suggested_action": "Enter numeric decimal coordinates.",
                })

        lon_val = row.get("Longitude")
        if not is_null_or_empty(lon_val):
            try:
                lon_num = float(lon_val)
                if lon_num < -180 or lon_num > 180:
                    errors.append({
                        "entity": "schools",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Longitude",
                        "original_value": str(lon_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "ERROR",
                        "message": f"Longitude {lon_num} is outside valid geographic range [-180, 180].",
                        "suggested_action": "Provide valid longitude coordinates.",
                    })
                elif lon_num < 73.5 or lon_num > 78.5:
                    errors.append({
                        "entity": "schools",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Longitude",
                        "original_value": str(lon_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "WARNING",
                        "message": f"Longitude {lon_num} is outside expected Haryana coordinates (~74.4° to 77.6° E).",
                        "suggested_action": "Verify school geographic coordinates.",
                    })
            except (ValueError, TypeError):
                errors.append({
                    "entity": "schools",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "Longitude",
                    "original_value": str(lon_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Longitude value '{lon_val}' is not a valid number.",
                    "suggested_action": "Enter numeric decimal coordinates.",
                })

        return errors

    @staticmethod
    def detect_duplicates(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Detects exact duplicates and conflicting School_Code duplicates."""
        duplicate_reports: List[Dict[str, Any]] = []
        exact_duplicate_indices: List[int] = []

        # 1. Exact Duplicate Rows
        seen_rows: Dict[Tuple, int] = {}
        exact_groups = defaultdict(list)

        for idx, row in enumerate(records, start=1):
            normalized_tuple = tuple(
                (k, str(v).strip().lower())
                for k, v in sorted(row.items())
                if not is_null_or_empty(v)
            )
            if normalized_tuple in seen_rows:
                first_row = seen_rows[normalized_tuple]
                exact_groups[normalized_tuple].append(idx)
                exact_duplicate_indices.append(idx - 1)
            else:
                seen_rows[normalized_tuple] = idx

        for norm_tuple, dup_row_nums in exact_groups.items():
            first_row = seen_rows[norm_tuple]
            all_rows = [first_row] + dup_row_nums
            duplicate_reports.append({
                "entity": "schools",
                "duplicate_type": "EXACT_DUPLICATE",
                "field_matched": "ALL_COLUMNS",
                "matched_value": f"Row #{first_row} and #{','.join(map(str, dup_row_nums))}",
                "row_numbers": all_rows,
                "sample_records": [records[r - 1] for r in all_rows[:3]],
                "recommendation": "Retain initial occurrence; drop exact duplicate rows.",
            })

        # 2. Conflicting School_Code Duplicates
        code_to_rows = defaultdict(list)
        for idx, row in enumerate(records, start=1):
            code = row.get("School_Code")
            if not is_null_or_empty(code):
                std_code, _, _ = validate_school_code(code)
                key = std_code or str(code).strip()
                code_to_rows[key].append((idx, row))

        for code, occurrences in code_to_rows.items():
            if len(occurrences) > 1:
                row_nums = [item[0] for item in occurrences]
                first_rec = occurrences[0][1]
                has_conflict = False
                for other_idx, other_rec in occurrences[1:]:
                    if any(
                        str(first_rec.get(col, "")).strip().lower() != str(other_rec.get(col, "")).strip().lower()
                        for col in ["School_Name", "District", "Block", "School_Type"]
                    ):
                        has_conflict = True
                        break

                if has_conflict:
                    duplicate_reports.append({
                        "entity": "schools",
                        "duplicate_type": "CONFLICTING_DUPLICATE",
                        "field_matched": "School_Code",
                        "matched_value": code,
                        "row_numbers": row_nums,
                        "sample_records": [item[1] for item in occurrences],
                        "recommendation": "Conflicting school records with identical School_Code. Preserving both records; manual review required.",
                    })

        return duplicate_reports, exact_duplicate_indices

    @staticmethod
    def clean_records(
        records: List[Dict[str, Any]],
        exact_dup_indices: List[int],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Cleans, standardizes, and deduplicates school records."""
        clean_records: List[Dict[str, Any]] = []
        standardization_logs: List[Dict[str, Any]] = []

        for idx, row in enumerate(records, start=1):
            if (idx - 1) in exact_dup_indices:
                continue

            cleaned = dict(row)
            school_code = safe_str(row.get("School_Code"))

            # Trim whitespace across all string fields
            for k, v in cleaned.items():
                if isinstance(v, str):
                    cleaned[k] = StandardizationService.clean_text_whitespace(v)

            # 1. School_Code normalization
            code_val = cleaned.get("School_Code")
            if not is_null_or_empty(code_val):
                std_code, is_valid, _ = validate_school_code(code_val)
                if std_code and std_code != str(code_val).strip():
                    cleaned["School_Code"] = std_code
                    standardization_logs.append({
                        "entity": "schools",
                        "record_id": std_code,
                        "row_number": idx,
                        "column": "School_Code",
                        "original_value": str(code_val),
                        "standard_value": std_code,
                        "rule": "Preserve Leading Zero / UDISE Normalization",
                    })

            # 2. School_Name title casing & whitespace
            name_val = cleaned.get("School_Name")
            if not is_null_or_empty(name_val) and isinstance(name_val, str):
                titled = name_val.title()
                if titled != name_val:
                    cleaned["School_Name"] = titled
                    standardization_logs.append({
                        "entity": "schools",
                        "record_id": school_code,
                        "row_number": idx,
                        "column": "School_Name",
                        "original_value": name_val,
                        "standard_value": titled,
                        "rule": "Title Casing",
                    })

            # 3. District Standardization
            dist_val = cleaned.get("District")
            if not is_null_or_empty(dist_val):
                std_dist, rule = StandardizationService.standardize_district(dist_val)
                if std_dist != dist_val:
                    cleaned["District"] = std_dist
                    standardization_logs.append({
                        "entity": "schools",
                        "record_id": school_code,
                        "row_number": idx,
                        "column": "District",
                        "original_value": str(dist_val),
                        "standard_value": std_dist,
                        "rule": rule or "District Canonical Mapping",
                    })

            # 4. Block & Village title casing
            for field in ["Block", "Village"]:
                f_val = cleaned.get(field)
                if not is_null_or_empty(f_val) and isinstance(f_val, str):
                    titled = f_val.title()
                    if titled != f_val:
                        cleaned[field] = titled
                        standardization_logs.append({
                            "entity": "schools",
                            "record_id": school_code,
                            "row_number": idx,
                            "column": field,
                            "original_value": f_val,
                            "standard_value": titled,
                            "rule": "Title Casing",
                        })

            # 5. School_Type & Management title casing
            for field in ["School_Type", "Management"]:
                f_val = cleaned.get(field)
                if not is_null_or_empty(f_val) and isinstance(f_val, str):
                    titled = f_val.title()
                    if titled != f_val:
                        cleaned[field] = titled
                        standardization_logs.append({
                            "entity": "schools",
                            "record_id": school_code,
                            "row_number": idx,
                            "column": field,
                            "original_value": f_val,
                            "standard_value": titled,
                            "rule": "Title Casing",
                        })

            # 6. Student_Capacity numeric normalization
            cap_val = cleaned.get("Student_Capacity")
            if not is_null_or_empty(cap_val):
                try:
                    cleaned["Student_Capacity"] = int(float(cap_val))
                except (ValueError, TypeError):
                    pass

            # 7. Coordinates numeric normalization
            for coord in ["Latitude", "Longitude"]:
                c_val = cleaned.get(coord)
                if not is_null_or_empty(c_val):
                    try:
                        cleaned[coord] = round(float(c_val), 6)
                    except (ValueError, TypeError):
                        pass

            clean_records.append(cleaned)

        return clean_records, standardization_logs
