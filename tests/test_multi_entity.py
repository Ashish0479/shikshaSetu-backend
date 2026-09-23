"""Automated Test Suite for Multi-Entity Education Data Ingestion, Cleaning, and Standardization System.

Tests:
1. Entity Detection (Teacher, School, Enrollment, Location, Unknown)
2. Deterministic Schema Mapping & Unmapped Columns
3. School Master Cleaning, Validation, Deduplication
4. Enrollment Cleaning, Validation, Deduplication
5. Location Cleaning, Validation, Deduplication
6. Cross-Entity Referential Integrity & Consistency Checks
7. Multi-Entity Quality Scoring & Aggregation
8. Multi-Sheet Excel Workbook Export
9. Backward Compatibility with Teacher-Only Ingestion
"""

import os
import io
import pytest
import pandas as pd

from app.models.canonical_schemas import EntityType
from app.services.entity_detector import EntityDetector, SchemaMapper
from app.services.school_cleaning_service import SchoolCleaningService
from app.services.enrollment_cleaning_service import EnrollmentCleaningService
from app.services.location_cleaning_service import LocationCleaningService
from app.services.cross_entity_service import CrossEntityValidator
from app.services.multi_entity_pipeline import MultiEntityPipelineService
from app.services.quality_service import QualityService


# --------------------------------------------------------------------------
# 1. Entity Detection Tests
# --------------------------------------------------------------------------
def test_entity_detection_teachers():
    cols = ["Teacher Name", "Designation", "Subject", "Qualification", "Experience Years", "UDISE Code"]
    res = EntityDetector.detect_entity(cols, filename="teachers_export.xlsx")
    assert res.entity_type == EntityType.TEACHER
    assert res.confidence >= 0.8
    assert "Teacher_Name" in res.column_matches.values()


def test_entity_detection_schools():
    cols = ["School Code", "School Name", "School Type", "Management", "Classes Offered", "Student Capacity"]
    res = EntityDetector.detect_entity(cols, filename="school_master.xlsx")
    assert res.entity_type == EntityType.SCHOOL
    assert res.confidence >= 0.8
    assert "School_Code" in res.column_matches.values()


def test_entity_detection_enrollment():
    cols = ["School Code", "Academic Year", "Class", "Section", "Gender", "Enrollment Count"]
    res = EntityDetector.detect_entity(cols, filename="student_enrollment.csv")
    assert res.entity_type == EntityType.ENROLLMENT
    assert res.confidence >= 0.8


def test_entity_detection_locations():
    cols = ["School Code", "District", "Block", "Village", "Latitude", "Longitude"]
    res = EntityDetector.detect_entity(cols, filename="school_gis_location.xlsx")
    assert res.entity_type == EntityType.LOCATION
    assert res.confidence >= 0.7


def test_entity_detection_ambiguous_returns_unknown():
    cols = ["Random Column A", "Random Column B", "Count"]
    res = EntityDetector.detect_entity(cols, filename="random_table.csv")
    assert res.entity_type == EntityType.UNKNOWN
    assert res.confidence == 0.0
    assert "Unable to confidently determine entity type" in res.reason


# --------------------------------------------------------------------------
# 2. Schema Mapping & Unmapped Columns Tests
# --------------------------------------------------------------------------
def test_schema_mapping_and_unmapped_columns():
    mapper = SchemaMapper(EntityType.SCHOOL)
    raw_cols = ["UDISE Code", "School Name", "District", "Unknown Extra Header", "Latitude"]
    res = mapper.map_columns(raw_cols)

    renames = res["canonical_renames"]
    assert renames["UDISE Code"] == "School_Code"
    assert renames["School Name"] == "School_Name"
    assert renames["District"] == "District"
    assert renames["Latitude"] == "Latitude"
    assert "Unknown Extra Header" in res["unmapped_columns"]

    # Verify unmapped columns are preserved in DataFrame
    df = pd.DataFrame([{"UDISE Code": "06120100101", "School Name": "GSSS Nilokheri", "Unknown Extra Header": "Extra Data"}])
    mapped_df, _, unmapped = mapper.apply_mapping_to_dataframe(df)
    assert "School_Code" in mapped_df.columns
    assert "School_Name" in mapped_df.columns
    assert "Unknown Extra Header" in mapped_df.columns
    assert "Unknown Extra Header" in unmapped


# --------------------------------------------------------------------------
# 3. School Master Cleaning & Validation Tests
# --------------------------------------------------------------------------
def test_school_cleaning_and_validation():
    raw_records = [
        # Normal
        {
            "School_Code": "06120100101",
            "School_Name": "  gsss nilokheri  ",
            "District": "gurgaon",  # Historical alias
            "Block": "nilokheri",
            "Student_Capacity": "1000",
            "Latitude": "29.8335",
            "Longitude": "76.9174"
        },
        # Defect: Missing leading zero, negative capacity, out-of-bounds lat
        {
            "School_Code": "6120100102",
            "School_Name": "GPS Test",
            "District": "Karnal",
            "Student_Capacity": "-20",  # Error
            "Latitude": "150.0",  # Out of bounds Error
            "Longitude": "76.9000"
        }
    ]

    # Validate
    errors_row1 = SchoolCleaningService.validate_row(raw_records[0], row_number=1)
    errors_row2 = SchoolCleaningService.validate_row(raw_records[1], row_number=2)

    # Row 1 should have 0 errors (gurgaon is normalized to Gurugram during cleaning)
    assert not any(e["severity"] == "ERROR" for e in errors_row1)

    # Row 2 should flag negative capacity and out of range latitude
    row2_cols = [e["column"] for e in errors_row2]
    assert "Student_Capacity" in row2_cols
    assert "Latitude" in row2_cols
    assert any(e["severity"] == "ERROR" and e["column"] == "Student_Capacity" for e in errors_row2)
    assert any(e["severity"] == "ERROR" and e["column"] == "Latitude" for e in errors_row2)

    # Clean
    clean_recs, std_logs = SchoolCleaningService.clean_records(raw_records, exact_dup_indices=[])
    assert clean_recs[0]["School_Name"] == "Gsss Nilokheri"
    assert clean_recs[0]["District"] == "Gurugram"  # District alias normalized
    assert clean_recs[1]["School_Code"] == "06120100102"  # Leading zero restored!


def test_school_duplicate_detection():
    records = [
        {"School_Code": "06120100101", "School_Name": "GSSS A", "District": "Karnal"},
        {"School_Code": "06120100101", "School_Name": "GSSS A", "District": "Karnal"},  # Exact clone
        {"School_Code": "06120100102", "School_Name": "GSSS B", "District": "Rohtak"},
        {"School_Code": "06120100102", "School_Name": "GPS Diverging", "District": "Sirsa"},  # Conflicting
    ]
    reports, exact_indices = SchoolCleaningService.detect_duplicates(records)
    assert len(exact_indices) == 1
    assert exact_indices[0] == 1  # Record 1 is exact clone of 0

    conflicts = [r for r in reports if r["duplicate_type"] == "CONFLICTING_DUPLICATE"]
    assert len(conflicts) == 1
    assert conflicts[0]["matched_value"] == "06120100102"


# --------------------------------------------------------------------------
# 4. Enrollment Cleaning & Validation Tests
# --------------------------------------------------------------------------
def test_enrollment_cleaning_and_validation():
    raw_records = [
        {
            "School_Code": "6120100101",  # Missing leading zero
            "Academic_Year": "2023-2024",
            "Class": "Class 9th",
            "Section": "sec-a",
            "Gender": "m",
            "Enrollment_Count": "45"
        },
        # Defect: Negative enrollment count
        {
            "School_Code": "06120100102",
            "Academic_Year": "2023-24",
            "Class": "Class 1",
            "Section": "A",
            "Gender": "Female",
            "Enrollment_Count": "-10"  # Error
        }
    ]

    errs_row2 = EnrollmentCleaningService.validate_row(raw_records[1], row_number=2)
    assert any(e["column"] == "Enrollment_Count" and e["severity"] == "ERROR" for e in errs_row2)

    clean_recs, std_logs = EnrollmentCleaningService.clean_records(raw_records, exact_dup_indices=[])
    assert clean_recs[0]["School_Code"] == "06120100101"
    assert clean_recs[0]["Academic_Year"] == "2023-24"
    assert clean_recs[0]["Class"] == "Class 9"
    assert clean_recs[0]["Section"] == "A"
    assert clean_recs[0]["Gender"] == "Male"
    assert clean_recs[0]["Enrollment_Count"] == 45


# --------------------------------------------------------------------------
# 5. Location Cleaning & Validation Tests
# --------------------------------------------------------------------------
def test_location_cleaning_and_validation():
    raw_records = [
        {
            "School_Code": "6120100101",
            "District": "mewat",  # Alias -> Nuh
            "Block": "nuh",
            "Village": "nuh",
            "Latitude": "28.1130",
            "Longitude": "77.0150"
        },
        # Defect: invalid longitude
        {
            "School_Code": "06120100102",
            "District": "Karnal",
            "Latitude": "29.8335",
            "Longitude": "250.0"  # Out of range Error
        }
    ]

    errs = LocationCleaningService.validate_row(raw_records[1], row_number=2)
    assert any(e["column"] == "Longitude" and e["severity"] == "ERROR" for e in errs)

    clean_recs, _ = LocationCleaningService.clean_records(raw_records, exact_dup_indices=[])
    assert clean_recs[0]["School_Code"] == "06120100101"
    assert clean_recs[0]["District"] == "Nuh"
    assert clean_recs[0]["Block"] == "Nuh"


# --------------------------------------------------------------------------
# 6. Cross-Entity Validation Tests
# --------------------------------------------------------------------------
def test_cross_entity_validation():
    schools = [
        {"School_Code": "06120100101", "School_Name": "GSSS Nilokheri", "District": "Karnal", "Latitude": 29.8335, "Longitude": 76.9174},
        {"School_Code": "06140100401", "School_Name": "GHS Ballabgarh", "District": "Faridabad", "Latitude": 28.3414, "Longitude": 77.3220},
    ]

    teachers = [
        # Normal match
        {"Teacher_ID": "HR-TCH-1", "School_Code": "06120100101", "District": "Karnal"},
        # Unmatched school code
        {"Teacher_ID": "HR-TCH-2", "School_Code": "06999999999", "District": "Hisar"},
        # District mismatch: Teacher says Gurugram, but school 06140100401 is in Faridabad!
        {"Teacher_ID": "HR-TCH-3", "School_Code": "06140100401", "District": "Gurugram"},
    ]

    enrollment = [
        # Unmatched school
        {"School_Code": "06888888888", "Class": "Class 10", "Enrollment_Count": 30},
    ]

    locations = [
        # Coordinate discrepancy > 5km vs School Master
        {"School_Code": "06140100401", "District": "Faridabad", "Latitude": 28.7000, "Longitude": 77.6000},
    ]

    issues = CrossEntityValidator.validate_cross_entities(
        teachers=teachers,
        schools=schools,
        enrollment=enrollment,
        locations=locations
    )

    issue_types = [i["issue_type"] for i in issues]
    assert "UNMATCHED_TEACHER_SCHOOL" in issue_types
    assert "TEACHER_SCHOOL_DISTRICT_MISMATCH" in issue_types
    assert "UNMATCHED_ENROLLMENT_SCHOOL" in issue_types
    assert "COORDINATE_DISCREPANCY" in issue_types


# --------------------------------------------------------------------------
# 7. End-to-End Multi-Entity Pipeline Execution
# --------------------------------------------------------------------------
def test_multi_entity_pipeline_end_to_end():
    tch_df = pd.DataFrame([
        {"Teacher_ID": "HR-001", "Teacher_Name": "Anil Kumar", "Designation": "PGT", "Subject": "Maths", "District": "gurgaon", "School_Code": "06120100101"},
        {"Teacher_ID": "HR-002", "Teacher_Name": "Sita Devi", "Designation": "PRT", "Subject": "", "District": "Karnal", "School_Code": "06120100101"},
    ])
    sch_df = pd.DataFrame([
        {"School_Code": "6120100101", "School_Name": "gsss nilokheri", "District": "Karnal", "School_Type": "Senior Secondary"},
    ])
    enr_df = pd.DataFrame([
        {"School_Code": "06120100101", "Academic_Year": "2023-2024", "Class": "10th", "Enrollment_Count": "50"},
    ])
    loc_df = pd.DataFrame([
        {"School_Code": "06120100101", "District": "karnal", "Latitude": "29.8335", "Longitude": "76.9174"},
    ])

    raw_dfs = {
        "teachers.csv": tch_df,
        "schools.csv": sch_df,
        "enrollment.csv": enr_df,
        "locations.csv": loc_df,
    }
    entity_types = {
        "teachers.csv": EntityType.TEACHER,
        "schools.csv": EntityType.SCHOOL,
        "enrollment.csv": EntityType.ENROLLMENT,
        "locations.csv": EntityType.LOCATION,
    }

    result = MultiEntityPipelineService.execute_multi_entity_pipeline(
        raw_entity_dfs=raw_dfs,
        detected_entity_types=entity_types,
        source_filename="all_entities.xlsx",
        total_file_size_bytes=4096,
    )

    metadata = result["metadata"]
    assert metadata["status"] == "processed"
    assert "teachers" in metadata["available_entities"]
    assert "schools" in metadata["available_entities"]
    assert "enrollment" in metadata["available_entities"]
    assert "locations" in metadata["available_entities"]
    assert len(metadata["missing_optional_entities"]) == 0

    # Verify separate canonical datasets generated
    clean_by_ent = result["clean_records_by_entity"]
    assert len(clean_by_ent["teachers"]) == 2
    assert len(clean_by_ent["schools"]) == 1
    assert len(clean_by_ent["enrollment"]) == 1
    assert len(clean_by_ent["locations"]) == 1

    # Verify standardizations
    assert clean_by_ent["teachers"][0]["Subject"] == "Mathematics"
    assert clean_by_ent["teachers"][0]["District"] == "Gurugram"
    assert clean_by_ent["schools"][0]["School_Code"] == "06120100101"
    assert clean_by_ent["enrollment"][0]["Class"] == "Class 10"

    # Verify Excel workbook generation
    excel_bytes = MultiEntityPipelineService.generate_excel_workbook(
        clean_records_by_entity=clean_by_ent,
        quality_report=result["quality_report"],
        validation_issues=result["validation_issues"],
    )
    assert len(excel_bytes) > 1000

    # Read back generated Excel to verify sheets
    excel_file = pd.ExcelFile(io.BytesIO(excel_bytes), engine="openpyxl")
    assert "Teachers" in excel_file.sheet_names
    assert "Schools" in excel_file.sheet_names
    assert "Enrollment" in excel_file.sheet_names
    assert "Locations" in excel_file.sheet_names
    assert "Quality_Report" in excel_file.sheet_names
    assert "Validation_Issues" in excel_file.sheet_names


# --------------------------------------------------------------------------
# 8. Backward Compatibility: Teacher-Only Ingestion
# --------------------------------------------------------------------------
def test_teacher_only_backward_compatibility():
    tch_df = pd.DataFrame([
        {"Teacher_ID": "HR-001", "Teacher_Name": "Ramesh Kumar", "Designation": "PGT", "Subject": "Physics", "District": "Hisar"},
    ])

    result = MultiEntityPipelineService.execute_multi_entity_pipeline(
        raw_entity_dfs={"teachers.csv": tch_df},
        detected_entity_types={"teachers.csv": EntityType.TEACHER},
        source_filename="teachers.csv",
        total_file_size_bytes=512,
    )

    metadata = result["metadata"]
    assert metadata["status"] == "processed"
    assert metadata["available_entities"] == ["teachers"]
    assert set(metadata["missing_optional_entities"]) == {"schools", "enrollment", "locations"}
    assert len(result["clean_records_by_entity"]["teachers"]) == 1
    assert metadata["overall_quality_score"] > 0.0
