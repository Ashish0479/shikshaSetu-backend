import pytest
from app.services.standardization_service import StandardizationService

def test_subject_standardization_variations():
    """Verify various abbreviations and casing map to canonical Haryana curriculum subjects."""
    test_cases = [
        ("Math", "Mathematics"),
        ("MATH", "Mathematics"),
        ("Maths", "Mathematics"),
        ("maths", "Mathematics"),
        ("Sci", "Science"),
        ("gen science", "Science"),
        ("Eng", "English"),
        ("hindi lit", "Hindi"),
        ("Skt", "Sanskrit"),
        ("SST", "Social Science"),
        ("s.st", "Social Science"),
        ("Phy", "Physics"),
        ("Chem", "Chemistry"),
        ("Bio", "Biology"),
        ("Comp Sci", "Computer Science"),
        ("it", "Computer Science"),
        ("Comm", "Commerce"),
        ("Eco", "Economics"),
        ("pet", "Physical Education"),
    ]
    for raw_input, expected_standard in test_cases:
        std_val, rule = StandardizationService.standardize_subject(raw_input)
        assert std_val == expected_standard, f"Failed on '{raw_input}': got '{std_val}', expected '{expected_standard}'"

def test_qualification_standardization_composite_and_abbr():
    """Verify academic qualifications and degrees are normalized correctly."""
    test_cases = [
        ("BEd", "B.Ed"),
        ("b.ed", "B.Ed"),
        ("m.ed", "M.Ed"),
        ("JBT", "D.El.Ed / JBT"),
        ("d.el.ed", "D.El.Ed / JBT"),
        ("MSc Maths", "M.Sc Mathematics"),
        ("m.sc maths", "M.Sc Mathematics"),
        ("MA English", "M.A English"),
        ("BSc Non Medical", "B.Sc (Non-Medical)"),
        ("b.com", "B.Com"),
        ("phd", "Ph.D"),
        ("mca", "MCA"),
    ]
    for raw_input, expected_standard in test_cases:
        std_val, _ = StandardizationService.standardize_qualification(raw_input)
        assert std_val == expected_standard, f"Failed on '{raw_input}': got '{std_val}', expected '{expected_standard}'"

def test_whitespace_normalization():
    """Verify multiple spaces, leading, and trailing whitespaces are trimmed."""
    raw = "   Ramesh    Kumar     Sharma   "
    cleaned = StandardizationService.clean_text_whitespace(raw)
    assert cleaned == "Ramesh Kumar Sharma"

def test_district_canonical_mapping():
    """Verify historic or colloquial district names are mapped to official 22 Haryana districts."""
    test_cases = [
        ("gurgaon", "Gurugram"),
        ("Gurgaon", "Gurugram"),
        ("mewat", "Nuh"),
        ("Mewat", "Nuh"),
        ("ch. dadri", "Charkhi Dadri"),
        ("ambala city", "Ambala"),
        ("mohindergarh", "Mahendragarh"),
        ("narnaul", "Mahendragarh"),
        ("sonepat", "Sonipat"),
        ("yamuna nagar", "Yamunanagar")
    ]
    for raw_input, expected_dist in test_cases:
        std_dist, _ = StandardizationService.standardize_district(raw_input)
        assert std_dist == expected_dist, f"Failed on '{raw_input}': got '{std_dist}', expected '{expected_dist}'"

def test_designation_and_employment_status():
    """Verify designation cadres and employment categories are standardized."""
    assert StandardizationService.standardize_designation("prt")[0] == "PRT"
    assert StandardizationService.standardize_designation("lecturer")[0] == "PGT"
    assert StandardizationService.standardize_designation("trained graduate teacher")[0] == "TGT"
    
    assert StandardizationService.standardize_employment_status("guest teacher")[0] == "Guest"
    assert StandardizationService.standardize_employment_status("hkrn")[0] == "Contractual (HKRN)"
    assert StandardizationService.standardize_employment_status("govt regular")[0] == "Regular"
