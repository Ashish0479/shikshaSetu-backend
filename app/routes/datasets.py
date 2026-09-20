import io
import pandas as pd
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from app.database.mongodb import db_client
from app.models.schemas import DatasetMetadata, DatasetPreviewResponse

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
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Records per page")
):
    """Returns paginated preview rows comparing raw ingested data against cleaned records."""
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset with ID '{dataset_id}' not found.")

    records_doc = db_client.get_teacher_records(dataset_id)
    if not records_doc:
        raise HTTPException(status_code=404, detail="No teacher records found for this dataset.")

    raw_records = records_doc.get("raw_records", [])
    clean_records = records_doc.get("clean_records", [])

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    sliced_raw = raw_records[start_idx:end_idx]
    sliced_clean = clean_records[start_idx:end_idx]

    raw_cols = list(raw_records[0].keys()) if raw_records else []
    clean_cols = list(clean_records[0].keys()) if clean_records else []

    return DatasetPreviewResponse(
        dataset_id=dataset_id,
        filename=metadata.get("filename", "dataset"),
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
async def download_clean_dataset(dataset_id: str):
    """Exports and streams the cleaned, standardized, and deduplicated dataset as a CSV file."""
    metadata = db_client.get_dataset(dataset_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Dataset with ID '{dataset_id}' not found.")

    records_doc = db_client.get_teacher_records(dataset_id)
    if not records_doc:
        raise HTTPException(status_code=404, detail="Clean records not found for this dataset.")

    clean_records = records_doc.get("clean_records", [])
    if not clean_records:
        raise HTTPException(status_code=404, detail="Dataset contains no clean records to download.")

    df_clean = pd.DataFrame(clean_records)
    csv_buffer = io.StringIO()
    df_clean.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue().encode("utf-8")

    orig_filename = metadata.get("filename", "dataset.csv")
    base_name = orig_filename.rsplit(".", 1)[0]
    download_filename = f"cleaned_{base_name}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"'
        }
    )
