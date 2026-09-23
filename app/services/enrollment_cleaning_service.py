"""Student / Enrollment Data Cleaning, Validation, Standardization, and Deduplication Service.

Supports:
- Student-level records
- Aggregated grade/section enrollment records
"""

import re
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
from app.utils.helpers import is_null_or_empty, safe_str, validate_school_code
from app.services.standardization_service import StandardizationService
from app.models.canonical_schemas import ENROLLMENT_CANONICAL_COLUMNS, ENROLLMENT_CRITICAL_COLUMNS


class EnrollmentCleaningService:
    @staticmethod
    def standardize_academic_year(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes academic session year (e.g. '2023-2024', '2023-24', '23-24' -> '2023-24')."""
        if is_null_or_empty(val):
            return None, None
        s = str(val).strip()
        m = re.match(r"^(\d{4})[/-](\d{4})$", s)
        if m:
            y1, y2 = m.groups()
            std = f"{y1}-{y2[-2:]}"
            return std, "Academic Year Normalization"
        m2 = re.match(r"^(\d{4})[/-](\d{2})$", s)
        if m2:
            y1, y2 = m2.groups()
            std = f"{y1}-{y2}"
            return std, "Academic Year Normalization"
        m3 = re.match(r"^(\d{4})$", s)
        if m3:
            y = int(m3.group(1))
            std = f"{y}-{str(y + 1)[-2:]}"
            return std, "Single Year Session Normalization"
        return s, None

    @staticmethod
    def standardize_class(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes class designation (e.g. '1', 'Class 1', 'Class 1st', 'I', '1st' -> 'Class 1')."""
        if is_null_or_empty(val):
            return None, None
        s = str(val).strip()
        lowered = s.lower().replace("class", "").replace("grade", "").replace("standard", "").strip()

        roman_map = {
            "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
            "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
            "xi": "11", "xii": "12"
        }
        if lowered in roman_map:
            num = roman_map[lowered]
            return f"Class {num}", "Roman Numeral Class Normalization"

        m = re.match(r"^(\d{1,2})(?:st|nd|rd|th)?$", lowered)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 12:
                return f"Class {num}", "Class Number Normalization"

        if "pre" in lowered or "kg" in lowered or "nursery" in lowered:
            return "Pre-Primary", "Pre-Primary Normalization"

        return s.title(), "Class Title Casing"

    @staticmethod
    def standardize_section(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes class section (e.g. 'a', 'sec-a' -> 'A')."""
        if is_null_or_empty(val):
            return None, None
        s = str(val).strip().upper()
        s = re.sub(r"^(?:SEC(?:TION)?[\s\.-]*)", "", s).strip()
        if len(s) == 1 and s.isalpha():
            return s, "Section Normalization"
        return s, None

    @staticmethod
    def validate_row(row: Dict[str, Any], row_number: int) -> List[Dict[str, Any]]:
        """Validates a single enrollment record."""
        errors: List[Dict[str, Any]] = []
        school_code = safe_str(row.get("School_Code"))

        # 1. Critical Column: School_Code
        if is_null_or_empty(row.get("School_Code")):
            errors.append({
                "entity": "enrollment",
                "row_number": row_number,
                "record_id": None,
                "column": "School_Code",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Mandatory School_Code is missing in enrollment record.",
                "suggested_action": "Provide 11-digit UDISE school code.",
            })
        else:
            _, is_valid_code, reason = validate_school_code(row.get("School_Code"))
            if not is_valid_code:
                errors.append({
                    "entity": "enrollment",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "School_Code",
                    "original_value": str(row.get("School_Code")),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "WARNING" if "does not begin with" in (reason or "") else "ERROR",
                    "message": reason or "Invalid school code.",
                    "suggested_action": "Verify 11-digit UDISE code with Haryana state prefix 06.",
                })

        # 2. Critical Column: Academic_Year
        acad_year = row.get("Academic_Year")
        if is_null_or_empty(acad_year):
            errors.append({
                "entity": "enrollment",
                "row_number": row_number,
                "record_id": school_code,
                "column": "Academic_Year",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Academic Year session is missing.",
                "suggested_action": "Enter academic session year (e.g. 2023-24).",
            })

        # 3. Critical Column: Class
        cls_val = row.get("Class")
        if is_null_or_empty(cls_val):
            errors.append({
                "entity": "enrollment",
                "row_number": row_number,
                "record_id": school_code,
                "column": "Class",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Class grade is missing in enrollment record.",
                "suggested_action": "Enter grade (Class 1 through 12).",
            })

        # 4. Critical Column: Enrollment_Count
        cnt_val = row.get("Enrollment_Count")
        if is_null_or_empty(cnt_val):
            errors.append({
                "entity": "enrollment",
                "row_number": row_number,
                "record_id": school_code,
                "column": "Enrollment_Count",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "WARNING",
                "message": "Enrollment count is missing (will default to 1 for student-level records).",
                "suggested_action": "Confirm student count or specify aggregate enrollment.",
            })
        else:
            try:
                cnt_num = float(cnt_val)
                if cnt_num < 0:
                    errors.append({
                        "entity": "enrollment",
                        "row_number": row_number,
                        "record_id": school_code,
                        "column": "Enrollment_Count",
                        "original_value": str(cnt_val),
                        "issue_type": "OUT_OF_RANGE",
                        "severity": "ERROR",
                        "message": f"Negative enrollment count ({cnt_num}) is invalid.",
                        "suggested_action": "Enter a non-negative student count.",
                    })
            except (ValueError, TypeError):
                errors.append({
                    "entity": "enrollment",
                    "row_number": row_number,
                    "record_id": school_code,
                    "column": "Enrollment_Count",
                    "original_value": str(cnt_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Enrollment count '{cnt_val}' is not a valid number.",
                    "suggested_action": "Enter numeric integer count.",
                })

        return errors

    @staticmethod
    def detect_duplicates(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Detects exact duplicates and logical enrollment duplicate conflicts."""
        duplicate_reports: List[Dict[str, Any]] = []
        exact_duplicate_indices: List[int] = []

        # 1. Exact duplicates
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
                "entity": "enrollment",
                "duplicate_type": "EXACT_DUPLICATE",
                "field_matched": "ALL_COLUMNS",
                "matched_value": f"Row #{first_row} and #{','.join(map(str, dup_row_nums))}",
                "row_numbers": all_rows,
                "sample_records": [records[r - 1] for r in all_rows[:3]],
                "recommendation": "Retain initial occurrence; drop duplicate enrollment records.",
            })

        # 2. Composite key duplicate conflict: School_Code + Academic_Year + Class + Section + Gender
        composite_to_rows = defaultdict(list)
        for idx, row in enumerate(records, start=1):
            s_code = safe_str(row.get("School_Code")) or ""
            a_year = safe_str(row.get("Academic_Year")) or ""
            cls_val = safe_str(row.get("Class")) or ""
            sec_val = safe_str(row.get("Section")) or ""
            gen_val = safe_str(row.get("Gender")) or ""
            sid_val = safe_str(row.get("Student_ID"))

            # If student-level with Student_ID, check Student_ID
            if sid_val:
                key = f"STUDENT:{sid_val.upper()}"
            else:
                key = f"ENR:{s_code.upper()}|{a_year.lower()}|{cls_val.lower()}|{sec_val.upper()}|{gen_val.lower()}"

            composite_to_rows[key].append((idx, row))

        for comp_key, occurrences in composite_to_rows.items():
            if len(occurrences) > 1:
                row_nums = [item[0] for item in occurrences]
                first_rec = occurrences[0][1]
                has_conflict = False
                for other_idx, other_rec in occurrences[1:]:
                    if str(first_rec.get("Enrollment_Count", "")).strip() != str(other_rec.get("Enrollment_Count", "")).strip():
                        has_conflict = True
                        break

                if has_conflict:
                    duplicate_reports.append({
                        "entity": "enrollment",
                        "duplicate_type": "CONFLICTING_DUPLICATE",
                        "field_matched": "School_Code + Year + Class + Section + Gender",
                        "matched_value": comp_key,
                        "row_numbers": row_nums,
                        "sample_records": [item[1] for item in occurrences],
                        "recommendation": "Conflicting enrollment figures for the same school, cohort, and academic session.",
                    })

        return duplicate_reports, exact_duplicate_indices

    @staticmethod
    def clean_records(
        records: List[Dict[str, Any]],
        exact_dup_indices: List[int],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Cleans, standardizes, and deduplicates enrollment records."""
        clean_records: List[Dict[str, Any]] = []
        standardization_logs: List[Dict[str, Any]] = []

        for idx, row in enumerate(records, start=1):
            if (idx - 1) in exact_dup_indices:
                continue

            cleaned = dict(row)
            school_code = safe_str(row.get("School_Code"))

            # Whitespace trimming
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
                        "entity": "enrollment",
                        "record_id": std_code,
                        "row_number": idx,
                        "column": "School_Code",
                        "original_value": str(code_val),
                        "standard_value": std_code,
                        "rule": "Preserve Leading Zero / UDISE Normalization",
                    })

            # 2. Academic_Year standardization
            year_val = cleaned.get("Academic_Year")
            if not is_null_or_empty(year_val):
                std_year, rule = EnrollmentCleaningService.standardize_academic_year(year_val)
                if std_year and std_year != str(year_val).strip():
                    cleaned["Academic_Year"] = std_year
                    standardization_logs.append({
                        "entity": "enrollment",
                        "record_id": school_code,
                        "row_number": idx,
                        "column": "Academic_Year",
                        "original_value": str(year_val),
                        "standard_value": std_year,
                        "rule": rule or "Academic Year Normalization",
                    })

            # 3. Class standardization
            cls_val = cleaned.get("Class")
            if not is_null_or_empty(cls_val):
                std_cls, rule = EnrollmentCleaningService.standardize_class(cls_val)
                if std_cls and std_cls != str(cls_val).strip():
                    cleaned["Class"] = std_cls
                    standardization_logs.append({
                        "entity": "enrollment",
                        "record_id": school_code,
                        "row_number": idx,
                        "column": "Class",
                        "original_value": str(cls_val),
                        "standard_value": std_cls,
                        "rule": rule or "Class Normalization",
                    })

            # 4. Section standardization
            sec_val = cleaned.get("Section")
            if not is_null_or_empty(sec_val):
                std_sec, rule = EnrollmentCleaningService.standardize_section(sec_val)
                if std_sec and std_sec != str(sec_val).strip():
                    cleaned["Section"] = std_sec
                    standardization_logs.append({
                        "entity": "enrollment",
                        "record_id": school_code,
                        "row_number": idx,
                        "column": "Section",
                        "original_value": str(sec_val),
                        "standard_value": std_sec,
                        "rule": rule or "Section Normalization",
                    })

            # 5. Gender standardization
            gen_val = cleaned.get("Gender")
            if not is_null_or_empty(gen_val):
                std_gen, rule = StandardizationService.standardize_gender(gen_val)
                if std_gen and std_gen != str(gen_val).strip():
                    cleaned["Gender"] = std_gen
                    standardization_logs.append({
                        "entity": "enrollment",
                        "record_id": school_code,
                        "row_number": idx,
                        "column": "Gender",
                        "original_value": str(gen_val),
                        "standard_value": std_gen,
                        "rule": rule or "Gender Normalization",
                    })

            # 6. Enrollment_Count normalization
            cnt_val = cleaned.get("Enrollment_Count")
            if not is_null_or_empty(cnt_val):
                try:
                    cleaned["Enrollment_Count"] = int(float(cnt_val))
                except (ValueError, TypeError):
                    pass
            elif not is_null_or_empty(cleaned.get("Student_ID")):
                # Individual student-level record default
                cleaned["Enrollment_Count"] = 1

            clean_records.append(cleaned)

        return clean_records, standardization_logs
