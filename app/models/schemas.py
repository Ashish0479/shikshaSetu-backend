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
    # Optional multi-entity extensions
    processing_id: Optional[str] = None
    available_entities: Optional[List[str]] = None
    missing_optional_entities: Optional[List[str]] = None
    entity_counts: Optional[Dict[str, Dict[str, int]]] = None


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
    processing_id: Optional[str] = None
    available_entities: Optional[List[str]] = None
    missing_optional_entities: Optional[List[str]] = None
    entity_counts: Optional[Dict[str, Dict[str, int]]] = None


class ValidationErrorItem(BaseModel):
    entity: Optional[str] = "teachers"
    row_number: int
    record_id: Optional[str] = None
    teacher_id: Optional[str] = None
    column: str
    original_value: Optional[str] = None
    issue_type: str  # MISSING_VALUE, INVALID_FORMAT, OUT_OF_RANGE, INVALID_DOMAIN, UNMATCHED_*, etc.
    severity: str    # ERROR, WARNING, INFO
    message: str
    suggested_action: str
    standardized_value: Optional[str] = None


class StandardizationLogItem(BaseModel):
    entity: Optional[str] = "teachers"
    row_number: int
    record_id: Optional[str] = None
    teacher_id: Optional[str] = None
    column: str
    original_value: str
    standard_value: str
    rule: str


class StandardizationSummaryItem(BaseModel):
    entity: Optional[str] = "teachers"
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
    entity: Optional[str] = "teachers"
    duplicate_type: str  # EXACT_ROW, EXACT_DUPLICATE, LOGICAL_TEACHER_ID, LOGICAL_CONTACT, CONFLICTING_DUPLICATE
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
    # Multi-entity optional fields
    available_entities: Optional[List[str]] = None
    missing_optional_entities: Optional[List[str]] = None
    entity_scores: Optional[Dict[str, Any]] = None
    entity_counts: Optional[Dict[str, Dict[str, int]]] = None
    cross_entity_issues_count: Optional[int] = None


class DatasetPreviewResponse(BaseModel):
    dataset_id: str
    filename: str
    entity: Optional[str] = "teachers"
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


# --------------------------------------------------------------------------
# Multi-Entity Inspection & Upload Schemas
# --------------------------------------------------------------------------

class ColumnMappingItem(BaseModel):
    raw_column: str
    canonical_column: Optional[str] = None
    mapping_reason: str
    confidence: float
    is_mapped: bool


class EntityInspectionItem(BaseModel):
    source_key: str
    detected_entity: str
    confidence: float
    reason: str
    total_rows: int
    total_columns: int
    raw_columns: List[str]
    mappings: List[ColumnMappingItem]
    unmapped_columns: List[str]
    status: str  # Ready, Ambiguous, etc.


class MultiEntityInspectionResponse(BaseModel):
    sources: List[EntityInspectionItem]
    available_entities: List[str]
    missing_optional_entities: List[str]
    can_process: bool
