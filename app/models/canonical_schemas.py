"""Canonical Data Models and Schema Definitions for Multi-Entity Education Data System.

Supports:
- Teachers (Teacher MIS records)
- Schools (UDISE School Master)
- Students / Enrollment (Student-level and aggregate grade/section enrollment)
- Locations (School geographic coordinates and administrative boundaries)
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Set
from pydantic import BaseModel, Field


class EntityType(str, Enum):
    TEACHER = "teachers"
    SCHOOL = "schools"
    ENROLLMENT = "enrollment"
    LOCATION = "locations"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, val: str) -> "EntityType":
        v = (val or "").strip().lower()
        if v in ("teacher", "teachers", "tch"):
            return cls.TEACHER
        if v in ("school", "schools", "sch"):
            return cls.SCHOOL
        if v in ("enrollment", "enrolment", "student", "students", "enr"):
            return cls.ENROLLMENT
        if v in ("location", "locations", "geo", "loc"):
            return cls.LOCATION
        return cls.UNKNOWN


# --------------------------------------------------------------------------
# Canonical Column Lists
# --------------------------------------------------------------------------

TEACHER_CANONICAL_COLUMNS: List[str] = [
    "Teacher_ID",
    "Teacher_Name",
    "Gender",
    "Date_of_Birth",
    "Designation",
    "Subject",
    "Qualification",
    "Experience_Years",
    "School_Code",
    "School_Name",
    "District",
    "Block",
    "Contact_Number",
    "Email_Address",
    "Employment_Status",
]

TEACHER_CRITICAL_COLUMNS: List[str] = [
    "Teacher_ID",
    "Teacher_Name",
    "Designation",
    "District",
]

SCHOOL_CANONICAL_COLUMNS: List[str] = [
    "School_Code",
    "School_Name",
    "District",
    "Block",
    "Village",
    "School_Type",
    "Management",
    "Classes_Offered",
    "Student_Capacity",
    "Latitude",
    "Longitude",
]

SCHOOL_CRITICAL_COLUMNS: List[str] = [
    "School_Code",
    "School_Name",
    "District",
]

ENROLLMENT_CANONICAL_COLUMNS: List[str] = [
    "Student_ID",
    "School_Code",
    "Academic_Year",
    "Class",
    "Section",
    "Gender",
    "Enrollment_Count",
]

ENROLLMENT_CRITICAL_COLUMNS: List[str] = [
    "School_Code",
    "Academic_Year",
    "Class",
    "Enrollment_Count",
]

LOCATION_CANONICAL_COLUMNS: List[str] = [
    "School_Code",
    "District",
    "Block",
    "Village",
    "Latitude",
    "Longitude",
]

LOCATION_CRITICAL_COLUMNS: List[str] = [
    "School_Code",
    "District",
    "Latitude",
    "Longitude",
]

# --------------------------------------------------------------------------
# Column Alias Mappings for Deterministic Schema Mapping
# --------------------------------------------------------------------------

TEACHER_ALIAS_MAP: Dict[str, str] = {
    "teacher_id": "Teacher_ID",
    "teacher id": "Teacher_ID",
    "teacherid": "Teacher_ID",
    "emp_id": "Teacher_ID",
    "employee_id": "Teacher_ID",
    "teacher_code": "Teacher_ID",
    "id": "Teacher_ID",
    "teacher_name": "Teacher_Name",
    "teacher name": "Teacher_Name",
    "name": "Teacher_Name",
    "employee_name": "Teacher_Name",
    "full_name": "Teacher_Name",
    "teacher full name": "Teacher_Name",
    "name of teacher": "Teacher_Name",
    "gender": "Gender",
    "sex": "Gender",
    "date_of_birth": "Date_of_Birth",
    "dob": "Date_of_Birth",
    "birth_date": "Date_of_Birth",
    "date of birth": "Date_of_Birth",
    "designation": "Designation",
    "post": "Designation",
    "cadre": "Designation",
    "role": "Designation",
    "subject": "Subject",
    "teaching_subject": "Subject",
    "sub": "Subject",
    "qualification": "Qualification",
    "highest_qualification": "Qualification",
    "education": "Qualification",
    "experience_years": "Experience_Years",
    "experience": "Experience_Years",
    "exp_years": "Experience_Years",
    "exp": "Experience_Years",
    "years_of_experience": "Experience_Years",
    "school_code": "School_Code",
    "udise": "School_Code",
    "udise_code": "School_Code",
    "udise code": "School_Code",
    "school id": "School_Code",
    "school_id": "School_Code",
    "school_name": "School_Name",
    "school": "School_Name",
    "name of school": "School_Name",
    "district": "District",
    "dist": "District",
    "district name": "District",
    "block": "Block",
    "educational_block": "Block",
    "contact_number": "Contact_Number",
    "phone": "Contact_Number",
    "mobile": "Contact_Number",
    "mobile_number": "Contact_Number",
    "phone_number": "Contact_Number",
    "contact": "Contact_Number",
    "email_address": "Email_Address",
    "email": "Email_Address",
    "mail": "Email_Address",
    "employment_status": "Employment_Status",
    "status": "Employment_Status",
    "emp_status": "Employment_Status",
    "type": "Employment_Status",
}

SCHOOL_ALIAS_MAP: Dict[str, str] = {
    "school_code": "School_Code",
    "school code": "School_Code",
    "school_id": "School_Code",
    "udise": "School_Code",
    "udise_code": "School_Code",
    "udise code": "School_Code",
    "udisecode": "School_Code",
    "school_name": "School_Name",
    "school name": "School_Name",
    "school": "School_Name",
    "institution_name": "School_Name",
    "district": "District",
    "district_name": "District",
    "dist": "District",
    "block": "Block",
    "block_name": "Block",
    "village": "Village",
    "village_name": "Village",
    "gram_panchayat": "Village",
    "school_type": "School_Type",
    "school category": "School_Type",
    "type": "School_Type",
    "category": "School_Type",
    "management": "Management",
    "school_management": "Management",
    "mgmt": "Management",
    "classes_offered": "Classes_Offered",
    "classes": "Classes_Offered",
    "class_range": "Classes_Offered",
    "grade_range": "Classes_Offered",
    "student_capacity": "Student_Capacity",
    "capacity": "Student_Capacity",
    "sanctioned_capacity": "Student_Capacity",
    "latitude": "Latitude",
    "lat": "Latitude",
    "longitude": "Longitude",
    "lon": "Longitude",
    "long": "Longitude",
    "lng": "Longitude",
}

ENROLLMENT_ALIAS_MAP: Dict[str, str] = {
    "student_id": "Student_ID",
    "student id": "Student_ID",
    "studentid": "Student_ID",
    "srn": "Student_ID",
    "student_reg_no": "Student_ID",
    "school_code": "School_Code",
    "school code": "School_Code",
    "udise": "School_Code",
    "udise_code": "School_Code",
    "udise code": "School_Code",
    "academic_year": "Academic_Year",
    "academic year": "Academic_Year",
    "session": "Academic_Year",
    "year": "Academic_Year",
    "class": "Class",
    "grade": "Class",
    "standard": "Class",
    "class_name": "Class",
    "section": "Section",
    "sec": "Section",
    "division": "Section",
    "gender": "Gender",
    "sex": "Gender",
    "enrollment_count": "Enrollment_Count",
    "enrollment": "Enrollment_Count",
    "enrolment": "Enrollment_Count",
    "student_count": "Enrollment_Count",
    "count": "Enrollment_Count",
    "total_students": "Enrollment_Count",
    "students": "Enrollment_Count",
    "no_of_students": "Enrollment_Count",
}

LOCATION_ALIAS_MAP: Dict[str, str] = {
    "school_code": "School_Code",
    "school code": "School_Code",
    "udise": "School_Code",
    "udise_code": "School_Code",
    "udise code": "School_Code",
    "school_id": "School_Code",
    "district": "District",
    "district_name": "District",
    "dist": "District",
    "block": "Block",
    "block_name": "Block",
    "village": "Village",
    "village_name": "Village",
    "latitude": "Latitude",
    "lat": "Latitude",
    "longitude": "Longitude",
    "lon": "Longitude",
    "long": "Longitude",
    "lng": "Longitude",
}

ENTITY_CANONICAL_SCHEMAS = {
    EntityType.TEACHER: TEACHER_CANONICAL_COLUMNS,
    EntityType.SCHOOL: SCHOOL_CANONICAL_COLUMNS,
    EntityType.ENROLLMENT: ENROLLMENT_CANONICAL_COLUMNS,
    EntityType.LOCATION: LOCATION_CANONICAL_COLUMNS,
}

ENTITY_CRITICAL_COLUMNS = {
    EntityType.TEACHER: TEACHER_CRITICAL_COLUMNS,
    EntityType.SCHOOL: SCHOOL_CRITICAL_COLUMNS,
    EntityType.ENROLLMENT: ENROLLMENT_CRITICAL_COLUMNS,
    EntityType.LOCATION: LOCATION_CRITICAL_COLUMNS,
}

ENTITY_ALIAS_MAPS = {
    EntityType.TEACHER: TEACHER_ALIAS_MAP,
    EntityType.SCHOOL: SCHOOL_ALIAS_MAP,
    EntityType.ENROLLMENT: ENROLLMENT_ALIAS_MAP,
    EntityType.LOCATION: LOCATION_ALIAS_MAP,
}
