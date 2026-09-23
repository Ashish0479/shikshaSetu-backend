"""School Location and GIS Data Cleaning, Validation, Standardization, and Deduplication Service."""

from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
from app.utils.helpers import is_null_or_empty, safe_str, validate_school_code
from app.services.standardization_service import StandardizationService, HARYANA_DISTRICTS
from app.models.canonical_schemas import LOCATION_CANONICAL_COLUMNS, LOCATION_CRITICAL_COLUMNS


class LocationCleaningService:
    @staticmethod
    def validate_row(row: Dict[str, Any], row_number: int) -> List[Dict[str, Any]]:
        """Validates a single location record against geographic bounds."""
        errors: List[Dict[str, Any]] = []
        school_code = safe_str(row.get("School_Code"))

        # 1. Critical Column: School_Code
        if is_null_or_empty(row.get("School_Code")):
            errors.append({
                "entity": "locations",
                "row_number": row_number,
                "record_id": None,
                "column": "School_Code",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Mandatory School_Code is missing in location record.",
                "suggested_action": "Provide 11-digit UDISE school code.",
            })
        else:
            _, is_valid_code, reason = validate_school_code(row.get("School_Code"))
            if not is_valid_code:
                errors.append({
                    "entity": "locations",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "School_Code",
                    "original_value": str(row.get("School_Code")),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "WARNING" if "does not begin with" in (reason or "") else "ERROR",
                    "message": reason or "Invalid school code.",
                    "suggested_action": "Verify 11-digit UDISE code with Haryana state prefix 06.",
                })

        # 2. Critical Column: District
        district = row.get("District")
        if is_null_or_empty(district):
            errors.append({
                "entity": "locations",
                "row_number": row_number,
                "record_id": school_code,
                "column": "District",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "District is missing in location record.",
                "suggested_action": "Specify one of 22 administrative districts of Haryana.",
            })
        elif str(district).strip().title() not in HARYANA_DISTRICTS:
            errors.append({
                "entity": "locations",
                "row_number": row_number,
                "record_id": school_code,
                "column": "District",
                "original_value": str(district),
                "issue_type": "INVALID_DOMAIN",
                "severity": "WARNING",
                "message": f"District '{district}' is not recognized in official Haryana districts list.",
                "suggested_action": "Confirm district spelling.",
            })

        # 3. Critical Column: Latitude
        lat_val = row.get("Latitude")
        if is_null_or_empty(lat_val):
            errors.append({
                "entity": "locations",
                "row_number": row_number,
                "record_id": school_code,
                "column": "Latitude",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Latitude coordinate is missing.",
                "suggested_action": "Provide geographic GPS latitude.",
            })
        else:
            try:
                lat_num = float(lat_val)
                if lat_num < -90 or lat_num > 90:
                    errors.append({
                        "entity": "locations",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Latitude",
                        "original_value": str(lat_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "ERROR",
                        "message": f"Latitude {lat_num} is outside valid world bounds [-90, 90].",
                        "suggested_action": "Provide valid latitude.",
                    })
                elif lat_num < 26.5 or lat_num > 31.5:
                    errors.append({
                        "entity": "locations",
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
                    "entity": "locations",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "Latitude",
                    "original_value": str(lat_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Latitude value '{lat_val}' is not numeric.",
                    "suggested_action": "Enter decimal coordinate.",
                })

        # 4. Critical Column: Longitude
        lon_val = row.get("Longitude")
        if is_null_or_empty(lon_val):
            errors.append({
                "entity": "locations",
                "row_number": row_number,
                "record_id": school_code,
                "column": "Longitude",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Longitude coordinate is missing.",
                "suggested_action": "Provide geographic GPS longitude.",
            })
        else:
            try:
                lon_num = float(lon_val)
                if lon_num < -180 or lon_num > 180:
                    errors.append({
                        "entity": "locations",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Longitude",
                        "original_value": str(lon_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "ERROR",
                        "message": f"Longitude {lon_num} is outside valid world bounds [-180, 180].",
                        "suggested_action": "Provide valid longitude.",
                    })
                elif lon_num < 73.5 or lon_num > 78.5:
                    errors.append({
                        "entity": "locations",
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
                    "entity": "locations",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "Longitude",
                    "original_value": str(lon_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Longitude value '{lon_val}' is not numeric.",
                    "suggested_action": "Enter decimal coordinate.",
                })

        return errors

    @staticmethod
    def detect_duplicates(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Detects exact and conflicting School_Code duplicates in locations."""
        duplicate_reports: List[Dict[str, Any]] = []
        exact_duplicate_indices: List[int] = []

        seen_rows: Dict[Tuple, int] = {}
        exact_groups = defaultdict(list)

        for idx, row in enumerate(records, start=1):
            norm_tuple = tuple(
                (k, str(v).strip().lower())
                for k, v in sorted(row.items())
                if not is_null_or_empty(v)
            )
            if norm_tuple in seen_rows:
                first_row = seen_rows[norm_tuple]
                exact_groups[norm_tuple].append(idx)
                exact_duplicate_indices.append(idx - 1)
            else:
                seen_rows[norm_tuple] = idx

        for norm_tuple, dup_row_nums in exact_groups.items():
            first_row = seen_rows[norm_tuple]
            all_rows = [first_row] + dup_row_nums
            duplicate_reports.append({
                "entity": "locations",
                "duplicate_type": "EXACT_DUPLICATE",
                "field_matched": "ALL_COLUMNS",
                "matched_value": f"Row #{first_row} and #{','.join(map(str, dup_row_nums))}",
                "row_numbers": all_rows,
                "sample_records": [records[r - 1] for r in all_rows[:3]],
                "recommendation": "Retain initial occurrence; drop exact duplicate rows.",
            })

        # Conflicting School_Code: same code, differing coordinates
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
                    lat1 = safe_str(first_rec.get("Latitude"))
                    lat2 = safe_str(other_rec.get("Latitude"))
                    lon1 = safe_str(first_rec.get("Longitude"))
                    lon2 = safe_str(other_rec.get("Longitude"))
                    if lat1 != lat2 or lon1 != lon2:
                        has_conflict = True
                        break

                if has_conflict:
                    duplicate_reports.append({
                        "entity": "locations",
                        "duplicate_type": "CONFLICTING_DUPLICATE",
                        "field_matched": "School_Code",
                        "matched_value": code,
                        "row_numbers": row_nums,
                        "sample_records": [item[1] for item in occurrences],
                        "recommendation": "Multiple diverging geographic coordinates found for identical School_Code.",
                    })

        return duplicate_reports, exact_duplicate_indices

    @staticmethod
    def clean_records(
        records: List[Dict[str, Any]],
        exact_dup_indices: List[int],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Cleans, standardizes, and deduplicates location records."""
        clean_records: List[Dict[str, Any]] = []
        standardization_logs: List[Dict[str, Any]] = []

        for idx, row in enumerate(records, start=1):
            if (idx - 1) in exact_dup_indices:
                continue

            cleaned = dict(row)
            school_code = safe_str(row.get("School_Code"))

            for k, v in cleaned.items():
                if isinstance(v, str):
                    cleaned[k] = StandardizationService.clean_text_whitespace(v)

            # 1. School_Code
            code_val = cleaned.get("School_Code")
            if not is_null_or_empty(code_val):
                std_code, is_valid, _ = validate_school_code(code_val)
                if std_code and std_code != str(code_val).strip():
                    cleaned["School_Code"] = std_code
                    standardization_logs.append({
                        "entity": "locations",
                        "record_id": std_code,
                        "row_number": idx,
                        "column": "School_Code",
                        "original_value": str(code_val),
                        "standard_value": std_code,
                        "rule": "Preserve Leading Zero / UDISE Normalization",
                    })

            # 2. District
            dist_val = cleaned.get("District")
            if not is_null_or_empty(dist_val):
                std_dist, rule = StandardizationService.standardize_district(dist_val)
                if std_dist != dist_val:
                    cleaned["District"] = std_dist
                    standardization_logs.append({
                        "entity": "locations",
                        "record_id": school_code,
                        "row_number": idx,
                        "column": "District",
                        "original_value": str(dist_val),
                        "standard_value": std_dist,
                        "rule": rule or "District Canonical Mapping",
                    })

            # 3. Block and Village
            for field in ["Block", "Village"]:
                f_val = cleaned.get(field)
                if not is_null_or_empty(f_val) and isinstance(f_val, str):
                    titled = f_val.title()
                    if titled != f_val:
                        cleaned[field] = titled
                        standardization_logs.append({
                            "entity": "locations",
                            "record_id": school_code,
                            "row_number": idx,
                            "column": field,
                            "original_value": f_val,
                            "standard_value": titled,
                            "rule": "Title Casing",
                        })

            # 4. Numeric coordinates rounding (6 decimal places is ~0.1m precision)
            for coord in ["Latitude", "Longitude"]:
                c_val = cleaned.get(coord)
                if not is_null_or_empty(c_val):
                    try:
                        cleaned[coord] = round(float(c_val), 6)
                    except (ValueError, TypeError):
                        pass

            clean_records.append(cleaned)

        return clean_records, standardization_logs
