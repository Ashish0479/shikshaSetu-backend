from typing import List, Dict, Any, Tuple
from collections import defaultdict
from app.utils.helpers import is_null_or_empty, clean_phone_number, validate_email_address

class DuplicateService:
    @staticmethod
    def detect_duplicates(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Analyzes records for both exact duplicate rows and logical/business duplicates.
        Returns:
            (duplicate_reports, list_of_exact_duplicate_row_indices_to_remove)"""
        duplicate_reports: List[Dict[str, Any]] = []
        exact_duplicate_indices: List[int] = []

        # 1. Exact Duplicate Detection
        seen_rows: Dict[Tuple, int] = {}
        exact_groups = defaultdict(list)

        for idx, row in enumerate(records, start=1):
            # Create a tuple of sorted key-value pairs ignoring casing and whitespace
            normalized_tuple = tuple(
                (k, str(v).strip().lower())
                for k, v in sorted(row.items())
                if not is_null_or_empty(v)
            )
            if normalized_tuple in seen_rows:
                original_row = seen_rows[normalized_tuple]
                exact_groups[normalized_tuple].append(idx)
                exact_duplicate_indices.append(idx - 1)  # 0-indexed for df dropping
            else:
                seen_rows[normalized_tuple] = idx

        for norm_tuple, dup_row_nums in exact_groups.items():
            first_row = seen_rows[norm_tuple]
            all_rows = [first_row] + dup_row_nums
            sample_rec = records[first_row - 1]
            duplicate_reports.append({
                "duplicate_type": "EXACT_ROW",
                "field_matched": "ALL_COLUMNS",
                "matched_value": f"Row #{first_row} and #{','.join(map(str, dup_row_nums))}",
                "row_numbers": all_rows,
                "sample_records": [records[r - 1] for r in all_rows[:3]],
                "recommendation": "Retain initial occurrence; eliminate redundant clone records during pipeline deduplication."
            })

        # 2. Logical Duplicate Detection: Teacher_ID conflict
        tid_to_rows = defaultdict(list)
        for idx, row in enumerate(records, start=1):
            tid = row.get("Teacher_ID")
            if not is_null_or_empty(tid):
                cleaned_tid = str(tid).strip().upper()
                tid_to_rows[cleaned_tid].append((idx, row))

        for tid, occurrences in tid_to_rows.items():
            if len(occurrences) > 1:
                # Check if it's already flagged as an exact duplicate group
                row_nums = [item[0] for item in occurrences]
                # If they have discrepancies in any other key field (Name, School, Subject, Exp), it's a logical conflict
                first_row = occurrences[0][1]
                has_conflict = False
                for other_idx, other_row in occurrences[1:]:
                    if any(str(first_row.get(col, "")).strip().lower() != str(other_row.get(col, "")).strip().lower()
                           for col in ["Teacher_Name", "Designation", "Subject", "School_Code"]):
                        has_conflict = True
                        break

                if has_conflict:
                    duplicate_reports.append({
                        "duplicate_type": "LOGICAL_TEACHER_ID",
                        "field_matched": "Teacher_ID",
                        "matched_value": tid,
                        "row_numbers": row_nums,
                        "sample_records": [item[1] for item in occurrences],
                        "recommendation": "Critical conflict: Same Teacher_ID assigned to diverging records. Requires manual registry review."
                    })

        # 3. Logical Duplicate: Contact Number shared across different Teacher IDs
        phone_to_records = defaultdict(list)
        for idx, row in enumerate(records, start=1):
            phone = row.get("Contact_Number")
            cleaned_phone, is_valid = clean_phone_number(phone)
            if cleaned_phone and is_valid:
                phone_to_records[cleaned_phone].append((idx, row.get("Teacher_ID"), row))

        for phone, entries in phone_to_records.items():
            if len(entries) > 1:
                unique_tids = {e[1] for e in entries if not is_null_or_empty(e[1])}
                if len(unique_tids) > 1:
                    row_nums = [e[0] for e in entries]
                    duplicate_reports.append({
                        "duplicate_type": "LOGICAL_CONTACT",
                        "field_matched": "Contact_Number",
                        "matched_value": phone,
                        "row_numbers": row_nums,
                        "sample_records": [e[2] for e in entries],
                        "recommendation": f"Shared mobile number detected across {len(unique_tids)} distinct Teacher IDs ({', '.join(map(str, unique_tids))})."
                    })

        return duplicate_reports, exact_duplicate_indices
#python -m uvicorn app.main:app --reload