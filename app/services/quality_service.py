from typing import List, Dict, Any
from app.config import settings
from app.utils.helpers import is_null_or_empty, CRITICAL_COLUMNS

class QualityService:
    @staticmethod
    def calculate_quality_scores(
        total_rows: int,
        total_columns: int,
        missing_stats: List[Dict[str, Any]],
        validation_errors: List[Dict[str, Any]],
        standardization_logs: List[Dict[str, Any]],
        duplicate_reports: List[Dict[str, Any]],
        exact_duplicate_count: int
    ) -> Dict[str, Any]:
        """Calculates transparent, explainable data quality scores (0-100) across 4 dimensions:
        1. Completeness (30%)
        2. Validity (30%)
        3. Consistency (20%)
        4. Uniqueness (20%)
        """
        if total_rows == 0 or total_columns == 0:
            return {
                "completeness_score": 0.0,
                "validity_score": 0.0,
                "consistency_score": 0.0,
                "uniqueness_score": 0.0,
                "overall_score": 0.0,
                "weights": {
                    "completeness": settings.WEIGHT_COMPLETENESS,
                    "validity": settings.WEIGHT_VALIDITY,
                    "consistency": settings.WEIGHT_CONSISTENCY,
                    "uniqueness": settings.WEIGHT_UNIQUENESS,
                },
                "explanation": ["Dataset contains no rows or columns to evaluate."]
            }

        total_cells = total_rows * total_columns
        total_missing_cells = sum(col["missing_count"] for col in missing_stats)

        # 1. Completeness Score (30%)
        # Weighted: Critical columns missing have double penalty
        critical_missing = sum(col["missing_count"] for col in missing_stats if col["is_critical"])
        non_critical_missing = total_missing_cells - critical_missing
        
        # Effective cell count with critical weight = 2.0
        critical_cols_count = len(CRITICAL_COLUMNS)
        non_critical_cols_count = max(1, total_columns - critical_cols_count)
        weighted_total = (critical_cols_count * 2.0 + non_critical_cols_count * 1.0) * total_rows
        weighted_missing = (critical_missing * 2.0) + (non_critical_missing * 1.0)
        
        completeness_ratio = max(0.0, (weighted_total - weighted_missing) / weighted_total)
        completeness_score = round(completeness_ratio * 100.0, 1)

        # 2. Validity Score (30%)
        # Total checked constraints: roughly 5 validations per row (experience, email, phone, dob, udise)
        total_checks = total_rows * 6
        error_count = sum(1 for e in validation_errors if e["severity"] == "ERROR")
        warning_count = sum(1 for e in validation_errors if e["severity"] == "WARNING")
        
        # Errors penalize 1.0 check, warnings penalize 0.25 check
        validity_penalty = (error_count * 1.0) + (warning_count * 0.25)
        validity_ratio = max(0.0, (total_checks - validity_penalty) / total_checks)
        validity_score = round(validity_ratio * 100.0, 1)

        # 3. Consistency Score (20%)
        # Standardizations needed reflect lack of canonical standardization in raw ingestion
        total_transformations = len(standardization_logs)
        # Ratio of categorical values that were clean vs messy
        expected_categorical_cells = total_rows * 5  # Designation, Subject, Qualification, District, Status
        consistency_ratio = max(0.0, (expected_categorical_cells - total_transformations) / expected_categorical_cells)
        consistency_score = round(consistency_ratio * 100.0, 1)

        # 4. Uniqueness Score (20%)
        # Penalize exact duplicates and logical conflicts
        logical_conflicts = sum(len(d["row_numbers"]) - 1 for d in duplicate_reports if d["duplicate_type"] != "EXACT_ROW")
        dup_penalty_rows = exact_duplicate_count + logical_conflicts
        uniqueness_ratio = max(0.0, (total_rows - dup_penalty_rows) / total_rows)
        uniqueness_score = round(uniqueness_ratio * 100.0, 1)

        # Overall Weighted Score
        overall_score = round(
            (settings.WEIGHT_COMPLETENESS * completeness_score) +
            (settings.WEIGHT_VALIDITY * validity_score) +
            (settings.WEIGHT_CONSISTENCY * consistency_score) +
            (settings.WEIGHT_UNIQUENESS * uniqueness_score),
            1
        )

        # Detailed explainable notes
        explanations = [
            f"Completeness ({completeness_score}/100, weight {int(settings.WEIGHT_COMPLETENESS*100)}%): "
            f"{total_missing_cells} total missing values detected across {total_rows} records "
            f"({critical_missing} in mandatory fields: {', '.join(CRITICAL_COLUMNS)}).",

            f"Validity ({validity_score}/100, weight {int(settings.WEIGHT_VALIDITY*100)}%): "
            f"{error_count} critical format/range errors and {warning_count} warnings detected in domain rules "
            f"(e.g., negative/excessive experience, malformed email/phone formats, invalid dates).",

            f"Consistency ({consistency_score}/100, weight {int(settings.WEIGHT_CONSISTENCY*100)}%): "
            f"{total_transformations} non-standard curriculum subjects, qualification abbreviations, "
            f"or district spelling variations standardized to official Haryana taxonomies.",

            f"Uniqueness ({uniqueness_score}/100, weight {int(settings.WEIGHT_UNIQUENESS*100)}%): "
            f"{exact_duplicate_count} exact duplicate rows and {logical_conflicts} logical conflict records "
            f"(shared Teacher_IDs or duplicate contact numbers) detected."
        ]

        return {
            "completeness_score": completeness_score,
            "validity_score": validity_score,
            "consistency_score": consistency_score,
            "uniqueness_score": uniqueness_score,
            "overall_score": overall_score,
            "weights": {
                "completeness": settings.WEIGHT_COMPLETENESS,
                "validity": settings.WEIGHT_VALIDITY,
                "consistency": settings.WEIGHT_CONSISTENCY,
                "uniqueness": settings.WEIGHT_UNIQUENESS,
            },
            "explanation": explanations
        }
