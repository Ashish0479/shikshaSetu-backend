"""API contract tests for the L1-L2 multi-entity workflow."""

import io
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


def _csv(name, content):
    return ("files", (name, content.encode("utf-8"), "text/csv"))


def test_multi_entity_api_quality_duplicates_and_excel_download():
    client = TestClient(app, raise_server_exceptions=False)
    files = [
        _csv("teachers.csv", "Teacher_ID,Teacher_Name,Designation,District,School_Code\nHR-TCH-10001,Asha Devi,PGT,Karnal,06120100101\n"),
        _csv("schools.csv", "School_Code,School_Name,District\n06120100101,GSSS Karnal,Karnal\n06120100101,GSSS Karnal,Karnal\n"),
        _csv("enrollment.csv", "School_Code,Academic_Year,Class,Enrollment_Count\n06120100101,2024-2025,10,30\n"),
        _csv("locations.csv", "School_Code,District,Latitude,Longitude\n06120100101,Karnal,29.68,76.99\n"),
    ]
    upload = client.post("/api/upload/multi", files=files)
    assert upload.status_code == 201
    dataset_id = upload.json()["dataset_id"]

    quality = client.get(f"/api/quality/{dataset_id}")
    assert quality.status_code == 200
    assert "valid_rows_count" in quality.json()
    assert "issue_counts_by_severity" in quality.json()

    duplicates = client.get(f"/api/quality/{dataset_id}/duplicates?entity=schools")
    assert duplicates.status_code == 200
    assert duplicates.json()["exact_duplicates_count"] == 1
    assert duplicates.json()["duplicates"][0]["entity"] == "schools"

    workbook = client.get(f"/api/datasets/{dataset_id}/download-excel")
    assert workbook.status_code == 200
    assert workbook.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument")


def test_multi_sheet_workbook_is_inspected_and_processed_as_multiple_entities():
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame([{"Teacher_ID": "HR-TCH-10001", "Teacher_Name": "Asha Devi", "Designation": "PGT", "District": "Karnal"}]).to_excel(writer, sheet_name="Teachers", index=False)
        pd.DataFrame([{"School_Code": "06120100101", "School_Name": "GSSS Karnal", "District": "Karnal"}]).to_excel(writer, sheet_name="Schools", index=False)
    client = TestClient(app, raise_server_exceptions=False)
    payload = {"files": ("education_master.xlsx", workbook.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    inspection = client.post("/api/upload/inspect", files=payload)
    assert inspection.status_code == 200
    assert inspection.json()["available_entities"] == ["teachers", "schools"]

    upload = client.post("/api/upload/multi", files=payload)
    assert upload.status_code == 201
    assert upload.json()["available_entities"] == ["teachers", "schools"]


def test_single_combined_csv_upload_creates_teacher_school_enrollment_records():
    client = TestClient(app, raise_server_exceptions=False)
    csv_content = (
        "Teacher_ID,Teacher_Name,Designation,Subject,Qualification,School_Code,School_Name,District,Block,"
        "Student_Count,Class,Academic_Year\n"
        "HR-TCH-10001,Asha Devi,PGT,Mathematics,M.Sc Mathematics,06120100101,GSSS Karnal,Karnal,Nilokheri,120,Class 10,2024-2025\n"
        "HR-TCH-10002,Ram Singh,TGT,Science,B.Sc,06120100101,GSSS Karnal,Karnal,Nilokheri,90,Class 9,2024-2025\n"
    )
    upload = client.post("/api/upload", files={"file": ("combined_school_file.csv", csv_content, "text/csv")})
    assert upload.status_code == 201
    payload = upload.json()
    assert "teachers" in payload["available_entities"]
    assert "schools" in payload["available_entities"]
    assert "enrollment" in payload["available_entities"]

    dataset_id = payload["dataset_id"]
    quality = client.get(f"/api/quality/{dataset_id}")
    assert quality.status_code == 200
    l3 = client.get(f"/api/quality/{dataset_id}/l3")
    assert l3.status_code == 200
    assert l3.json()["summary"]["schools_analyzed"] >= 1
