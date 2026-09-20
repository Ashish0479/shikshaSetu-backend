from typing import List, Dict, Any, Tuple
from app.utils.helpers import (
    is_null_or_empty,
    clean_phone_number,
    validate_email_address,
    validate_experience,
    parse_date_of_birth,
    validate_school_code,
    STANDARD_COLUMNS,
    CRITICAL_COLUMNS,
)
from app.services.standardization_service import HARYANA_DISTRICTS

class ValidationService:
    @staticmethod
    def validate_schema(columns: List[str]) -> Tuple[bool, List[str], List[str]]:
        """Verifies present columns against schema.
        Returns (is_valid, missing_critical_columns, missing_optional_columns)."""
        present_set = set(columns)
        missing_critical = [col for col in CRITICAL_COLUMNS if col not in present_set]
        missing_optional = [col for col in STANDARD_COLUMNS if col not in present_set and col not in CRITICAL_COLUMNS]
        is_valid = len(missing_critical) == 0
        return is_valid, missing_critical, missing_optional

    @staticmethod
    def validate_row(row: Dict[str, Any], row_number: int) -> List[Dict[str, Any]]:
        """Validates a single teacher record across all domain rules.
        Returns a list of validation errors/warnings."""
        errors: List[Dict[str, Any]] = []
        teacher_id = str(row.get("Teacher_ID", "")).strip() if not is_null_or_empty(row.get("Teacher_ID")) else None

        # 1. Critical Column: Teacher_ID
        if is_null_or_empty(row.get("Teacher_ID")):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "Teacher_ID",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Mandatory Teacher_ID is missing.",
                "suggested_action": "Assign or cross-reference unique Haryana Teacher MIS Employee Code."
            })

        # 2. Critical Column: Teacher_Name
        teacher_name = row.get("Teacher_Name")
        if is_null_or_empty(teacher_name):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "Teacher_Name",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Teacher Name is missing.",
                "suggested_action": "Verify teacher full name in school establishment register."
            })

        # 3. Critical Column: Designation
        designation = row.get("Designation")
        if is_null_or_empty(designation):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "Designation",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "Teacher Designation/Cadre is missing.",
                "suggested_action": "Designate cadre: PRT, TGT, PGT, Headmaster, or Principal."
            })

        # 4. Critical Column: District
        district = row.get("District")
        if is_null_or_empty(district):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "District",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "ERROR",
                "message": "School District is missing.",
                "suggested_action": "Specify one of 22 administrative districts of Haryana."
            })
        elif str(district).strip().title() not in HARYANA_DISTRICTS:
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "District",
                "original_value": str(district),
                "issue_type": "INVALID_DOMAIN",
                "severity": "WARNING",
                "message": f"District '{district}' is not recognized in official Haryana districts list.",
                "suggested_action": "Confirm district spelling or administrative boundaries."
            })

        # 5. Subject Validation (Coupled with Designation)
        subject = row.get("Subject")
        desig_str = str(designation or "").upper()
        if is_null_or_empty(subject):
            if any(k in desig_str for k in ("PGT", "TGT", "LECTURER")):
                errors.append({
                    "row_number": row_number,
                    "teacher_id": teacher_id,
                    "column": "Subject",
                    "original_value": None,
                    "issue_type": "MISSING_VALUE",
                    "severity": "ERROR",
                    "message": f"Secondary/Senior Secondary teacher ({desig_str}) must have an assigned Subject.",
                    "suggested_action": "Assign core teaching discipline."
                })
            else:
                errors.append({
                    "row_number": row_number,
                    "teacher_id": teacher_id,
                    "column": "Subject",
                    "original_value": None,
                    "issue_type": "MISSING_VALUE",
                    "severity": "WARNING",
                    "message": "Subject is blank. Defaults to General for Primary cadres.",
                    "suggested_action": "Review if teacher has specialized subject duties."
                })

        # 6. Experience Years Validation
        exp_val = row.get("Experience_Years")
        if is_null_or_empty(exp_val):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "Experience_Years",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "WARNING",
                "message": "Years of experience is not specified.",
                "suggested_action": "Compute from date of first appointment."
            })
        else:
            _, is_valid_exp, exp_reason = validate_experience(exp_val)
            if not is_valid_exp:
                errors.append({
                    "row_number": row_number,
                    "teacher_id": teacher_id,
                    "column": "Experience_Years",
                    "original_value": str(exp_val),
                    "issue_type": "OUT_OF_RANGE",
                    "severity": "ERROR",
                    "message": exp_reason or "Invalid experience value.",
                    "suggested_action": "Verify service book records for accurate tenure."
                })

        # 7. Contact Number Validation
        contact_val = row.get("Contact_Number")
        if is_null_or_empty(contact_val):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "Contact_Number",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "WARNING",
                "message": "Contact mobile number is missing.",
                "suggested_action": "Collect updated 10-digit mobile number for communication."
            })
        else:
            _, is_valid_phone = clean_phone_number(contact_val)
            if not is_valid_phone:
                errors.append({
                    "row_number": row_number,
                    "teacher_id": teacher_id,
                    "column": "Contact_Number",
                    "original_value": str(contact_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Contact number '{contact_val}' is not a valid 10-digit Indian mobile number.",
                    "suggested_action": "Enter a valid 10-digit mobile number starting with 6, 7, 8, or 9."
                })

        # 8. Email Address Validation
        email_val = row.get("Email_Address")
        if is_null_or_empty(email_val):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "Email_Address",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "WARNING",
                "message": "Official/personal email address is missing.",
                "suggested_action": "Register valid email address for administrative notices."
            })
        else:
            _, is_valid_email = validate_email_address(email_val)
            if not is_valid_email:
                errors.append({
                    "row_number": row_number,
                    "teacher_id": teacher_id,
                    "column": "Email_Address",
                    "original_value": str(email_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": f"Email address '{email_val}' does not comply with standard email format.",
                    "suggested_action": "Correct syntax to user@domain.com."
                })

        # 9. Date of Birth Validation
        dob_val = row.get("Date_of_Birth")
        if not is_null_or_empty(dob_val):
            _, is_valid_dob, dob_reason = parse_date_of_birth(dob_val)
            if not is_valid_dob:
                errors.append({
                    "row_number": row_number,
                    "teacher_id": teacher_id,
                    "column": "Date_of_Birth",
                    "original_value": str(dob_val),
                    "issue_type": "OUT_OF_RANGE" if "outside" in (dob_reason or "") else "INVALID_FORMAT",
                    "severity": "ERROR",
                    "message": dob_reason or "Date of birth invalid.",
                    "suggested_action": "Check matriculation certificate for verified date of birth."
                })

        # 10. School UDISE Code Validation
        udise_val = row.get("School_Code")
        if not is_null_or_empty(udise_val):
            _, is_valid_udise, udise_reason = validate_school_code(udise_val)
            if not is_valid_udise:
                errors.append({
                    "row_number": row_number,
                    "teacher_id": teacher_id,
                    "column": "School_Code",
                    "original_value": str(udise_val),
                    "issue_type": "INVALID_FORMAT",
                    "severity": "WARNING",
                    "message": udise_reason or "Invalid UDISE code.",
                    "suggested_action": "Cross-verify school code with Haryana UDISE+ directory."
                })

        # 11. Qualification Validation
        qual_val = row.get("Qualification")
        if is_null_or_empty(qual_val):
            errors.append({
                "row_number": row_number,
                "teacher_id": teacher_id,
                "column": "Qualification",
                "original_value": None,
                "issue_type": "MISSING_VALUE",
                "severity": "WARNING",
                "message": "Academic/Professional qualification is missing.",
                "suggested_action": "Record highest professional educational credential."
            })

        return errors
