import uuid
from datetime import datetime
from typing import Dict, Any, List, Tuple
from collections import Counter
import pandas as pd
from app.utils.helpers import (
    is_null_or_empty,
    clean_phone_number,
    validate_email_address,
    CRITICAL_COLUMNS,
    STANDARD_COLUMNS,
)
from app.services.standardization_service import StandardizationService
from app.services.validation_service import ValidationService
from app.services.duplicate_service import DuplicateService
from app.services.quality_service import QualityService

class CleaningPipelineService:
    @staticmethod
    def execute_pipeline(raw_df: pd.DataFrame, filename: str, file_size_bytes: int) -> Dict[str, Any]:
        """Executes the full 13-stage cleaning, validation, and standardization pipeline.
        Returns a complete structured bundle of datasets, quality metrics, and audit logs.
        """
        dataset_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        total_raw_rows = len(raw_df)

        # Replace NaN, 'nan', 'N/A', etc. with None
        raw_df = raw_df.where(pd.notnull(raw_df), None)
        raw_records: List[Dict[str, Any]] = raw_df.to_dict(orient="records")

        # ----------------------------------------------------
        # Stage 1: Missing Value Detection
        # ----------------------------------------------------
        missing_stats: List[Dict[str, Any]] = []
        total_missing_cells = 0

        for col in raw_df.columns:
            missing_rows = []
            for row_idx, val in enumerate(raw_df[col], start=1):
                if is_null_or_empty(val):
                    missing_rows.append(row_idx)

            missing_count = len(missing_rows)
            total_missing_cells += missing_count
            pct = round((missing_count / total_raw_rows) * 100.0, 2) if total_raw_rows > 0 else 0.0
            is_critical = col in CRITICAL_COLUMNS

            missing_stats.append({
                "column": col,
                "missing_count": missing_count,
                "missing_percentage": pct,
                "is_critical": is_critical,
                "affected_rows": missing_rows
            })

        # ----------------------------------------------------
        # Stage 2: Validation Analysis (Row-by-Row)
        # ----------------------------------------------------
        validation_errors: List[Dict[str, Any]] = []
        rows_with_errors = set()

        for idx, row in enumerate(raw_records, start=1):
            row_errors = ValidationService.validate_row(row, idx)
            if row_errors:
                validation_errors.extend(row_errors)
                if any(e["severity"] == "ERROR" for e in row_errors):
                    rows_with_errors.add(idx)

        # ----------------------------------------------------
        # Stage 3: Duplicate Detection
        # ----------------------------------------------------
        duplicate_reports, exact_dup_row_indices = DuplicateService.detect_duplicates(raw_records)
        exact_duplicate_count = len(exact_dup_row_indices)

        # ----------------------------------------------------
        # Stage 4: Standardization Engine & Audit Logging
        # ----------------------------------------------------
        standardization_logs: List[Dict[str, Any]] = []
        clean_records: List[Dict[str, Any]] = []

        for idx, row in enumerate(raw_records, start=1):
            # Skip exact duplicate rows in the final clean dataset
            if (idx - 1) in exact_dup_row_indices:
                continue

            cleaned_row = dict(row)
            teacher_id = str(row.get("Teacher_ID", "")).strip() if not is_null_or_empty(row.get("Teacher_ID")) else None

            # Trim whitespace across all string fields
            for k, v in cleaned_row.items():
                if isinstance(v, str):
                    trimmed = StandardizationService.clean_text_whitespace(v)
                    cleaned_row[k] = trimmed

            # 1. Subject Standardization
            subj_val = cleaned_row.get("Subject")
            desig_val = cleaned_row.get("Designation")
            # If PRT and blank subject, auto-standardize
            if is_null_or_empty(subj_val) and desig_val and "PRT" in str(desig_val).upper():
                cleaned_row["Subject"] = "General (All Subjects)"
                standardization_logs.append({
                    "row_number": idx,
                    "teacher_id": teacher_id,
                    "column": "Subject",
                    "original_value": "EMPTY / MISSING",
                    "standard_value": "General (All Subjects)",
                    "rule": "PRT General Subject Default"
                })
            elif not is_null_or_empty(subj_val):
                std_subj, rule = StandardizationService.standardize_subject(subj_val)
                if std_subj != subj_val:
                    cleaned_row["Subject"] = std_subj
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Subject",
                        "original_value": str(subj_val),
                        "standard_value": std_subj,
                        "rule": rule or "Taxonomy Normalization"
                    })

            # 2. Qualification Standardization
            qual_val = cleaned_row.get("Qualification")
            if not is_null_or_empty(qual_val):
                std_qual, rule = StandardizationService.standardize_qualification(qual_val)
                if std_qual != qual_val:
                    cleaned_row["Qualification"] = std_qual
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Qualification",
                        "original_value": str(qual_val),
                        "standard_value": std_qual,
                        "rule": rule or "Qualification Normalization"
                    })

            # 3. District Standardization
            dist_val = cleaned_row.get("District")
            if not is_null_or_empty(dist_val):
                std_dist, rule = StandardizationService.standardize_district(dist_val)
                if std_dist != dist_val:
                    cleaned_row["District"] = std_dist
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "District",
                        "original_value": str(dist_val),
                        "standard_value": std_dist,
                        "rule": rule or "District Canonical Mapping"
                    })

            # 4. Designation Standardization
            if not is_null_or_empty(desig_val):
                std_desig, rule = StandardizationService.standardize_designation(desig_val)
                if std_desig != desig_val:
                    cleaned_row["Designation"] = std_desig
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Designation",
                        "original_value": str(desig_val),
                        "standard_value": std_desig,
                        "rule": rule or "Cadre Normalization"
                    })

            # 5. Employment Status Standardization
            status_val = cleaned_row.get("Employment_Status")
            if not is_null_or_empty(status_val):
                std_status, rule = StandardizationService.standardize_employment_status(status_val)
                if std_status != status_val:
                    cleaned_row["Employment_Status"] = std_status
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Employment_Status",
                        "original_value": str(status_val),
                        "standard_value": std_status,
                        "rule": rule or "Status Normalization"
                    })

            # 6. Gender Standardization
            gender_val = cleaned_row.get("Gender")
            if not is_null_or_empty(gender_val):
                std_gender, rule = StandardizationService.standardize_gender(gender_val)
                if std_gender != gender_val:
                    cleaned_row["Gender"] = std_gender
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Gender",
                        "original_value": str(gender_val),
                        "standard_value": std_gender,
                        "rule": rule or "Gender Normalization"
                    })

            # 7. Contact Number Clean Up
            phone_val = cleaned_row.get("Contact_Number")
            if not is_null_or_empty(phone_val):
                std_phone, is_valid_phone = clean_phone_number(phone_val)
                if is_valid_phone and std_phone != str(phone_val).strip():
                    cleaned_row["Contact_Number"] = std_phone
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Contact_Number",
                        "original_value": str(phone_val),
                        "standard_value": std_phone,
                        "rule": "10-Digit Mobile Cleaning"
                    })

            # 8. Email Normalization (Lowercased)
            email_val = cleaned_row.get("Email_Address")
            if not is_null_or_empty(email_val):
                std_email, is_valid_email = validate_email_address(email_val)
                if is_valid_email and std_email != str(email_val).strip():
                    cleaned_row["Email_Address"] = std_email
                    standardization_logs.append({
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Email_Address",
                        "original_value": str(email_val),
                        "standard_value": std_email,
                        "rule": "Lowercase Email Normalization"
                    })

            # 9. Proper casing for School Name and Block
            for text_col in ["School_Name", "Block"]:
                tc_val = cleaned_row.get(text_col)
                if not is_null_or_empty(tc_val) and isinstance(tc_val, str):
                    titled = tc_val.title()
                    if titled != tc_val:
                        cleaned_row[text_col] = titled
                        standardization_logs.append({
                            "row_number": idx,
                            "teacher_id": teacher_id,
                            "column": text_col,
                            "original_value": tc_val,
                            "standard_value": titled,
                            "rule": "Title Casing"
                        })

            clean_records.append(cleaned_row)

        total_clean_rows = len(clean_records)

        # ----------------------------------------------------
        # Stage 5: Standardization Summary Aggregation
        # ----------------------------------------------------
        std_summary_map = Counter(
            (log["column"], log["original_value"], log["standard_value"])
            for log in standardization_logs
        )
        standardization_summary = [
            {
                "column": col,
                "original_value": orig,
                "standard_value": std,
                "count": count
            }
            for (col, orig, std), count in std_summary_map.most_common()
        ]

        # ----------------------------------------------------
        # Stage 6: Quality Score Computation
        # ----------------------------------------------------
        scores = QualityService.calculate_quality_scores(
            total_rows=total_raw_rows,
            total_columns=len(raw_df.columns),
            missing_stats=missing_stats,
            validation_errors=validation_errors,
            standardization_logs=standardization_logs,
            duplicate_reports=duplicate_reports,
            exact_duplicate_count=exact_duplicate_count
        )

        # Issue counters
        issue_type_counter = Counter(e["issue_type"] for e in validation_errors)
        issue_severity_counter = Counter(e["severity"] for e in validation_errors)

        valid_rows_count = total_raw_rows - len(rows_with_errors)
        invalid_rows_count = len(rows_with_errors)

        # ----------------------------------------------------
        # Return Structured Result
        # ----------------------------------------------------
        metadata = {
            "dataset_id": dataset_id,
            "filename": filename,
            "file_size_bytes": file_size_bytes,
            "total_rows_raw": total_raw_rows,
            "total_rows_clean": total_clean_rows,
            "total_columns": len(raw_df.columns),
            "status": "processed",
            "created_at": created_at,
            "overall_quality_score": scores["overall_score"],
            "column_names": list(raw_df.columns)
        }

        quality_report = {
            "dataset_id": dataset_id,
            "filename": filename,
            "total_rows": total_raw_rows,
            "valid_rows_count": valid_rows_count,
            "invalid_rows_count": invalid_rows_count,
            "duplicate_rows_count": exact_duplicate_count,
            "total_missing_values": total_missing_cells,
            "scores": scores,
            "issue_counts_by_type": dict(issue_type_counter),
            "issue_counts_by_severity": dict(issue_severity_counter),
            "top_standardizations": standardization_summary[:10]
        }

        missing_values_report = {
            "dataset_id": dataset_id,
            "total_missing_cells": total_missing_cells,
            "total_cells": total_raw_rows * len(raw_df.columns),
            "overall_missing_rate": round((total_missing_cells / max(1, total_raw_rows * len(raw_df.columns))) * 100.0, 2),
            "columns": missing_stats
        }

        duplicate_analysis_report = {
            "dataset_id": dataset_id,
            "exact_duplicates_count": exact_duplicate_count,
            "logical_duplicates_count": len([d for d in duplicate_reports if d["duplicate_type"] != "EXACT_ROW"]),
            "total_duplicates_impacted_rows": len(set(
                [idx for d in duplicate_reports for idx in d["row_numbers"]]
            )),
            "duplicates": duplicate_reports
        }

        return {
            "metadata": metadata,
            "raw_records": raw_records,
            "clean_records": clean_records,
            "quality_report": quality_report,
            "validation_errors": validation_errors,
            "standardization_logs": standardization_logs,
            "standardization_summary": standardization_summary,
            "missing_values_report": missing_values_report,
            "duplicate_analysis_report": duplicate_analysis_report
        }
