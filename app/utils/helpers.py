import re
import math
from typing import Optional, Tuple, Any
from datetime import datetime

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^\d{10}$")

COLUMN_ALIAS_MAP = {
    # Teacher ID aliases
    "teacher_id": "Teacher_ID",
    "teacher id": "Teacher_ID",
    "teacherid": "Teacher_ID",
    "emp_id": "Teacher_ID",
    "employee_id": "Teacher_ID",
    "id": "Teacher_ID",
    # Teacher Name aliases
    "teacher_name": "Teacher_Name",
    "teacher name": "Teacher_Name",
    "name": "Teacher_Name",
    "employee_name": "Teacher_Name",
    "full_name": "Teacher_Name",
    # Gender
    "gender": "Gender",
    "sex": "Gender",
    # Date of birth
    "date_of_birth": "Date_of_Birth",
    "dob": "Date_of_Birth",
    "birth_date": "Date_of_Birth",
    # Designation
    "designation": "Designation",
    "post": "Designation",
    "cadre": "Designation",
    "role": "Designation",
    # Subject
    "subject": "Subject",
    "teaching_subject": "Subject",
    "sub": "Subject",
    # Qualification
    "qualification": "Qualification",
    "highest_qualification": "Qualification",
    "education": "Qualification",
    # Experience
    "experience_years": "Experience_Years",
    "experience": "Experience_Years",
    "exp_years": "Experience_Years",
    "exp": "Experience_Years",
    "years_of_experience": "Experience_Years",
    # School Code
    "school_code": "School_Code",
    "udise": "School_Code",
    "udise_code": "School_Code",
    "school_id": "School_Code",
    # School Name
    "school_name": "School_Name",
    "school": "School_Name",
    # District
    "district": "District",
    "dist": "District",
    # Block
    "block": "Block",
    "educational_block": "Block",
    # Contact Number
    "contact_number": "Contact_Number",
    "phone": "Contact_Number",
    "mobile": "Contact_Number",
    "phone_number": "Contact_Number",
    "contact": "Contact_Number",
    # Email
    "email_address": "Email_Address",
    "email": "Email_Address",
    "mail": "Email_Address",
    # Employment Status
    "employment_status": "Employment_Status",
    "status": "Employment_Status",
    "emp_status": "Employment_Status",
    "type": "Employment_Status"
}

STANDARD_COLUMNS = [
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
    "Employment_Status"
]

CRITICAL_COLUMNS = [
    "Teacher_ID",
    "Teacher_Name",
    "Designation",
    "District"
]

# Explicit schema / data type map: Force string loading for identifier fields & text columns
SCHEMA_DTYPE_MAP = {
    # Standard columns
    "Teacher_ID": str,
    "Teacher_Name": str,
    "Gender": str,
    "Date_of_Birth": str,
    "Designation": str,
    "Subject": str,
    "Qualification": str,
    "Experience_Years": object,
    "School_Code": str,
    "School_Name": str,
    "District": str,
    "Block": str,
    "Contact_Number": str,
    "Email_Address": str,
    "Employment_Status": str,
}
for _raw_alias, _std_col in COLUMN_ALIAS_MAP.items():
    if _std_col == "Experience_Years":
        SCHEMA_DTYPE_MAP[_raw_alias] = object
    else:
        SCHEMA_DTYPE_MAP[_raw_alias] = str

def is_null_or_empty(val: Any) -> bool:
    """Checks whether a value is effectively null, empty, or placeholder."""
    if val is None:
        return True
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    s = str(val).strip()
    if s == "" or s.lower() in ("nan", "none", "null", "n/a", "na", "-", "--", "nil", "undefined"):
        return True
    return False

def safe_str(val: Any) -> Optional[str]:
    """Converts any cell value to a safe string, stripping whitespace and avoiding float .0 artifacts."""
    if is_null_or_empty(val):
        return None
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        s = str(val).strip()
        if s.endswith(".0"):
            return s[:-2]
        return s
    if isinstance(val, int):
        return str(val)
    s = str(val).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s

def normalize_column_name(raw_name: str) -> str:
    """Normalizes raw column header to standard column name using alias dictionary."""
    cleaned = str(raw_name).strip().lower().replace("-", "_").replace(" ", "_")
    return COLUMN_ALIAS_MAP.get(cleaned, str(raw_name).strip())

def sanitize_filename(filename: str) -> str:
    """Sanitizes filename against path traversal and special characters."""
    filename = re.sub(r"[^\w\s\.-]", "", filename)
    filename = filename.strip().replace(" ", "_")
    return filename or "uploaded_file"

def clean_phone_number(val: Any) -> Tuple[Optional[str], bool]:
    """Cleans phone numbers to 10 digits.
    Returns (cleaned_phone, is_valid)."""
    if is_null_or_empty(val):
        return None, True  # Handled as missing, not format error
    
    raw = safe_str(val)
    if not raw:
        return None, True
    # Strip common scientific notation, e.g., 9.87654E+09
    if "e+" in raw.lower():
        try:
            raw = str(int(float(raw)))
        except ValueError:
            pass

    digits = re.sub(r"\D", "", raw)
    # Remove leading country code +91 or 91 if 12 digits, or 0091 if 14 digits
    if digits.startswith("0091") and len(digits) == 14:
        digits = digits[4:]
    elif digits.startswith("910") and len(digits) == 13:
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
        
    if len(digits) == 10 and digits[0] in "6789":
        return digits, True
    return raw, False

def validate_email_address(val: Any) -> Tuple[Optional[str], bool]:
    """Validates email format.
    Returns (cleaned_email, is_valid)."""
    if is_null_or_empty(val):
        return None, True  # Missing, not format error
    s = str(val).strip()
    if EMAIL_REGEX.match(s):
        parts = s.split("@")
        if len(parts) == 2:
            domain = parts[1]
            if not domain.startswith("-") and not domain.endswith("-") and not domain.endswith("."):
                return s.lower(), True
    return s, False

def validate_experience(val: Any) -> Tuple[Optional[float], bool, Optional[str]]:
    """Validates experience years. Valid range: [0, 45].
    Returns (parsed_value, is_valid, error_reason)."""
    if is_null_or_empty(val):
        return None, True, None
    try:
        exp = float(val)
        if exp < 0:
            return exp, False, f"Negative experience years ({exp}) is invalid"
        if exp > 45:
            return exp, False, f"Experience ({exp} yrs) exceeds realistic threshold (max 45 yrs)"
        return round(exp, 1), True, None
    except (ValueError, TypeError):
        return None, False, f"Value '{val}' is not a valid numeric experience"

def parse_date_of_birth(val: Any) -> Tuple[Optional[str], bool, Optional[str]]:
    """Normalizes date of birth to YYYY-MM-DD.
    Validates teacher age between 18 and 65 years."""
    if is_null_or_empty(val):
        return None, True, None
    s = str(val).strip()
    parsed_date = None
    if isinstance(val, datetime):
        parsed_date = val
    else:
        for fmt in (
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%d.%m.%Y",
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y",
            "%d-%m-%y",
            "%d/%m/%y"
        ):
            try:
                parsed_date = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
            
    if parsed_date is None:
        return s, False, f"Date '{s}' could not be parsed to a standard date format"
    
    today = datetime.now()
    age = today.year - parsed_date.year - ((today.month, today.day) < (parsed_date.month, parsed_date.day))
    if age < 18 or age > 65:
        return parsed_date.strftime("%Y-%m-%d"), False, f"Calculated age ({age} yrs) outside realistic teacher range (18-65)"
        
    return parsed_date.strftime("%Y-%m-%d"), True, None

def validate_school_code(val: Any) -> Tuple[Optional[str], bool, Optional[str]]:
    """Validates school code (Canonical Haryana UDISE: 11 digits starting with '06').
    Returns (standardized_code, is_valid, reason)."""
    if is_null_or_empty(val):
        return None, True, None
    s = safe_str(val)
    if not s:
        return None, True, None
    cleaned = re.sub(r"[\s\.-]", "", s)
    if not cleaned.isdigit():
        return s, False, f"School_Code '{val}' contains non-numeric characters"
    if len(cleaned) == 11:
        if cleaned.startswith("06"):
            return cleaned, True, None
        return s, False, f"School_Code '{val}' is 11 digits but does not begin with Haryana state prefix '06'"
    elif len(cleaned) == 10:
        if cleaned.startswith("6"):
            # Missing leading zero due to numeric export
            std = "0" + cleaned
            return std, True, None
        return s, False, f"School_Code '{val}' is 10 digits but cannot be safely normalized to Haryana '06' prefix"
    else:
        return s, False, f"UDISE code '{val}' must be 11 digits starting with '06' (got {len(cleaned)} digits)"
