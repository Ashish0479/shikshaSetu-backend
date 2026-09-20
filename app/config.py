import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Teacher Data Quality & Standardization System"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    
    # MongoDB Configuration
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "shikshasetu_quality_db")
    MONGODB_TIMEOUT_MS: int = int(os.getenv("MONGODB_TIMEOUT_MS", "3000"))
    
    # Upload and Processing limits
    MAX_FILE_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB
    ALLOWED_EXTENSIONS: List[str] = [".csv", ".xlsx", ".xls"]
    
    # CORS Origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
    ]
    
    # Quality Scoring Weights (Transparent formula: Completeness 30%, Validity 30%, Consistency 20%, Uniqueness 20%)
    WEIGHT_COMPLETENESS: float = 0.30
    WEIGHT_VALIDITY: float = 0.30
    WEIGHT_CONSISTENCY: float = 0.20
    WEIGHT_UNIQUENESS: float = 0.20

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"

settings = Settings()
