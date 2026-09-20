import re
from typing import Any, Dict, Tuple, Optional, List
from app.utils.helpers import is_null_or_empty

# Official 22 districts of Haryana
HARYANA_DISTRICTS = [
    "Ambala", "Bhiwani", "Charkhi Dadri", "Faridabad", "Fatehabad",
    "Gurugram", "Hisar", "Jhajjar", "Jind", "Kaithal", "Karnal",
    "Kurukshetra", "Mahendragarh", "Nuh", "Palwal", "Panchkula",
    "Panipat", "Rewari", "Rohtak", "Sirsa", "Sonipat", "Yamunanagar"
]

DISTRICT_MAPPING = {
    "ambala": "Ambala",
    "ambala cantt": "Ambala",
    "ambala city": "Ambala",
    "bhiwani": "Bhiwani",
    "charkhi dadri": "Charkhi Dadri",
    "ch. dadri": "Charkhi Dadri",
    "dadri": "Charkhi Dadri",
    "faridabad": "Faridabad",
    "fatehabad": "Fatehabad",
    "fatehbad": "Fatehabad",
    "gurugram": "Gurugram",
    "gurgaon": "Gurugram",
    "hisar": "Hisar",
    "hissar": "Hisar",
    "jhajjar": "Jhajjar",
    "jind": "Jind",
    "kaithal": "Kaithal",
    "karnal": "Karnal",
    "kurukshetra": "Kurukshetra",
    "kkr": "Kurukshetra",
    "mahendragarh": "Mahendragarh",
    "mohindergarh": "Mahendragarh",
    "narnaul": "Mahendragarh",
    "mgarh": "Mahendragarh",
    "nuh": "Nuh",
    "mewat": "Nuh",
    "palwal": "Palwal",
    "panchkula": "Panchkula",
    "panipat": "Panipat",
    "rewari": "Rewari",
    "rohtak": "Rohtak",
    "sirsa": "Sirsa",
    "sonipat": "Sonipat",
    "sonepat": "Sonipat",
    "yamunanagar": "Yamunanagar",
    "yamuna nagar": "Yamunanagar",
    "ynr": "Yamunanagar"
}

SUBJECT_MAPPING = {
    # Mathematics
    "math": "Mathematics",
    "maths": "Mathematics",
    "mathmatics": "Mathematics",
    "mathematics": "Mathematics",
    "applied math": "Mathematics",
    "mth": "Mathematics",
    # Science
    "sci": "Science",
    "science": "Science",
    "gen science": "Science",
    "general science": "Science",
    "gen. sci": "Science",
    # English
    "eng": "English",
    "english": "English",
    "eng.": "English",
    # Hindi
    "hindi": "Hindi",
    "hnd": "Hindi",
    "hindi lit": "Hindi",
    "hindi literature": "Hindi",
    # Sanskrit
    "skt": "Sanskrit",
    "sanskrit": "Sanskrit",
    "sans": "Sanskrit",
    # Social Science / Studies
    "sst": "Social Science",
    "s.st": "Social Science",
    "s.st.": "Social Science",
    "social science": "Social Science",
    "social studies": "Social Science",
    "social study": "Social Science",
    # Physics
    "phy": "Physics",
    "physics": "Physics",
    # Chemistry
    "chem": "Chemistry",
    "chemistry": "Chemistry",
    # Biology
    "bio": "Biology",
    "biology": "Biology",
    "life science": "Biology",
    # Computer Science
    "cs": "Computer Science",
    "comp sci": "Computer Science",
    "computer": "Computer Science",
    "computer science": "Computer Science",
    "it": "Computer Science",
    "info tech": "Computer Science",
    "information technology": "Computer Science",
    # Commerce
    "comm": "Commerce",
    "commerce": "Commerce",
    # Economics
    "eco": "Economics",
    "economics": "Economics",
    # Geography
    "geo": "Geography",
    "geog": "Geography",
    "geography": "Geography",
    # History
    "hist": "History",
    "history": "History",
    # Political Science
    "pol sci": "Political Science",
    "pol. sci": "Political Science",
    "pol science": "Political Science",
    "political science": "Political Science",
    "civics": "Political Science",
    # Physical Education
    "phy edu": "Physical Education",
    "physical edu": "Physical Education",
    "physical education": "Physical Education",
    "pet": "Physical Education",
    "dpe": "Physical Education",
    # Fine Arts
    "fine arts": "Fine Arts",
    "fine art": "Fine Arts",
    "art": "Fine Arts",
    "drawing": "Fine Arts",
    # Music
    "music": "Music",
    # Punjabi
    "punjabi": "Punjabi",
    "pun": "Punjabi",
    # Urdu
    "urdu": "Urdu",
    # General PRT
    "general": "General (All Subjects)",
    "all": "General (All Subjects)",
    "all subjects": "General (All Subjects)",
    "prt general": "General (All Subjects)"
}

QUALIFICATION_MAPPING = {
    # Elementary Education / JBT
    "jbt": "D.El.Ed / JBT",
    "d.el.ed": "D.El.Ed / JBT",
    "deled": "D.El.Ed / JBT",
    "d.ed": "D.El.Ed / JBT",
    "ded": "D.El.Ed / JBT",
    "diploma in elementary education": "D.El.Ed / JBT",
    "j.b.t.": "D.El.Ed / JBT",
    # B.Ed
    "b.ed": "B.Ed",
    "bed": "B.Ed",
    "b. ed": "B.Ed",
    "bachelor of education": "B.Ed",
    # M.Ed
    "m.ed": "M.Ed",
    "med": "M.Ed",
    "m. ed": "M.Ed",
    "master of education": "M.Ed",
    # B.Sc
    "b.sc": "B.Sc",
    "bsc": "B.Sc",
    "b. sc": "B.Sc",
    "bachelor of science": "B.Sc",
    "b.sc non medical": "B.Sc (Non-Medical)",
    "bsc non medical": "B.Sc (Non-Medical)",
    "bsc nm": "B.Sc (Non-Medical)",
    "b.sc medical": "B.Sc (Medical)",
    "bsc medical": "B.Sc (Medical)",
    # M.Sc
    "m.sc": "M.Sc",
    "msc": "M.Sc",
    "m. sc": "M.Sc",
    "master of science": "M.Sc",
    "msc maths": "M.Sc Mathematics",
    "m.sc maths": "M.Sc Mathematics",
    "msc mathematics": "M.Sc Mathematics",
    "m.sc. mathematics": "M.Sc Mathematics",
    "msc physics": "M.Sc Physics",
    "msc chemistry": "M.Sc Chemistry",
    "msc bio": "M.Sc Biology",
    "msc cs": "M.Sc Computer Science",
    # B.A
    "b.a": "B.A",
    "ba": "B.A",
    "b. a": "B.A",
    "bachelor of arts": "B.A",
    # M.A
    "m.a": "M.A",
    "ma": "M.A",
    "m. a": "M.A",
    "master of arts": "M.A",
    "ma english": "M.A English",
    "ma hindi": "M.A Hindi",
    "ma sst": "M.A Social Science",
    "ma history": "M.A History",
    "ma pol sci": "M.A Political Science",
    "ma economics": "M.A Economics",
    # B.Com / M.Com
    "b.com": "B.Com",
    "bcom": "B.Com",
    "b. com": "B.Com",
    "m.com": "M.Com",
    "mcom": "M.Com",
    "m. com": "M.Com",
    # IT / Computer
    "bca": "BCA",
    "b.c.a": "BCA",
    "mca": "MCA",
    "m.c.a": "MCA",
    "b.tech": "B.Tech",
    "btech": "B.Tech",
    "m.tech": "M.Tech",
    "mtech": "M.Tech",
    # Higher
    "ph.d": "Ph.D",
    "phd": "Ph.D",
    "doctorate": "Ph.D",
    "ph.d.": "Ph.D"
}

DESIGNATION_MAPPING = {
    "prt": "PRT",
    "primary teacher": "PRT",
    "p.r.t.": "PRT",
    "p.r.t": "PRT",
    "jbt teacher": "PRT",
    "tgt": "TGT",
    "trained graduate teacher": "TGT",
    "t.g.t.": "TGT",
    "t.g.t": "TGT",
    "pgt": "PGT",
    "post graduate teacher": "PGT",
    "p.g.t.": "PGT",
    "p.g.t": "PGT",
    "lecturer": "PGT",
    "school lecturer": "PGT",
    "headmaster": "Headmaster",
    "head master": "Headmaster",
    "head mistress": "Headmaster",
    "hm": "Headmaster",
    "h.m.": "Headmaster",
    "principal": "Principal",
    "prin.": "Principal"
}

EMPLOYMENT_STATUS_MAPPING = {
    "regular": "Regular",
    "permanent": "Regular",
    "govt regular": "Regular",
    "guest": "Guest",
    "guest teacher": "Guest",
    "atithi adhyapak": "Guest",
    "contract": "Contractual (HKRN)",
    "contractual": "Contractual (HKRN)",
    "hkrn": "Contractual (HKRN)",
    "haryana kaushal rozgar nigam": "Contractual (HKRN)",
    "temporary": "Contractual (HKRN)"
}

GENDER_MAPPING = {
    "m": "Male",
    "male": "Male",
    "f": "Female",
    "female": "Female",
    "o": "Other",
    "other": "Other",
    "transgender": "Other"
}

class StandardizationService:
    @staticmethod
    def clean_text_whitespace(val: Any) -> Optional[str]:
        """Trims leading/trailing whitespace and collapses multiple interior spaces."""
        if is_null_or_empty(val):
            return None
        return re.sub(r"\s+", " ", str(val)).strip()

    @staticmethod
    def standardize_subject(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes subject value against canonical Haryana curriculum taxonomy.
        Returns (standardized_val, rule_name)."""
        if is_null_or_empty(val):
            return None, None
        
        cleaned = StandardizationService.clean_text_whitespace(val)
        lowered = cleaned.lower()
        
        # Direct lookup
        if lowered in SUBJECT_MAPPING:
            std = SUBJECT_MAPPING[lowered]
            return std, "Taxonomy Lookup" if std != cleaned else None
            
        # Pattern checks
        if "math" in lowered:
            return "Mathematics", "Keyword Matching (Math)"
        if "sci" in lowered and "soc" not in lowered:
            return "Science", "Keyword Matching (Science)"
        if "comp" in lowered or "it" == lowered or "infor" in lowered:
            return "Computer Science", "Keyword Matching (Computer)"
            
        # Title case default if unrecognized
        return cleaned.title(), "Title Case Normalization"

    @staticmethod
    def standardize_qualification(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes academic qualifications.
        Returns (standardized_val, rule_name)."""
        if is_null_or_empty(val):
            return None, None
            
        cleaned = StandardizationService.clean_text_whitespace(val)
        lowered = cleaned.lower()
        
        if lowered in QUALIFICATION_MAPPING:
            std = QUALIFICATION_MAPPING[lowered]
            return std, "Taxonomy Lookup" if std != cleaned else None
            
        # Common prefix checks
        if lowered.startswith("m.sc") or lowered.startswith("msc"):
            parts = cleaned.split(maxsplit=1)
            subject = parts[1] if len(parts) > 1 else ""
            return f"M.Sc {subject}".strip(), "Degree Prefix Normalization"
        if lowered.startswith("m.a") or lowered.startswith("ma "):
            parts = cleaned.split(maxsplit=1)
            subject = parts[1] if len(parts) > 1 else ""
            return f"M.A {subject}".strip(), "Degree Prefix Normalization"
            
        return cleaned, None

    @staticmethod
    def standardize_district(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes district to one of 22 official Haryana districts."""
        if is_null_or_empty(val):
            return None, None
            
        cleaned = StandardizationService.clean_text_whitespace(val)
        lowered = cleaned.lower()
        
        if lowered in DISTRICT_MAPPING:
            std = DISTRICT_MAPPING[lowered]
            return std, "District Canonical Mapping" if std != cleaned else None
            
        return cleaned.title(), "District Title Case"

    @staticmethod
    def standardize_designation(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes teacher cadre/designation (PRT, TGT, PGT, Headmaster, Principal)."""
        if is_null_or_empty(val):
            return None, None
            
        cleaned = StandardizationService.clean_text_whitespace(val)
        lowered = cleaned.lower()
        
        if lowered in DESIGNATION_MAPPING:
            std = DESIGNATION_MAPPING[lowered]
            return std, "Cadre Canonical Mapping" if std != cleaned else None
            
        return cleaned.upper(), "Cadre Uppercase"

    @staticmethod
    def standardize_employment_status(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes employment status (Regular, Guest, Contractual (HKRN))."""
        if is_null_or_empty(val):
            return None, None
            
        cleaned = StandardizationService.clean_text_whitespace(val)
        lowered = cleaned.lower()
        
        if lowered in EMPLOYMENT_STATUS_MAPPING:
            std = EMPLOYMENT_STATUS_MAPPING[lowered]
            return std, "Status Canonical Mapping" if std != cleaned else None
            
        return cleaned.title(), "Status Title Case"

    @staticmethod
    def standardize_gender(val: Any) -> Tuple[Optional[str], Optional[str]]:
        """Standardizes gender (Male, Female, Other)."""
        if is_null_or_empty(val):
            return None, None
            
        cleaned = StandardizationService.clean_text_whitespace(val)
        lowered = cleaned.lower()
        
        if lowered in GENDER_MAPPING:
            std = GENDER_MAPPING[lowered]
            return std, "Gender Normalization" if std != cleaned else None
            
        return cleaned.title(), "Gender Title Case"
