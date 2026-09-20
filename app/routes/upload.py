import os
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.services.ingestion_service import IngestionService
from app.services.cleaning_service import CleaningPipelineService
from app.database.mongodb import db_client
from app.models.schemas import DatasetUploadResponse

router = APIRouter(prefix="/upload", tags=["Data Ingestion & Pipeline"])

@router.post("", response_model=DatasetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(file: UploadFile = File(...)):
    """Uploads a teacher dataset (CSV or Excel), validates its schema,
    runs the 13-stage data quality pipeline, and persists results to MongoDB."""
    try:
        # Step 1: Ingest file and normalize column headers
        df, filename, file_size, _ = await IngestionService.read_uploaded_file(file)

        # Step 2: Execute cleaning and standardization pipeline
        pipeline_result = CleaningPipelineService.execute_pipeline(
            raw_df=df,
            filename=filename,
            file_size_bytes=file_size
        )

        metadata = pipeline_result["metadata"]
        dataset_id = metadata["dataset_id"]

        # Step 3: Persist across MongoDB collections
        db_client.insert_dataset(metadata)
        db_client.insert_teacher_records(
            dataset_id=dataset_id,
            raw_records=pipeline_result["raw_records"],
            clean_records=pipeline_result["clean_records"]
        )
        db_client.insert_quality_report(
            dataset_id=dataset_id,
            report=pipeline_result["quality_report"]
        )
        db_client.insert_validation_errors(
            dataset_id=dataset_id,
            errors=pipeline_result["validation_errors"]
        )
        db_client.insert_standardization_logs(
            dataset_id=dataset_id,
            logs=pipeline_result["standardization_logs"],
            summary=pipeline_result["standardization_summary"]
        )

        return DatasetUploadResponse(
            dataset_id=dataset_id,
            filename=filename,
            file_size_bytes=file_size,
            total_rows=metadata["total_rows_raw"],
            total_columns=metadata["total_columns"],
            status="processed",
            overall_quality_score=metadata["overall_quality_score"],
            created_at=metadata["created_at"]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during dataset processing: {str(e)}"
        )

@router.post("/demo", response_model=DatasetUploadResponse, status_code=status.HTTP_201_CREATED)
async def load_synthetic_demo_dataset():
    """Loads the pre-packaged synthetic Haryana teachers demonstration dataset."""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "sample_haryana_teachers_raw.csv"),
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "sample_haryana_teachers_raw.csv"),
        "C:\\Users\\JDPK\\Desktop\\shikshaSetu\\teacher-data-quality-system\\data\\sample_haryana_teachers_raw.csv"
    ]
    data_path = None
    for p in possible_paths:
        if os.path.exists(p):
            data_path = p
            break

    if not data_path or not os.path.exists(data_path):
        raise HTTPException(
            status_code=404,
            detail="Synthetic demo dataset file not found on server."
        )

    try:
        df = pd.read_csv(data_path, dtype=str)
        file_size = os.path.getsize(data_path)
        filename = "sample_haryana_teachers_raw.csv"

        pipeline_result = CleaningPipelineService.execute_pipeline(
            raw_df=df,
            filename=filename,
            file_size_bytes=file_size
        )

        metadata = pipeline_result["metadata"]
        dataset_id = metadata["dataset_id"]

        db_client.insert_dataset(metadata)
        db_client.insert_teacher_records(
            dataset_id=dataset_id,
            raw_records=pipeline_result["raw_records"],
            clean_records=pipeline_result["clean_records"]
        )
        db_client.insert_quality_report(
            dataset_id=dataset_id,
            report=pipeline_result["quality_report"]
        )
        db_client.insert_validation_errors(
            dataset_id=dataset_id,
            errors=pipeline_result["validation_errors"]
        )
        db_client.insert_standardization_logs(
            dataset_id=dataset_id,
            logs=pipeline_result["standardization_logs"],
            summary=pipeline_result["standardization_summary"]
        )

        return DatasetUploadResponse(
            dataset_id=dataset_id,
            filename=filename,
            file_size_bytes=file_size,
            total_rows=metadata["total_rows_raw"],
            total_columns=metadata["total_columns"],
            status="processed",
            overall_quality_score=metadata["overall_quality_score"],
            created_at=metadata["created_at"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load synthetic demo dataset: {str(e)}"
        )
