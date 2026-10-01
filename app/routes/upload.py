import os
import json
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from app.services.ingestion_service import IngestionService
from app.services.entity_detector import EntityDetector, SchemaMapper
from app.services.multi_entity_pipeline import MultiEntityPipelineService
from app.models.canonical_schemas import EntityType
from app.database.mongodb import db_client
from app.models.schemas import (
    DatasetUploadResponse,
    MultiEntityInspectionResponse,
    EntityInspectionItem,
    ColumnMappingItem,
)

router = APIRouter(prefix="/upload", tags=["Data Ingestion & Pipeline"])


@router.post("", response_model=DatasetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(file: UploadFile = File(...)):
    """Uploads a dataset (CSV or Excel), automatically detects single/multi-sheet entities,
    executes the multi-entity L1-L2 cleaning pipeline, and persists results."""
    try:
        dfs_by_source, filename, file_size = await IngestionService.read_any_uploaded_file(file)

        # Detect entities for each sheet/source
        detected_entities: dict[str, EntityType] = {}
        for source_key, df in dfs_by_source.items():
            sheet_hint = source_key.split(" - ")[-1] if " - " in source_key else None
            detection = EntityDetector.detect_entity(
                columns=list(df.columns),
                filename=filename,
                sheet_name=sheet_hint
            )
            combined_types = EntityDetector.detect_combined_entity_types(list(df.columns))
            if detection.entity_type == EntityType.UNKNOWN and len(dfs_by_source) == 1 and combined_types:
                detection.entity_type = EntityType.TEACHER
            elif detection.entity_type == EntityType.UNKNOWN and len(dfs_by_source) == 1:
                detection.entity_type = EntityType.TEACHER
            detected_entities[source_key] = detection.entity_type

        # Execute multi-entity pipeline
        pipeline_result = MultiEntityPipelineService.execute_multi_entity_pipeline(
            raw_entity_dfs=dfs_by_source,
            detected_entity_types=detected_entities,
            source_filename=filename,
            total_file_size_bytes=file_size,
        )

        metadata = pipeline_result["metadata"]
        dataset_id = metadata["dataset_id"]

        # Persist across MongoDB collections
        db_client.insert_dataset(metadata)
        db_client.insert_entity_records(
            dataset_id=dataset_id,
            raw_records_by_entity=pipeline_result["raw_records_by_entity"],
            clean_records_by_entity=pipeline_result["clean_records_by_entity"],
        )
        db_client.insert_quality_report(
            dataset_id=dataset_id,
            report=pipeline_result["quality_report"],
        )
        db_client.insert_validation_errors(
            dataset_id=dataset_id,
            errors=pipeline_result["validation_issues"],
        )
        db_client.insert_standardization_logs(
            dataset_id=dataset_id,
            logs=pipeline_result["standardization_logs"],
            summary=pipeline_result["standardization_summary"],
        )

        return DatasetUploadResponse(
            dataset_id=dataset_id,
            processing_id=dataset_id,
            filename=filename,
            file_size_bytes=file_size,
            total_rows=metadata["total_rows_raw"],
            total_columns=metadata["total_columns"],
            status="processed",
            overall_quality_score=metadata["overall_quality_score"],
            created_at=metadata["created_at"],
            available_entities=metadata.get("available_entities"),
            missing_optional_entities=metadata.get("missing_optional_entities"),
            entity_counts=metadata.get("entity_counts"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during dataset processing: {str(e)}"
        )


@router.post("/inspect", response_model=MultiEntityInspectionResponse)
async def inspect_uploaded_files(files: List[UploadFile] = File(...)):
    """Inspects uploaded file(s) or sheets, performing deterministic entity detection
    and schema mapping without executing cleaning. Allows user verification and overrides."""
    try:
        all_dfs, primary_name, total_size = await IngestionService.read_multiple_files(files)
        inspection_items: List[EntityInspectionItem] = []
        found_entities = set()

        for source_key, df in all_dfs.items():
            sheet_hint = source_key.split(" - ")[-1] if " - " in source_key else None
            detection = EntityDetector.detect_entity(
                columns=list(df.columns),
                filename=source_key,
                sheet_name=sheet_hint,
            )

            # Get column mappings
            active_entity = detection.entity_type if detection.entity_type != EntityType.UNKNOWN else EntityType.TEACHER
            mapper = SchemaMapper(active_entity)
            map_res = mapper.map_columns(list(df.columns))

            mapping_items = [
                ColumnMappingItem(
                    raw_column=m["raw_column"],
                    canonical_column=m["canonical_column"],
                    mapping_reason=m["mapping_reason"],
                    confidence=m["confidence"],
                    is_mapped=m["is_mapped"],
                )
                for m in map_res["mappings"]
            ]

            status_str = "Ready" if detection.entity_type != EntityType.UNKNOWN else "Ambiguous"
            if detection.entity_type != EntityType.UNKNOWN:
                found_entities.add(detection.entity_type.value)

            inspection_items.append(
                EntityInspectionItem(
                    source_key=source_key,
                    detected_entity=detection.entity_type.value,
                    confidence=detection.confidence,
                    reason=detection.reason,
                    total_rows=len(df),
                    total_columns=len(df.columns),
                    raw_columns=list(df.columns),
                    mappings=mapping_items,
                    unmapped_columns=map_res["unmapped_columns"],
                    status=status_str,
                )
            )

        all_known = [EntityType.TEACHER.value, EntityType.SCHOOL.value, EntityType.ENROLLMENT.value, EntityType.LOCATION.value]
        available = [e for e in all_known if e in found_entities]
        missing = [e for e in all_known if e not in found_entities]

        return MultiEntityInspectionResponse(
            sources=inspection_items,
            available_entities=available,
            missing_optional_entities=missing,
            can_process=len(inspection_items) > 0,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to inspect uploaded files: {str(e)}"
        )


@router.post("/multi", response_model=DatasetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_multi_files(
    files: List[UploadFile] = File(...),
    entity_overrides: Optional[str] = Form(None),
):
    """Uploads and processes multiple files or multi-sheet workbooks with optional entity overrides.
    entity_overrides is a JSON string: { source_key: "teachers" | "schools" | "enrollment" | "locations" }
    """
    try:
        all_dfs, primary_name, total_size = await IngestionService.read_multiple_files(files)

        overrides_dict = {}
        if entity_overrides:
            try:
                overrides_dict = json.loads(entity_overrides)
            except Exception:
                pass

        detected_entities: dict[str, EntityType] = {}
        for source_key, df in all_dfs.items():
            if source_key in overrides_dict:
                detected_entities[source_key] = EntityType.from_str(overrides_dict[source_key])
            else:
                sheet_hint = source_key.split(" - ")[-1] if " - " in source_key else None
                detection = EntityDetector.detect_entity(
                    columns=list(df.columns),
                    filename=source_key,
                    sheet_name=sheet_hint,
                )
                detected_entities[source_key] = detection.entity_type

        pipeline_result = MultiEntityPipelineService.execute_multi_entity_pipeline(
            raw_entity_dfs=all_dfs,
            detected_entity_types=detected_entities,
            source_filename=primary_name,
            total_file_size_bytes=total_size,
        )

        metadata = pipeline_result["metadata"]
        dataset_id = metadata["dataset_id"]

        db_client.insert_dataset(metadata)
        db_client.insert_entity_records(
            dataset_id=dataset_id,
            raw_records_by_entity=pipeline_result["raw_records_by_entity"],
            clean_records_by_entity=pipeline_result["clean_records_by_entity"],
        )
        db_client.insert_quality_report(
            dataset_id=dataset_id,
            report=pipeline_result["quality_report"],
        )
        db_client.insert_validation_errors(
            dataset_id=dataset_id,
            errors=pipeline_result["validation_issues"],
        )
        db_client.insert_standardization_logs(
            dataset_id=dataset_id,
            logs=pipeline_result["standardization_logs"],
            summary=pipeline_result["standardization_summary"],
        )

        return DatasetUploadResponse(
            dataset_id=dataset_id,
            processing_id=dataset_id,
            filename=primary_name,
            file_size_bytes=total_size,
            total_rows=metadata["total_rows_raw"],
            total_columns=metadata["total_columns"],
            status="processed",
            overall_quality_score=metadata["overall_quality_score"],
            created_at=metadata["created_at"],
            available_entities=metadata.get("available_entities"),
            missing_optional_entities=metadata.get("missing_optional_entities"),
            entity_counts=metadata.get("entity_counts"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during multi-file dataset processing: {str(e)}"
        )


@router.post("/demo", response_model=DatasetUploadResponse, status_code=status.HTTP_201_CREATED)
async def load_synthetic_demo_dataset():
    """Loads the pre-packaged synthetic Haryana demonstration dataset."""
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "sample_haryana_teachers_raw.csv"),
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "sample_haryana_teachers_raw.csv"),
        "C:\\Users\\JDPK\\Desktop\\shikshaSetu\\teacher-data-quality-system\\data\\sample_haryana_teachers_raw.csv",
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

        pipeline_result = MultiEntityPipelineService.execute_multi_entity_pipeline(
            raw_entity_dfs={filename: df},
            detected_entity_types={filename: EntityType.TEACHER},
            source_filename=filename,
            total_file_size_bytes=file_size,
        )

        metadata = pipeline_result["metadata"]
        dataset_id = metadata["dataset_id"]

        db_client.insert_dataset(metadata)
        db_client.insert_entity_records(
            dataset_id=dataset_id,
            raw_records_by_entity=pipeline_result["raw_records_by_entity"],
            clean_records_by_entity=pipeline_result["clean_records_by_entity"],
        )
        db_client.insert_quality_report(
            dataset_id=dataset_id,
            report=pipeline_result["quality_report"],
        )
        db_client.insert_validation_errors(
            dataset_id=dataset_id,
            errors=pipeline_result["validation_issues"],
        )
        db_client.insert_standardization_logs(
            dataset_id=dataset_id,
            logs=pipeline_result["standardization_logs"],
            summary=pipeline_result["standardization_summary"],
        )

        return DatasetUploadResponse(
            dataset_id=dataset_id,
            processing_id=dataset_id,
            filename=filename,
            file_size_bytes=file_size,
            total_rows=metadata["total_rows_raw"],
            total_columns=metadata["total_columns"],
            status="processed",
            overall_quality_score=metadata["overall_quality_score"],
            created_at=metadata["created_at"],
            available_entities=metadata.get("available_entities"),
            missing_optional_entities=metadata.get("missing_optional_entities"),
            entity_counts=metadata.get("entity_counts"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load synthetic demo dataset: {str(e)}"
        )
