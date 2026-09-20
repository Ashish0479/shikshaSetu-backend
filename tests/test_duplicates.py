import pytest
from app.services.duplicate_service import DuplicateService

def test_exact_row_duplicates_detection():
    """Verify identical row duplicates are recognized and scheduled for elimination."""
    records = [
        {"Teacher_ID": "HR-101", "Teacher_Name": "Rajesh Kumar", "Subject": "Mathematics", "District": "Karnal"},
        {"Teacher_ID": "HR-102", "Teacher_Name": "Sunita Devi", "Subject": "Science", "District": "Hisar"},
        # Exact clone of record 1
        {"Teacher_ID": "HR-101", "Teacher_Name": "Rajesh Kumar", "Subject": "Mathematics", "District": "Karnal"},
    ]
    reports, exact_indices = DuplicateService.detect_duplicates(records)
    assert len(exact_indices) == 1
    assert exact_indices[0] == 2  # Third item (index 2) is a duplicate of index 0
    exact_reports = [r for r in reports if r["duplicate_type"] == "EXACT_ROW"]
    assert len(exact_reports) == 1
    assert 1 in exact_reports[0]["row_numbers"]
    assert 3 in exact_reports[0]["row_numbers"]

def test_logical_teacher_id_duplicate_conflict():
    """Verify duplicate Teacher_IDs with conflicting teacher attributes are flagged."""
    records = [
        {"Teacher_ID": "HR-105", "Teacher_Name": "Amit Sharma", "Designation": "PGT", "Subject": "Physics", "School_Code": "06120101"},
        {"Teacher_ID": "HR-105", "Teacher_Name": "Vikram Singh", "Designation": "TGT", "Subject": "Social Science", "School_Code": "06120199"},
    ]
    reports, exact_indices = DuplicateService.detect_duplicates(records)
    assert len(exact_indices) == 0  # Not exact rows
    logical_reports = [r for r in reports if r["duplicate_type"] == "LOGICAL_TEACHER_ID"]
    assert len(logical_reports) == 1
    assert logical_reports[0]["matched_value"] == "HR-105"
    assert "Critical conflict" in logical_reports[0]["recommendation"]

def test_logical_contact_number_duplication():
    """Verify when the same mobile number is assigned across two distinct teachers."""
    records = [
        {"Teacher_ID": "HR-201", "Teacher_Name": "Meena Kumari", "Contact_Number": "9812345678"},
        {"Teacher_ID": "HR-202", "Teacher_Name": "Ritu Bala", "Contact_Number": "+91 98123-45678"},
    ]
    reports, _ = DuplicateService.detect_duplicates(records)
    contact_reports = [r for r in reports if r["duplicate_type"] == "LOGICAL_CONTACT"]
    assert len(contact_reports) == 1
    assert contact_reports[0]["matched_value"] == "9812345678"
    assert "Shared mobile number" in contact_reports[0]["recommendation"]
