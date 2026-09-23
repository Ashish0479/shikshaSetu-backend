import io
import pandas as pd
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from app.database.mongodb import db_client
from app.models.schemas import DatasetMetadata, DatasetPreviewResponse
from app.services.multi_entity_pipeline import MultiEntityPipelineService

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("", response_model=List[DatasetMetadata])
async def list_datasets():
    """Returns a list of all uploaded and processed datasets with metadata."""
    datasets = db_client.list_datasets()
    return datasets


@router.get("/{dataset_id}", response_model=DatasetMetadata)
async def get_dataset(dataset_id: str):
    """Returns metadata for a specific dataset."""
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset with ID '{dataset_id}' not found.")
    return metadata


@router.get("/{dataset_id}/preview", response_model=DatasetPreviewResponse)
async def get_dataset_preview(
    dataset_id: str,
    entity: Optional[str] = Query(None, description="Entity type: teachers, schools, enrollment, locations"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Records per page"),
):
    """Returns paginated preview rows comparing raw ingested data against cleaned records for a given entity."""
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset with ID '{dataset_id}' not found.")

    available = metadata.get("available_entities", ["teachers"])
    target_entity = (entity or (available[0] if available else "teachers")).lower()

    clean_records = db_client.get_entity_records(dataset_id, target_entity) or []
    
    # Try getting raw records from entity_records or teacher_records
    raw_records = []
    if db_client.is_connected and db_client.db is not None:
        doc = db_client.db.entity_records.find_one({"dataset_id": dataset_id}, {"_id": 0})
    else:
        doc = db_client._in_memory_store["entity_records"].get(dataset_id)

    if doc and "raw_records_by_entity" in doc:
        raw_records = doc["raw_records_by_entity"].get(target_entity, [])
    elif target_entity in ("teachers", "teacher"):
        tch_doc = db_client.get_teacher_records(dataset_id)
        if tch_doc:
            raw_records = tch_doc.get("raw_records", [])

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    sliced_raw = raw_records[start_idx:end_idx]
    sliced_clean = clean_records[start_idx:end_idx]

    raw_cols = list(raw_records[0].keys()) if raw_records else []
    clean_cols = list(clean_records[0].keys()) if clean_records else []

    return DatasetPreviewResponse(
        dataset_id=dataset_id,
        filename=metadata.get("filename", "dataset"),
        entity=target_entity,
        total_raw_rows=len(raw_records),
        total_clean_rows=len(clean_records),
        page=page,
        page_size=page_size,
        raw_columns=raw_cols,
        clean_columns=clean_cols,
        raw_rows=sliced_raw,
        clean_rows=sliced_clean
    )


@router.get("/{dataset_id}/download")
async def download_clean_dataset(
    dataset_id: str,
    entity: Optional[str] = Query(None, description="Entity to download: teachers, schools, enrollment, locations, or excel/all"),
    format: Optional[str] = Query("csv", description="Format: csv or xlsx"),
):
    """Exports and streams the cleaned dataset.
    Supports individual entity CSVs or a complete multi-sheet Excel workbook.
    """
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset with ID '{dataset_id}' not found.")

    available = metadata.get("available_entities", ["teachers"])
    req_entity = (entity or "").strip().lower()

    # If Excel format requested or entity is "excel"/"all"
    if format.lower() == "xlsx" or req_entity in ("excel", "all"):
        all_clean = db_client.get_all_clean_records(dataset_id)
        quality_report = db_client.get_quality_report(dataset_id) or {}
        validation_issues = db_client.get_validation_errors(dataset_id) or []

        excel_bytes = MultiEntityPipelineService.generate_excel_workbook(
            clean_records_by_entity=all_clean,
            quality_report=quality_report,
            validation_issues=validation_issues,
        )

        base_name = metadata.get("filename", "dataset").rsplit(".", 1)[0]
        download_filename = f"cleaned_{base_name}.xlsx"

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{download_filename}"'
            }
        )

    # Individual entity CSV download
    target_entity = req_entity if req_entity in ("teachers", "schools", "enrollment", "locations") else (available[0] if available else "teachers")
    clean_records = db_client.get_entity_records(dataset_id, target_entity) or []

    if not clean_records:
        raise HTTPException(status_code=404, detail=f"No clean records found for entity '{target_entity}'.")

    df_clean = pd.DataFrame(clean_records)
    csv_buffer = io.StringIO()
    df_clean.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue().encode("utf-8")

    download_filename = f"cleaned_{target_entity}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"'
        }
    )


@router.get("/{dataset_id}/download-excel")
async def download_clean_excel_workbook(dataset_id: str):
    """Exports and streams the complete multi-sheet Excel dataset."""
    # Pass an explicit value because calling a FastAPI endpoint as a helper
    # otherwise leaves its ``Query`` default object in place.
    return await download_clean_dataset(dataset_id=dataset_id, entity=None, format="xlsx")
