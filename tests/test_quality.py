import pytest
import pandas as pd
from app.services.quality_service import QualityService
from app.services.cleaning_service import CleaningPipelineService
from app.config import settings

def test_quality_score_calculation_perfect_data():
    """Verify that a flawless dataset with no errors, missing values, or duplicates yields 100/100."""
    scores = QualityService.calculate_quality_scores(
        total_rows=50,
        total_columns=15,
        missing_stats=[{"column": "Teacher_ID", "missing_count": 0, "is_critical": True}],
        validation_errors=[],
        standardization_logs=[],
        duplicate_reports=[],
        exact_duplicate_count=0
    )
    assert scores["completeness_score"] == 100.0
    assert scores["validity_score"] == 100.0
    assert scores["consistency_score"] == 100.0
    assert scores["uniqueness_score"] == 100.0
    assert scores["overall_score"] == 100.0
    assert len(scores["explanation"]) == 4

def test_quality_score_weighted_deductions():
    """Verify quality score formula weights (30% Comp, 30% Val, 20% Cons, 20% Uniq)."""
    # Synthesize test data
    scores = QualityService.calculate_quality_scores(
        total_rows=100,
        total_columns=10,
        missing_stats=[
            {"column": "Teacher_ID", "missing_count": 5, "is_critical": True},
            {"column": "Email_Address", "missing_count": 10, "is_critical": False}
        ],
        validation_errors=[{"severity": "ERROR"}, {"severity": "ERROR"}, {"severity": "WARNING"}],
        standardization_logs=[{"rule": "r1"}, {"rule": "r2"}],
        duplicate_reports=[{"duplicate_type": "EXACT_ROW", "row_numbers": [1, 2]}],
        exact_duplicate_count=1
    )

    expected_overall = round(
        (0.30 * scores["completeness_score"]) +
        (0.30 * scores["validity_score"]) +
        (0.20 * scores["consistency_score"]) +
        (0.20 * scores["uniqueness_score"]),
        1
    )
    assert scores["overall_score"] == expected_overall
    assert 0.0 <= scores["overall_score"] <= 100.0

def test_full_cleaning_pipeline_execution():
    """Verify end-to-end execution of the 13-stage cleaning pipeline."""
    sample_data = {
        "Teacher_ID": ["HR-001", "HR-002", "HR-001"],  # 1 duplicate
        "Teacher_Name": ["  Anil Kumar  ", "Suman Rani", "  Anil Kumar  "],
        "Gender": ["M", "Female", "M"],
        "Date_of_Birth": ["1988-04-12", "1992-08-20", "1988-04-12"],
        "Designation": ["pgt", "PRT", "pgt"],
        "Subject": ["Maths", None, "Maths"],  # Maths -> Mathematics; PRT None -> General
        "Qualification": ["MSc Maths", "JBT", "MSc Maths"],
        "Experience_Years": ["8", "-2", "8"],  # -2 is an invalid error
        "School_Code": ["06120100101", "06120100102", "06120100101"],
        "School_Name": ["gsss karnal", "gps hisar", "gsss karnal"],
        "District": ["gurgaon", "Hisar", "gurgaon"],  # gurgaon -> Gurugram
        "Block": ["gurugram", "hisar-1", "gurugram"],
        "Contact_Number": ["+91 98123-45678", "9876543210", "+91 98123-45678"],
        "Email_Address": ["ANIL@GMAIL.COM", "suman.rani@haryana.gov.in", "ANIL@GMAIL.COM"],
        "Employment_Status": ["regular", "guest teacher", "regular"]
    }
    raw_df = pd.DataFrame(sample_data)

    result = CleaningPipelineService.execute_pipeline(
        raw_df=raw_df,
        filename="test_dataset.csv",
        file_size_bytes=1024
    )

    metadata = result["metadata"]
    assert metadata["total_rows_raw"] == 3
    assert metadata["total_rows_clean"] == 2  # 1 duplicate row dropped!

    # Check standardization log
    std_logs = result["standardization_logs"]
    std_columns = [log["column"] for log in std_logs]
    assert "Subject" in std_columns
    assert "District" in std_columns
    assert "Designation" in std_columns

    # Verify clean records
    clean_records = result["clean_records"]
    assert clean_records[0]["District"] == "Gurugram"
    assert clean_records[0]["Subject"] == "Mathematics"
    assert clean_records[0]["Qualification"] == "M.Sc Mathematics"
    assert clean_records[0]["Contact_Number"] == "9812345678"
    assert clean_records[0]["Email_Address"] == "anil@gmail.com"
    assert clean_records[1]["Subject"] == "General (All Subjects)"

    # Verify validation errors caught negative experience (-2)
    val_errors = result["validation_errors"]
    exp_errors = [e for e in val_errors if e["column"] == "Experience_Years"]
    assert len(exp_errors) > 0
    assert exp_errors[0]["severity"] == "ERROR"
