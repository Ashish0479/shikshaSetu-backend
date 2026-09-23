"""Multi-Entity Education Data Ingestion, Cleaning, and Standardization Pipeline Service.

Orchestrates:
L1: Ingestion, Multi-Sheet / Multi-File parsing, Entity Detection, Deterministic Schema Mapping.
L2: Entity-specific Validation, Standardization, Deduplication, Cross-Entity Consistency,
    Multi-Entity Quality Scoring, and Audit Logging.
"""

import io
import uuid
import openpyxl
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd

from app.models.canonical_schemas import (
    EntityType,
    ENTITY_CANONICAL_SCHEMAS,
    ENTITY_CRITICAL_COLUMNS,
    TEACHER_CRITICAL_COLUMNS,
    SCHOOL_CRITICAL_COLUMNS,
    ENROLLMENT_CRITICAL_COLUMNS,
    LOCATION_CRITICAL_COLUMNS,
)
from app.services.entity_detector import EntityDetector, SchemaMapper
from app.services.school_cleaning_service import SchoolCleaningService
from app.services.enrollment_cleaning_service import EnrollmentCleaningService
from app.services.location_cleaning_service import LocationCleaningService
from app.services.cross_entity_service import CrossEntityValidator
from app.services.standardization_service import StandardizationService
from app.services.validation_service import ValidationService
from app.services.duplicate_service import DuplicateService
from app.services.quality_service import QualityService
from app.utils.helpers import (
    is_null_or_empty,
    clean_phone_number,
    validate_email_address,
    CRITICAL_COLUMNS,
)


class MultiEntityPipelineService:
    @classmethod
    def execute_multi_entity_pipeline(
        cls,
        raw_entity_dfs: Dict[str, pd.DataFrame],
        detected_entity_types: Dict[str, EntityType],
        processing_id: Optional[str] = None,
        source_filename: str = "multi_entity_dataset",
        total_file_size_bytes: int = 0,
    ) -> Dict[str, Any]:
        """Executes the complete L1-L2 pipeline across multiple entity datasets.
        
        Args:
            raw_entity_dfs: dict of { source_key: DataFrame }
            detected_entity_types: dict of { source_key: EntityType }
            processing_id: unique processing / dataset ID
            source_filename: primary filename
            total_file_size_bytes: upload size
        """
        pid = processing_id or str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        # Group dataframes by resolved EntityType
        # If multiple files map to the same entity, concatenate them
        dfs_by_entity: Dict[str, List[pd.DataFrame]] = {
            EntityType.TEACHER.value: [],
            EntityType.SCHOOL.value: [],
            EntityType.ENROLLMENT.value: [],
            EntityType.LOCATION.value: [],
        }

        schema_mappings_summary: Dict[str, Any] = {}

        for source_key, df in raw_entity_dfs.items():
            entity_type = detected_entity_types.get(source_key, EntityType.UNKNOWN)
            if entity_type == EntityType.UNKNOWN:
                continue

            # Apply deterministic schema mapping
            mapper = SchemaMapper(entity_type)
            mapped_df, renames, unmapped = mapper.apply_mapping_to_dataframe(df)

            schema_mappings_summary[source_key] = {
                "entity": entity_type.value,
                "mappings": mapper.map_columns(list(df.columns))["mappings"],
                "unmapped_columns": unmapped,
            }

            dfs_by_entity[entity_type.value].append(mapped_df)

        # Merge DataFrames for each entity
        merged_dfs: Dict[str, pd.DataFrame] = {}
        for ent_name, df_list in dfs_by_entity.items():
            if df_list:
                merged = pd.concat(df_list, ignore_index=True)
                merged = merged.where(pd.notnull(merged), None)
                merged_dfs[ent_name] = merged

        available_entities = [e for e in dfs_by_entity.keys() if e in merged_dfs and len(merged_dfs[e]) > 0]
        all_entities = [EntityType.TEACHER.value, EntityType.SCHOOL.value, EntityType.ENROLLMENT.value, EntityType.LOCATION.value]
        missing_optional_entities = [e for e in all_entities if e not in available_entities]

        # Results containers
        raw_records_by_entity: Dict[str, List[Dict[str, Any]]] = {}
        clean_records_by_entity: Dict[str, List[Dict[str, Any]]] = {}
        validation_issues: List[Dict[str, Any]] = []
        standardization_logs: List[Dict[str, Any]] = []
        duplicate_reports: List[Dict[str, Any]] = []
        entity_scorecards: Dict[str, Dict[str, Any]] = {}
        entity_counts: Dict[str, Dict[str, int]] = {}

        # ----------------------------------------------------
        # 1. TEACHERS PROCESSING
        # ----------------------------------------------------
        if EntityType.TEACHER.value in merged_dfs:
            tch_df = merged_dfs[EntityType.TEACHER.value]
            raw_tch = tch_df.to_dict(orient="records")
            raw_records_by_entity[EntityType.TEACHER.value] = raw_tch

            # Validation
            tch_errors: List[Dict[str, Any]] = []
            for idx, row in enumerate(raw_tch, start=1):
                errs = ValidationService.validate_row(row, idx)
                for e in errs:
                    e["entity"] = "teachers"
                    e["record_id"] = str(row.get("Teacher_ID", "")).strip() or None
                tch_errors.extend(errs)
            validation_issues.extend(tch_errors)

            # Deduplication
            t_dup_reports, t_exact_indices = DuplicateService.detect_duplicates(raw_tch)
            for d in t_dup_reports:
                d["entity"] = "teachers"
            duplicate_reports.extend(t_dup_reports)

            # Cleaning & Standardization
            clean_tch, tch_std_logs = cls._clean_teachers(raw_tch, t_exact_indices)
            clean_records_by_entity[EntityType.TEACHER.value] = clean_tch
            standardization_logs.extend(tch_std_logs)

            # Missing Stats
            tch_missing = cls._calculate_missing_stats(tch_df, TEACHER_CRITICAL_COLUMNS)

            # Quality Score
            tch_scores = QualityService.calculate_entity_quality_score(
                entity_type="teachers",
                total_rows=len(raw_tch),
                total_columns=len(tch_df.columns),
                missing_stats=tch_missing,
                validation_errors=tch_errors,
                standardization_logs=tch_std_logs,
                duplicate_reports=t_dup_reports,
                exact_duplicate_count=len(t_exact_indices),
                critical_columns=TEACHER_CRITICAL_COLUMNS,
            )
            entity_scorecards[EntityType.TEACHER.value] = tch_scores
            entity_counts[EntityType.TEACHER.value] = {
                "raw": len(raw_tch),
                "clean": len(clean_tch),
                "duplicates_removed": len(t_exact_indices),
            }

        # ----------------------------------------------------
        # 2. SCHOOLS PROCESSING
        # ----------------------------------------------------
        if EntityType.SCHOOL.value in merged_dfs:
            sch_df = merged_dfs[EntityType.SCHOOL.value]
            raw_sch = sch_df.to_dict(orient="records")
            raw_records_by_entity[EntityType.SCHOOL.value] = raw_sch

            sch_errors: List[Dict[str, Any]] = []
            for idx, row in enumerate(raw_sch, start=1):
                errs = SchoolCleaningService.validate_row(row, idx)
                sch_errors.extend(errs)
            validation_issues.extend(sch_errors)

            s_dup_reports, s_exact_indices = SchoolCleaningService.detect_duplicates(raw_sch)
            duplicate_reports.extend(s_dup_reports)

            clean_sch, sch_std_logs = SchoolCleaningService.clean_records(raw_sch, s_exact_indices)
            clean_records_by_entity[EntityType.SCHOOL.value] = clean_sch
            standardization_logs.extend(sch_std_logs)

            sch_missing = cls._calculate_missing_stats(sch_df, SCHOOL_CRITICAL_COLUMNS)

            sch_scores = QualityService.calculate_entity_quality_score(
                entity_type="schools",
                total_rows=len(raw_sch),
                total_columns=len(sch_df.columns),
                missing_stats=sch_missing,
                validation_errors=sch_errors,
                standardization_logs=sch_std_logs,
                duplicate_reports=s_dup_reports,
                exact_duplicate_count=len(s_exact_indices),
                critical_columns=SCHOOL_CRITICAL_COLUMNS,
            )
            entity_scorecards[EntityType.SCHOOL.value] = sch_scores
            entity_counts[EntityType.SCHOOL.value] = {
                "raw": len(raw_sch),
                "clean": len(clean_sch),
                "duplicates_removed": len(s_exact_indices),
            }

        # ----------------------------------------------------
        # 3. ENROLLMENT PROCESSING
        # ----------------------------------------------------
        if EntityType.ENROLLMENT.value in merged_dfs:
            enr_df = merged_dfs[EntityType.ENROLLMENT.value]
            raw_enr = enr_df.to_dict(orient="records")
            raw_records_by_entity[EntityType.ENROLLMENT.value] = raw_enr

            enr_errors: List[Dict[str, Any]] = []
            for idx, row in enumerate(raw_enr, start=1):
                errs = EnrollmentCleaningService.validate_row(row, idx)
                enr_errors.extend(errs)
            validation_issues.extend(enr_errors)

            e_dup_reports, e_exact_indices = EnrollmentCleaningService.detect_duplicates(raw_enr)
            duplicate_reports.extend(e_dup_reports)

            clean_enr, enr_std_logs = EnrollmentCleaningService.clean_records(raw_enr, e_exact_indices)
            clean_records_by_entity[EntityType.ENROLLMENT.value] = clean_enr
            standardization_logs.extend(enr_std_logs)

            enr_missing = cls._calculate_missing_stats(enr_df, ENROLLMENT_CRITICAL_COLUMNS)

            enr_scores = QualityService.calculate_entity_quality_score(
                entity_type="enrollment",
                total_rows=len(raw_enr),
                total_columns=len(enr_df.columns),
                missing_stats=enr_missing,
                validation_errors=enr_errors,
                standardization_logs=enr_std_logs,
                duplicate_reports=e_dup_reports,
                exact_duplicate_count=len(e_exact_indices),
                critical_columns=ENROLLMENT_CRITICAL_COLUMNS,
            )
            entity_scorecards[EntityType.ENROLLMENT.value] = enr_scores
            entity_counts[EntityType.ENROLLMENT.value] = {
                "raw": len(raw_enr),
                "clean": len(clean_enr),
                "duplicates_removed": len(e_exact_indices),
            }

        # ----------------------------------------------------
        # 4. LOCATIONS PROCESSING
        # ----------------------------------------------------
        if EntityType.LOCATION.value in merged_dfs:
            loc_df = merged_dfs[EntityType.LOCATION.value]
            raw_loc = loc_df.to_dict(orient="records")
            raw_records_by_entity[EntityType.LOCATION.value] = raw_loc

            loc_errors: List[Dict[str, Any]] = []
            for idx, row in enumerate(raw_loc, start=1):
                errs = LocationCleaningService.validate_row(row, idx)
                loc_errors.extend(errs)
            validation_issues.extend(loc_errors)

            l_dup_reports, l_exact_indices = LocationCleaningService.detect_duplicates(raw_loc)
            duplicate_reports.extend(l_dup_reports)

            clean_loc, loc_std_logs = LocationCleaningService.clean_records(raw_loc, l_exact_indices)
            clean_records_by_entity[EntityType.LOCATION.value] = clean_loc
            standardization_logs.extend(loc_std_logs)

            loc_missing = cls._calculate_missing_stats(loc_df, LOCATION_CRITICAL_COLUMNS)

            loc_scores = QualityService.calculate_entity_quality_score(
                entity_type="locations",
                total_rows=len(raw_loc),
                total_columns=len(loc_df.columns),
                missing_stats=loc_missing,
                validation_errors=loc_errors,
                standardization_logs=loc_std_logs,
                duplicate_reports=l_dup_reports,
                exact_duplicate_count=len(l_exact_indices),
                critical_columns=LOCATION_CRITICAL_COLUMNS,
            )
            entity_scorecards[EntityType.LOCATION.value] = loc_scores
            entity_counts[EntityType.LOCATION.value] = {
                "raw": len(raw_loc),
                "clean": len(clean_loc),
                "duplicates_removed": len(l_exact_indices),
            }

        # ----------------------------------------------------
        # 5. CROSS-ENTITY VALIDATION
        # ----------------------------------------------------
        cross_entity_issues = CrossEntityValidator.validate_cross_entities(
            teachers=clean_records_by_entity.get(EntityType.TEACHER.value),
            schools=clean_records_by_entity.get(EntityType.SCHOOL.value),
            enrollment=clean_records_by_entity.get(EntityType.ENROLLMENT.value),
            locations=clean_records_by_entity.get(EntityType.LOCATION.value),
        )
        validation_issues.extend(cross_entity_issues)

        # ----------------------------------------------------
        # 6. OVERALL QUALITY SCORECARD
        # ----------------------------------------------------
        overall_scores = QualityService.calculate_dataset_level_score(entity_scorecards)

        total_raw_rows_all = sum(cnt["raw"] for cnt in entity_counts.values())
        total_clean_rows_all = sum(cnt["clean"] for cnt in entity_counts.values())
        total_duplicates_removed = sum(cnt["duplicates_removed"] for cnt in entity_counts.values())

        # Standardization Summary
        std_summary_map: Dict[Tuple[str, str, str, str], int] = {}
        for log in standardization_logs:
            key = (log.get("entity", ""), log.get("column", ""), str(log.get("original_value", "")), str(log.get("standard_value", "")))
            std_summary_map[key] = std_summary_map.get(key, 0) + 1

        standardization_summary = [
            {
                "entity": ent,
                "column": col,
                "original_value": orig,
                "standard_value": std,
                "count": count,
            }
            for (ent, col, orig, std), count in sorted(std_summary_map.items(), key=lambda x: x[1], reverse=True)
        ]

        metadata = {
            "dataset_id": pid,
            "processing_id": pid,
            "filename": source_filename,
            "file_size_bytes": total_file_size_bytes,
            "available_entities": available_entities,
            "missing_optional_entities": missing_optional_entities,
            "entity_counts": entity_counts,
            "total_rows_raw": total_raw_rows_all,
            "total_rows_clean": total_clean_rows_all,
            "total_duplicates_removed": total_duplicates_removed,
            "total_columns": sum(len(df.columns) for df in merged_dfs.values()),
            "status": "processed",
            "created_at": created_at,
            "overall_quality_score": overall_scores["overall_score"],
            "column_names": [f"{ent}:{col}" for ent, df in merged_dfs.items() for col in df.columns],
        }

        quality_report = {
            "dataset_id": pid,
            "processing_id": pid,
            "filename": source_filename,
            "total_rows": total_raw_rows_all,
            "total_clean_rows": total_clean_rows_all,
            "scores": overall_scores,
            "entity_scores": entity_scorecards,
            "available_entities": available_entities,
            "missing_optional_entities": missing_optional_entities,
            "entity_counts": entity_counts,
            "cross_entity_issues_count": len(cross_entity_issues),
            "top_standardizations": standardization_summary[:20],
        }

        # Keep the long-standing quality endpoint contract intact while also
        # returning the entity-level scorecards above.  These summaries are
        # intentionally calculated after cross-entity validation so referential
        # issues are included in the review totals.
        issue_counts_by_type: Dict[str, int] = {}
        issue_counts_by_severity: Dict[str, int] = {}
        invalid_row_refs = set()
        for issue in validation_issues:
            issue_type = str(issue.get("issue_type", "UNKNOWN"))
            severity = str(issue.get("severity", "WARNING")).upper()
            issue_counts_by_type[issue_type] = issue_counts_by_type.get(issue_type, 0) + 1
            issue_counts_by_severity[severity] = issue_counts_by_severity.get(severity, 0) + 1
            if severity == "ERROR":
                invalid_row_refs.add((issue.get("entity", ""), issue.get("row_number")))

        total_missing_values = sum(
            1 for issue in validation_issues if issue.get("issue_type") == "MISSING_VALUE"
        )
        quality_report.update({
            "valid_rows_count": max(0, total_raw_rows_all - len(invalid_row_refs)),
            "invalid_rows_count": len(invalid_row_refs),
            "duplicate_rows_count": total_duplicates_removed,
            "total_missing_values": total_missing_values,
            "issue_counts_by_type": issue_counts_by_type,
            "issue_counts_by_severity": issue_counts_by_severity,
        })

        return {
            "metadata": metadata,
            "raw_records_by_entity": raw_records_by_entity,
            "clean_records_by_entity": clean_records_by_entity,
            "quality_report": quality_report,
            "validation_issues": validation_issues,
            "standardization_logs": standardization_logs,
            "standardization_summary": standardization_summary,
            "duplicate_reports": duplicate_reports,
            "schema_mappings": schema_mappings_summary,
            "available_entities": available_entities,
            "missing_optional_entities": missing_optional_entities,
        }

    @staticmethod
    def _calculate_missing_stats(df: pd.DataFrame, critical_cols: List[str]) -> List[Dict[str, Any]]:
        total_rows = len(df)
        stats = []
        for col in df.columns:
            missing_indices = []
            for idx, val in enumerate(df[col], start=1):
                if is_null_or_empty(val):
                    missing_indices.append(idx)
            m_count = len(missing_indices)
            pct = round((m_count / total_rows) * 100.0, 2) if total_rows > 0 else 0.0
            stats.append({
                "column": col,
                "missing_count": m_count,
                "missing_percentage": pct,
                "is_critical": col in critical_cols,
                "affected_rows": missing_indices,
            })
        return stats

    @staticmethod
    def _clean_teachers(
        raw_records: List[Dict[str, Any]],
        exact_dup_indices: List[int],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Cleans and standardizes teacher records matching existing rules."""
        clean_records: List[Dict[str, Any]] = []
        standardization_logs: List[Dict[str, Any]] = []

        for idx, row in enumerate(raw_records, start=1):
            if (idx - 1) in exact_dup_indices:
                continue

            cleaned_row = dict(row)
            teacher_id = str(row.get("Teacher_ID", "")).strip() if not is_null_or_empty(row.get("Teacher_ID")) else None

            # Trim whitespace across string fields
            for k, v in cleaned_row.items():
                if isinstance(v, str):
                    cleaned_row[k] = StandardizationService.clean_text_whitespace(v)

            # 1. Subject Standardization
            subj_val = cleaned_row.get("Subject")
            desig_val = cleaned_row.get("Designation")
            if is_null_or_empty(subj_val) and desig_val and "PRT" in str(desig_val).upper():
                cleaned_row["Subject"] = "General (All Subjects)"
                standardization_logs.append({
                    "entity": "teachers",
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
                        "entity": "teachers",
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
                        "entity": "teachers",
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
                        "entity": "teachers",
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
                        "entity": "teachers",
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
                        "entity": "teachers",
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
                        "entity": "teachers",
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
                        "entity": "teachers",
                        "row_number": idx,
                        "teacher_id": teacher_id,
                        "column": "Contact_Number",
                        "original_value": str(phone_val),
                        "standard_value": std_phone,
                        "rule": "10-Digit Mobile Cleaning"
                    })

            # 8. Email Normalization
            email_val = cleaned_row.get("Email_Address")
            if not is_null_or_empty(email_val):
                std_email, is_valid_email = validate_email_address(email_val)
                if is_valid_email and std_email != str(email_val).strip():
                    cleaned_row["Email_Address"] = std_email
                    standardization_logs.append({
                        "entity": "teachers",
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
                            "entity": "teachers",
                            "row_number": idx,
                            "teacher_id": teacher_id,
                            "column": text_col,
                            "original_value": tc_val,
                            "standard_value": titled,
                            "rule": "Title Casing"
                        })

            clean_records.append(cleaned_row)

        return clean_records, standardization_logs

    @classmethod
    def generate_excel_workbook(
        cls,
        clean_records_by_entity: Dict[str, List[Dict[str, Any]]],
        quality_report: Dict[str, Any],
        validation_issues: List[Dict[str, Any]],
    ) -> bytes:
        """Generates a complete multi-sheet Excel (.xlsx) file containing:
        - Teachers (if available)
        - Schools (if available)
        - Enrollment (if available)
        - Locations (if available)
        - Quality_Report
        - Validation_Issues
        """
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            sheet_mapping = {
                EntityType.TEACHER.value: "Teachers",
                EntityType.SCHOOL.value: "Schools",
                EntityType.ENROLLMENT.value: "Enrollment",
                EntityType.LOCATION.value: "Locations",
            }

            for ent_key, sheet_title in sheet_mapping.items():
                recs = clean_records_by_entity.get(ent_key, [])
                if recs:
                    df = pd.DataFrame(recs)
                    df.to_excel(writer, sheet_name=sheet_title, index=False)

            # Quality Report Sheet
            scores = quality_report.get("scores", {})
            entity_scores = quality_report.get("entity_scores", {})
            score_rows = [
                {"Dimension": "Overall Data Quality Score", "Score": scores.get("overall_score"), "Weight": "100%"},
                {"Dimension": "Completeness", "Score": scores.get("completeness_score"), "Weight": f"{int(scores.get('weights', {}).get('completeness', 0.3)*100)}%"},
                {"Dimension": "Validity", "Score": scores.get("validity_score"), "Weight": f"{int(scores.get('weights', {}).get('validity', 0.3)*100)}%"},
                {"Dimension": "Consistency", "Score": scores.get("consistency_score"), "Weight": f"{int(scores.get('weights', {}).get('consistency', 0.2)*100)}%"},
                {"Dimension": "Uniqueness", "Score": scores.get("uniqueness_score"), "Weight": f"{int(scores.get('weights', {}).get('uniqueness', 0.2)*100)}%"},
            ]
            for ent_name, ent_sc in entity_scores.items():
                score_rows.append({
                    "Dimension": f"Entity: {ent_name.capitalize()} Score",
                    "Score": ent_sc.get("overall_score"),
                    "Weight": f"Comp: {ent_sc.get('completeness_score')} | Val: {ent_sc.get('validity_score')}"
                })

            df_scores = pd.DataFrame(score_rows)
            df_scores.to_excel(writer, sheet_name="Quality_Report", index=False)

            # Validation Issues Sheet
            if validation_issues:
                df_issues = pd.DataFrame(validation_issues)
                # Keep most useful columns first
                front_cols = ["entity", "severity", "issue_type", "column", "row_number", "record_id", "original_value", "message", "suggested_action"]
                existing_front = [c for c in front_cols if c in df_issues.columns]
                other_cols = [c for c in df_issues.columns if c not in existing_front]
                df_issues = df_issues[existing_front + other_cols]
                df_issues.to_excel(writer, sheet_name="Validation_Issues", index=False)
            else:
                df_no_issues = pd.DataFrame([{"Status": "No validation issues identified."}])
                df_no_issues.to_excel(writer, sheet_name="Validation_Issues", index=False)

        output.seek(0)
        return output.getvalue()
