from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime

class DatasetUploadResponse(BaseModel):
    dataset_id: str
    filename: str
    file_size_bytes: int
    total_rows: int
    total_columns: int
    status: str
    overall_quality_score: float
    created_at: str

class DatasetMetadata(BaseModel):
    dataset_id: str
    filename: str
    file_size_bytes: int
    total_rows_raw: int
    total_rows_clean: int
    total_columns: int
    status: str
    created_at: str
    overall_quality_score: float
    column_names: List[str]

class ValidationErrorItem(BaseModel):
    row_number: int
    teacher_id: Optional[str] = None
    column: str
    original_value: Optional[str] = None
    issue_type: str  # MISSING_VALUE, INVALID_FORMAT, OUT_OF_RANGE, INVALID_DOMAIN
    severity: str    # ERROR, WARNING
    message: str
    suggested_action: str
    standardized_value: Optional[str] = None

class StandardizationLogItem(BaseModel):
    row_number: int
    teacher_id: Optional[str] = None
    column: str
    original_value: str
    standard_value: str
    rule: str

class StandardizationSummaryItem(BaseModel):
    column: str
    original_value: str
    standard_value: str
    count: int

class MissingValueColumnStat(BaseModel):
    column: str
    missing_count: int
    missing_percentage: float
    is_critical: bool
    affected_rows: List[int]

class DuplicateRecordItem(BaseModel):
    duplicate_type: str  # EXACT_ROW, LOGICAL_TEACHER_ID, LOGICAL_CONTACT
    field_matched: str
    matched_value: str
    row_numbers: List[int]
    sample_records: List[Dict[str, Any]]
    recommendation: str

class QualityScoreBreakdown(BaseModel):
    completeness_score: float
    validity_score: float
    consistency_score: float
    uniqueness_score: float
    overall_score: float
    weights: Dict[str, float]
    explanation: List[str]

class QualityReportResponse(BaseModel):
    dataset_id: str
    filename: str
    total_rows: int
    valid_rows_count: int
    invalid_rows_count: int
    duplicate_rows_count: int
    total_missing_values: int
    scores: QualityScoreBreakdown
    issue_counts_by_type: Dict[str, int]
    issue_counts_by_severity: Dict[str, int]
    top_standardizations: List[StandardizationSummaryItem]

class DatasetPreviewResponse(BaseModel):
    dataset_id: str
    filename: str
    total_raw_rows: int
    total_clean_rows: int
    page: int
    page_size: int
    raw_columns: List[str]
    clean_columns: List[str]
    raw_rows: List[Dict[str, Any]]
    clean_rows: List[Dict[str, Any]]

class MissingValuesResponse(BaseModel):
    dataset_id: str
    total_missing_cells: int
    total_cells: int
    overall_missing_rate: float
    columns: List[MissingValueColumnStat]

class DuplicateAnalysisResponse(BaseModel):
    dataset_id: str
    exact_duplicates_count: int
    logical_duplicates_count: int
    total_duplicates_impacted_rows: int
    duplicates: List[DuplicateRecordItem]

class StandardizationResponse(BaseModel):
    dataset_id: str
    total_transformations_applied: int
    unique_rules_applied: int
    summary: List[StandardizationSummaryItem]
    logs: List[StandardizationLogItem]
