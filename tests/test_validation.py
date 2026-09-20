import pytest
from app.utils.helpers import (
    validate_experience,
    validate_email_address,
    clean_phone_number,
    parse_date_of_birth,
    validate_school_code,
)
from app.services.validation_service import ValidationService

def test_experience_validation_rules():
    """Verify negative and out-of-range experiences trigger errors."""
    # Negative experience
    val, is_valid, reason = validate_experience(-4)
    assert not is_valid
    assert "Negative experience" in reason

    # Out of realistic service range (>45 yrs)
    val, is_valid, reason = validate_experience(52)
    assert not is_valid
    assert "exceeds realistic threshold" in reason

    # Valid experience
    val, is_valid, reason = validate_experience("14.5")
    assert is_valid
    assert val == 14.5
    assert reason is None

    # Zero experience (fresh PRT joiner)
    val, is_valid, reason = validate_experience(0)
    assert is_valid
    assert val == 0.0

def test_email_validation_rules():
    """Verify standard RFC email compliance check."""
    invalid_emails = ["invalid@", "teacher@domain", "@gmail.com", "plainaddress", "test@.com"]
    for email in invalid_emails:
        cleaned, is_valid = validate_email_address(email)
        assert not is_valid, f"Email '{email}' should be invalid"

    valid_emails = ["anita.devi@haryanaschools.gov.in", "teacher_haryana@gmail.com", "sunil.kumar12@yahoo.co.in"]
    for email in valid_emails:
        cleaned, is_valid = validate_email_address(email)
        assert is_valid, f"Email '{email}' should be valid"
        assert cleaned == email.lower()

def test_contact_number_validation_and_cleaning():
    """Verify phone cleaning to 10 digits and country-code handling."""
    # With +91 country code
    cleaned, is_valid = clean_phone_number("+91 98765 43210")
    assert is_valid
    assert cleaned == "9876543210"

    # With dashes
    cleaned, is_valid = clean_phone_number("98120-12345")
    assert is_valid
    assert cleaned == "9812012345"

    # Invalid length
    cleaned, is_valid = clean_phone_number("98765")
    assert not is_valid

    # Starts with invalid digit
    cleaned, is_valid = clean_phone_number("1234567890")
    assert not is_valid

def test_date_of_birth_validation():
    """Verify DOB parsing and age bounds checking (18 - 65 yrs)."""
    # Valid date
    dob, is_valid, _ = parse_date_of_birth("1985-06-15")
    assert is_valid
    assert dob == "1985-06-15"

    # Unrealistic age (child teacher)
    dob, is_valid, reason = parse_date_of_birth("2020-01-01")
    assert not is_valid
    assert "outside realistic teacher range" in reason

    # Malformed date string
    dob, is_valid, reason = parse_date_of_birth("not-a-date")
    assert not is_valid

def test_row_level_validation_missing_critical():
    """Verify validation engine flags missing critical Teacher_ID and District."""
    bad_row = {
        "Teacher_ID": None,
        "Teacher_Name": "Pooja Verma",
        "Designation": "PGT",
        "Subject": None,  # PGT missing subject should be ERROR
        "District": None,
        "Experience_Years": -2,
        "Contact_Number": "12345",
        "Email_Address": "bad-email"
    }
    errors = ValidationService.validate_row(bad_row, row_number=14)
    error_columns = [e["column"] for e in errors]
    error_severities = [e["severity"] for e in errors]

    assert "Teacher_ID" in error_columns
    assert "District" in error_columns
    assert "Subject" in error_columns
    assert "Experience_Years" in error_columns
    assert "Contact_Number" in error_columns
    assert "Email_Address" in error_columns
    assert error_severities.count("ERROR") >= 5
