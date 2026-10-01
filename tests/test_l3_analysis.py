from app.services.ptr_analysis_service import PTRAnalysisService
from app.services.qualification_matcher_service import QualificationMatcherService
from app.services.geographic_paradox_service import GeographicParadoxService
from app.services.l3_analysis_service import L3AnalysisService


def test_ptr_analysis_shortage_and_surplus():
    schools = [
        {"School_Code": "06120100101", "School_Name": "GSSS A", "District": "Karnal"},
        {"School_Code": "06120100102", "School_Name": "GSSS B", "District": "Karnal"},
    ]
    teachers = [
        {"Teacher_ID": "T1", "School_Code": "06120100101", "Designation": "PGT", "Subject": "Mathematics", "Qualification": "M.Sc Mathematics"},
        {"Teacher_ID": "T2", "School_Code": "06120100101", "Designation": "TGT", "Subject": "Science", "Qualification": "B.Sc"},
        {"Teacher_ID": "T3", "School_Code": "06120100102", "Designation": "PRT", "Subject": "General (All Subjects)", "Qualification": "D.El.Ed / JBT"},
    ]
    enrollment = [
        {"School_Code": "06120100101", "Enrollment_Count": 120},
        {"School_Code": "06120100102", "Enrollment_Count": 40},
    ]

    result = PTRAnalysisService.analyze_schools(schools, teachers, enrollment, ptr_threshold=35.0)
    assert len(result["schools"]) == 2
    assert result["schools"][0]["status"] == "SHORTAGE"
    assert result["schools"][1]["status"] == "SHORTAGE"
    assert result["summary"]["schools_with_shortage"] == 2
    assert result["summary"]["schools_with_surplus"] == 0


def test_ptr_status_uses_shortage_surplus_tolerance():
    schools = [{"School_Code": "06120100101", "School_Name": "Test", "District": "Karnal"}]

    shortage = PTRAnalysisService.analyze_schools(
        schools, [{"School_Code": "06120100101"}] * 5,
        [{"School_Code": "06120100101", "Enrollment_Count": 300}],
        ptr_threshold=35.0,
    )["schools"][0]
    assert shortage["ptr"] == 60.0
    assert shortage["expected_teachers"] == 8.57
    assert shortage["shortage"] == 3.57
    assert shortage["surplus"] == 0.0
    assert shortage["status"] == "SHORTAGE"

    surplus = PTRAnalysisService.analyze_schools(
        schools, [{"School_Code": "06120100101"}] * 12,
        [{"School_Code": "06120100101", "Enrollment_Count": 180}],
        ptr_threshold=35.0,
    )["schools"][0]
    assert surplus["ptr"] == 15.0
    assert surplus["expected_teachers"] == 5.14
    assert surplus["shortage"] == 0.0
    assert surplus["surplus"] == 6.86
    assert surplus["status"] == "SURPLUS"

    for students, teachers in [(90, 3), (60, 2)]:
        result = PTRAnalysisService.analyze_schools(
            schools, [{"School_Code": "06120100101"}] * teachers,
            [{"School_Code": "06120100101", "Enrollment_Count": students}],
            ptr_threshold=35.0,
        )["schools"][0]
        assert result["shortage"] == 0.0
        assert result["status"] == "SURPLUS"


def test_qualification_matcher_statuses():
    teachers = [
        {"Teacher_ID": "T1", "Teacher_Name": "Asha", "School_Code": "06120100101", "Designation": "PGT", "Subject": "Mathematics", "Qualification": "M.Sc Mathematics"},
        {"Teacher_ID": "T2", "Teacher_Name": "Bharat", "School_Code": "06120100102", "Designation": "PRT", "Subject": "English", "Qualification": "B.A"},
        {"Teacher_ID": "T3", "Teacher_Name": "Chetna", "School_Code": "06120100103", "Designation": "TGT", "Subject": "Physics", "Qualification": ""},
    ]

    result = QualificationMatcherService.evaluate_teachers(teachers)
    assert result["summary"]["match_count"] >= 1
    assert any(r["qualification_match"] == "MATCH" for r in result["records"])
    assert any(r["qualification_match"] == "UNKNOWN" for r in result["records"])


def test_qualification_matcher_exact_specializations_and_incompatibility():
    teachers = [
        {"Teacher_ID": "MATH", "Subject": "Mathematics", "Qualification": "B.Sc Mathematics"},
        {"Teacher_ID": "ECON", "Subject": "Economics", "Qualification": "M.A Economics"},
        {"Teacher_ID": "PHYS", "Subject": "Physics", "Qualification": "M.Sc Physics"},
        {"Teacher_ID": "POL", "Subject": "Political Science", "Qualification": "M.A Political Science"},
        {"Teacher_ID": "BAD", "Subject": "Mathematics", "Qualification": "M.A History"},
        {"Teacher_ID": "CS", "Subject": "Computer Science", "Qualification": "BCA"},
        {"Teacher_ID": "UNKNOWN", "Subject": "Unlisted Subject", "Qualification": "Unlisted Degree"},
    ]

    records = {row["Teacher_ID"]: row for row in QualificationMatcherService.evaluate_teachers(teachers)["records"]}
    assert records["MATH"]["qualification_match"] == "MATCH"
    assert records["ECON"]["qualification_match"] == "MATCH"
    assert records["PHYS"]["qualification_match"] == "MATCH"
    assert records["POL"]["qualification_match"] == "MATCH"
    assert records["BAD"]["qualification_match"] == "MISMATCH"
    assert records["BAD"]["reason"] == "Qualification specialization does not match the assigned subject."
    assert records["CS"]["qualification_match"] == "MATCH"
    assert records["UNKNOWN"]["qualification_match"] == "UNKNOWN"


def test_geographic_paradox_detects_nearby_shortage_and_surplus():
    schools = [
        {"School_Code": "06120100101", "School_Name": "School A", "District": "Karnal", "Latitude": 29.68, "Longitude": 76.99},
        {"School_Code": "06120100102", "School_Name": "School B", "District": "Karnal", "Latitude": 29.690, "Longitude": 77.00},
    ]
    ptr = [
        {"school_code": "06120100101", "status": "SHORTAGE", "shortage": 2.0, "school_name": "School A"},
        {"school_code": "06120100102", "status": "SURPLUS", "surplus": 1.0, "school_name": "School B"},
    ]

    result = GeographicParadoxService.detect_imbalances(schools, ptr, max_distance_km=10.0)
    assert result["flag_count"] >= 1
    assert any(item["potential_issue"] for item in result["flags"])


def test_geographic_analysis_receives_final_ptr_statuses():
    schools = [
        {"School_Code": "S001", "School_Name": "Shortage School", "District": "Karnal", "Latitude": 29.680, "Longitude": 76.990},
        {"School_Code": "S002", "School_Name": "Surplus School", "District": "Karnal", "Latitude": 29.690, "Longitude": 77.000},
    ]
    teachers = ([{"School_Code": "S001"}] * 5) + ([{"School_Code": "S002"}] * 12)
    enrollment = [
        {"School_Code": "S001", "Enrollment_Count": 300},
        {"School_Code": "S002", "Enrollment_Count": 180},
    ]

    ptr = PTRAnalysisService.analyze_schools(schools, teachers, enrollment, ptr_threshold=35.0)
    statuses = {row["school_code"]: row["status"] for row in ptr["schools"]}
    assert statuses == {"S001": "SHORTAGE", "S002": "SURPLUS"}

    geographic = GeographicParadoxService.detect_imbalances(schools, ptr["schools"], max_distance_km=10.0)
    assert geographic["flag_count"] == 1
    assert geographic["flags"][0]["shortage_school_code"] == "S001"
    assert geographic["flags"][0]["surplus_school_code"] == "S002"


def test_l3_orchestrator_combines_analysis_outputs():
    dataset = {
        "teachers": [
            {"Teacher_ID": "T1", "Teacher_Name": "Asha", "School_Code": "06120100101", "Designation": "PGT", "Subject": "Mathematics", "Qualification": "M.Sc Mathematics", "District": "Karnal"},
            {"Teacher_ID": "T2", "Teacher_Name": "Bharat", "School_Code": "06120100101", "Designation": "PRT", "Subject": "General (All Subjects)", "Qualification": "D.El.Ed / JBT", "District": "Karnal"},
        ],
        "schools": [
            {"School_Code": "06120100101", "School_Name": "GSSS A", "District": "Karnal", "Latitude": 29.69, "Longitude": 77.00},
        ],
        "enrollment": [
            {"School_Code": "06120100101", "Enrollment_Count": 90},
        ],
    }

    result = L3AnalysisService.analyze_record_sets(dataset, ptr_threshold=35.0, max_distance_km=10.0)
    assert "ptr_analysis" in result
    assert "qualification_analysis" in result
    assert "geographic_analysis" in result
    assert result["summary"]["schools_analyzed"] >= 1
