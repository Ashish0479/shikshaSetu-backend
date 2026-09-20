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
async def get_missing_values(dataset_id: str):
    """Returns detailed missing value analysis per column, including affected row numbers."""
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

    records_doc = db_client.get_teacher_records(dataset_id)
    if not records_doc:
        raise HTTPException(status_code=404, detail="Records not found.")

    raw_records = records_doc.get("raw_records", [])
    total_raw_rows = len(raw_records)
    cols = metadata.get("column_names", [])

    missing_stats = []
    total_missing_cells = 0

    for col in cols:
        affected = []
        for idx, r in enumerate(raw_records, start=1):
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
async def get_duplicate_analysis(dataset_id: str):
    """Returns comprehensive duplicate analysis: exact duplicate rows and logical ID conflicts."""
    records_doc = db_client.get_teacher_records(dataset_id)
    if not records_doc:
        raise HTTPException(status_code=404, detail="Records not found.")

    raw_records = records_doc.get("raw_records", [])
    duplicate_reports, exact_indices = DuplicateService.detect_duplicates(raw_records)
    
    exact_count = len(exact_indices)
    logical_count = len([d for d in duplicate_reports if d["duplicate_type"] != "EXACT_ROW"])
    impacted_rows = len(set([idx for d in duplicate_reports for idx in d["row_numbers"]]))

    return DuplicateAnalysisResponse(
        dataset_id=dataset_id,
        exact_duplicates_count=exact_count,
        logical_duplicates_count=logical_count,
        total_duplicates_impacted_rows=impacted_rows,
        duplicates=duplicate_reports
    )

@router.get("/{dataset_id}/standardization", response_model=StandardizationResponse)
async def get_standardization_changes(dataset_id: str):
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
    severity: Optional[str] = Query(None, description="Filter by severity: ERROR or WARNING"),
    column: Optional[str] = Query(None, description="Filter by column name")
):
    """Returns granular validation issues with optional filters for severity and column."""
    errors = db_client.get_validation_errors(dataset_id)
    if severity:
        errors = [e for e in errors if e.get("severity", "").upper() == severity.upper()]
    if column:
        errors = [e for e in errors if e.get("column", "").lower() == column.lower()]
    return errors
