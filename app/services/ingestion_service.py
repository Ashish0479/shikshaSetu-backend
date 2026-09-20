import os
import io
import pandas as pd
from typing import Tuple, Dict, Any, List
from fastapi import UploadFile, HTTPException
from app.config import settings
from app.utils.helpers import sanitize_filename, normalize_column_name, STANDARD_COLUMNS, CRITICAL_COLUMNS

class IngestionService:
    @staticmethod
    async def read_uploaded_file(file: UploadFile) -> Tuple[pd.DataFrame, str, int, Dict[str, str]]:
        """Validates and parses uploaded CSV or Excel file into a Pandas DataFrame.
        Returns:
            (dataframe, sanitized_filename, file_size_bytes, column_renaming_map)
        """
        original_filename = file.filename or "unknown_file"
        sanitized_name = sanitize_filename(original_filename)
        ext = os.path.splitext(sanitized_name)[1].lower()

        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

        contents = await file.read()
        file_size = len(contents)

        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty (0 bytes). Please upload a valid CSV or Excel file."
            )

        if file_size > settings.MAX_FILE_SIZE_BYTES:
            max_mb = settings.MAX_FILE_SIZE_BYTES / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum threshold of {max_mb:.0f} MB."
            )

        df: pd.DataFrame
        try:
            if ext == ".csv":
                # Handle potential encoding variations
                for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                    try:
                        df = pd.read_csv(io.BytesIO(contents), encoding=encoding, dtype=str)
                        break
                    except (UnicodeDecodeError, pd.errors.ParserError):
                        continue
                else:
                    raise HTTPException(
                        status_code=422,
                        detail="Failed to decode CSV file. The file may be corrupt or have an unsupported encoding."
                    )
            else:
                # Excel .xlsx or .xls
                try:
                    df = pd.read_excel(io.BytesIO(contents), dtype=str, engine="openpyxl" if ext == ".xlsx" else None)
                except Exception as ex:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Corrupted or invalid Excel spreadsheet: {str(ex)}"
                    )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to read file: {str(e)}"
            )

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file contains no data rows."
            )

        # Normalize column headers
        column_map = {}
        for col in df.columns:
            normalized = normalize_column_name(col)
            column_map[col] = normalized

        df = df.rename(columns=column_map)

        # Verify critical columns
        missing_critical = [col for col in CRITICAL_COLUMNS if col not in df.columns]
        if missing_critical:
            raise HTTPException(
                status_code=422,
                detail=f"Missing mandatory columns: {', '.join(missing_critical)}. "
                       f"Expected headers matching: {', '.join(CRITICAL_COLUMNS)}"
            )

        return df, sanitized_name, file_size, column_map
