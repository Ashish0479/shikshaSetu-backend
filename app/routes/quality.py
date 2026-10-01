from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.database.mongodb import db_client
from app.models.schemas import (
    QualityReportResponse,
    MissingValuesResponse,
    DuplicateAnalysisResponse,
    StandardizationResponse,
    ValidationErrorItem
)
from app.services.duplicate_service import DuplicateService
from app.services.school_cleaning_service import SchoolCleaningService
from app.services.enrollment_cleaning_service import EnrollmentCleaningService
from app.services.location_cleaning_service import LocationCleaningService
from app.services.l3_analysis_service import L3AnalysisService
from app.utils.helpers import is_null_or_empty, CRITICAL_COLUMNS

router = APIRouter(prefix="/quality", tags=["Data Quality Analysis"])


@router.get("/{dataset_id}", response_model=QualityReportResponse)
async def get_quality_report(dataset_id: str):
    """Returns the comprehensive data quality scorecard and issue summaries."""
    report = db_client.get_quality_report(dataset_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Quality report for dataset '{dataset_id}' not found.")
    return report


@router.get("/{dataset_id}/missing-values", response_model=MissingValuesResponse)
async def get_missing_values(
    dataset_id: str,
    entity: Optional[str] = Query(None, description="Filter missing values by entity (e.g. teachers, schools)")
):
    """Returns detailed missing value analysis per column, including affected row numbers."""
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

    target_entity = (entity or "teachers").lower()
    
    # Try fetching from entity_records
    records = db_client.get_entity_records(dataset_id, target_entity)
    if not records and target_entity in ("teacher", "teachers"):
        records_doc = db_client.get_teacher_records(dataset_id)
        records = records_doc.get("raw_records", []) if records_doc else []

    if not records:
        return MissingValuesResponse(
            dataset_id=dataset_id,
            total_missing_cells=0,
            total_cells=0,
            overall_missing_rate=0.0,
            columns=[]
        )

    cols = list(records[0].keys()) if records else []
    total_raw_rows = len(records)
    missing_stats = []
    total_missing_cells = 0

    for col in cols:
        affected = []
        for idx, r in enumerate(records, start=1):
            if is_null_or_empty(r.get(col)):
                affected.append(idx)
        m_count = len(affected)
        total_missing_cells += m_count
        pct = round((m_count / total_raw_rows) * 100.0, 2) if total_raw_rows > 0 else 0.0

        missing_stats.append({
            "column": col,
            "missing_count": m_count,
            "missing_percentage": pct,
            "is_critical": col in CRITICAL_COLUMNS,
            "affected_rows": affected
        })

    total_cells = total_raw_rows * len(cols)
    return MissingValuesResponse(
        dataset_id=dataset_id,
        total_missing_cells=total_missing_cells,
        total_cells=total_cells,
        overall_missing_rate=round((total_missing_cells / max(1, total_cells)) * 100.0, 2),
        columns=missing_stats
    )


@router.get("/{dataset_id}/duplicates", response_model=DuplicateAnalysisResponse)
async def get_duplicate_analysis(
    dataset_id: str,
    entity: Optional[str] = Query(None, description="Filter duplicates by entity")
):
    """Returns comprehensive duplicate analysis: exact duplicate rows and logical ID conflicts."""
    target_entity = (entity or "teachers").lower()
    aliases = {"teacher": "teachers", "school": "schools", "location": "locations"}
    target_entity = aliases.get(target_entity, target_entity)
    raw_records = db_client.get_raw_entity_records(dataset_id, target_entity)
    if target_entity == "schools":
        duplicate_reports, exact_indices = SchoolCleaningService.detect_duplicates(raw_records)
    elif target_entity == "enrollment":
        duplicate_reports, exact_indices = EnrollmentCleaningService.detect_duplicates(raw_records)
    elif target_entity == "locations":
        duplicate_reports, exact_indices = LocationCleaningService.detect_duplicates(raw_records)
    else:
        duplicate_reports, exact_indices = DuplicateService.detect_duplicates(raw_records)

    for report in duplicate_reports:
        report.setdefault("entity", target_entity)

    exact_count = len(exact_indices)
    logical_count = len([d for d in duplicate_reports if d.get("duplicate_type") not in ("EXACT_ROW", "EXACT_DUPLICATE")])
    impacted_rows = len(set([idx for d in duplicate_reports for idx in d.get("row_numbers", [])]))

    return DuplicateAnalysisResponse(
        dataset_id=dataset_id,
        exact_duplicates_count=exact_count,
        logical_duplicates_count=logical_count,
        total_duplicates_impacted_rows=impacted_rows,
        duplicates=duplicate_reports
    )


@router.get("/{dataset_id}/standardization", response_model=StandardizationResponse)
async def get_standardization_changes(
    dataset_id: str,
    entity: Optional[str] = Query(None, description="Filter standardization logs by entity: teachers, schools, enrollment, locations")
):
    """Returns the audit log and aggregated summary of all standardization transformations applied."""
    doc = db_client.get_standardization_logs(dataset_id)
    if not doc:
        return StandardizationResponse(
            dataset_id=dataset_id,
            total_transformations_applied=0,
            unique_rules_applied=0,
            summary=[],
            logs=[]
        )

    logs = doc.get("logs", [])
    summary = doc.get("summary", [])

    if entity:
        logs = [l for l in logs if l.get("entity", "teachers") == entity.lower()]
        summary = [s for s in summary if s.get("entity", "teachers") == entity.lower()]

    rules = set(l.get("rule") for l in logs if l.get("rule"))

    return StandardizationResponse(
        dataset_id=dataset_id,
        total_transformations_applied=len(logs),
        unique_rules_applied=len(rules),
        summary=summary,
        logs=logs
    )


@router.get("/{dataset_id}/issues", response_model=List[ValidationErrorItem])
async def get_validation_issues(
    dataset_id: str,
    entity: Optional[str] = Query(None, description="Filter by entity: teachers, schools, enrollment, locations"),
    severity: Optional[str] = Query(None, description="Filter by severity: ERROR or WARNING"),
    column: Optional[str] = Query(None, description="Filter by column name")
):
    """Returns granular validation issues with optional filters for entity, severity, and column."""
    errors = db_client.get_validation_errors(dataset_id)
    if entity:
        errors = [e for e in errors if str(e.get("entity", "teachers")).lower() == entity.lower()]
    if severity:
        errors = [e for e in errors if str(e.get("severity", "")).upper() == severity.upper()]
    if column:
        errors = [e for e in errors if str(e.get("column", "")).lower() == column.lower()]
    return errors


@router.get("/{dataset_id}/l3")
async def get_l3_analysis(
    dataset_id: str,
    ptr_threshold: Optional[float] = Query(None, description="Optional PTR threshold override"),
    max_distance_km: Optional[float] = Query(None, description="Optional geospatial imbalance threshold")
):
    """Runs the deterministic Layer 3 analytics across cleaned teacher, school, and enrollment data."""
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

    clean_records = db_client.get_all_clean_records(dataset_id)
    if not clean_records:
        raise HTTPException(status_code=404, detail=f"No cleaned records found for dataset '{dataset_id}'.")

    analysis = L3AnalysisService.analyze_record_sets(
        clean_data=clean_records,
        ptr_threshold=ptr_threshold,
        max_distance_km=max_distance_km,
    )
    return analysis
