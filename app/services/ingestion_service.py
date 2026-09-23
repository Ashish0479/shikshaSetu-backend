import os
import io
import pandas as pd
from typing import Tuple, Dict, Any, List, Optional
from fastapi import UploadFile, HTTPException
from app.config import settings
from app.utils.helpers import sanitize_filename, normalize_column_name, STANDARD_COLUMNS, CRITICAL_COLUMNS


class IngestionService:
    @staticmethod
    async def read_uploaded_file(file: UploadFile) -> Tuple[pd.DataFrame, str, int, Dict[str, str]]:
        """Backward-compatible single-file reader for teacher datasets.
        Validates presence of critical teacher columns.
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

        df = IngestionService._parse_bytes_to_dataframe(contents, ext)

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

        # Verify critical teacher columns (backward-compatible check)
        missing_critical = [col for col in CRITICAL_COLUMNS if col not in df.columns]
        if missing_critical:
            raise HTTPException(
                status_code=422,
                detail=f"Missing mandatory columns: {', '.join(missing_critical)}. "
                       f"Expected headers matching: {', '.join(CRITICAL_COLUMNS)}"
            )

        return df, sanitized_name, file_size, column_map

    @classmethod
    def _parse_bytes_to_dataframe(cls, contents: bytes, ext: str) -> pd.DataFrame:
        """Parses byte content of CSV or Excel to a Pandas DataFrame."""
        if ext == ".csv":
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    return pd.read_csv(io.BytesIO(contents), encoding=encoding, dtype=str)
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            raise HTTPException(
                status_code=422,
                detail="Failed to decode CSV file. The file may be corrupt or have an unsupported encoding."
            )
        else:
            try:
                return pd.read_excel(io.BytesIO(contents), dtype=str, engine="openpyxl" if ext == ".xlsx" else None)
            except Exception as ex:
                raise HTTPException(
                    status_code=422,
                    detail=f"Corrupted or invalid Excel spreadsheet: {str(ex)}"
                )

    @classmethod
    async def read_any_uploaded_file(cls, file: UploadFile) -> Tuple[Dict[str, pd.DataFrame], str, int]:
        """Parses a CSV or Excel file into one or more DataFrames without enforcing teacher schema.
        If Excel workbook has multiple sheets, each sheet is returned as a separate DataFrame.
        Returns:
            (dict of { source_key: dataframe }, sanitized_filename, file_size_bytes)
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
                detail=f"Uploaded file '{sanitized_name}' is empty (0 bytes)."
            )

        if file_size > settings.MAX_FILE_SIZE_BYTES:
            max_mb = settings.MAX_FILE_SIZE_BYTES / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"File '{sanitized_name}' exceeds maximum threshold of {max_mb:.0f} MB."
            )

        result_dfs: Dict[str, pd.DataFrame] = {}

        if ext == ".csv":
            df = cls._parse_bytes_to_dataframe(contents, ext)
            if not df.empty:
                result_dfs[sanitized_name] = df
        else:
            # Excel - Check sheets
            try:
                excel_file = pd.ExcelFile(io.BytesIO(contents), engine="openpyxl" if ext == ".xlsx" else None)
                for sheet in excel_file.sheet_names:
                    df = pd.read_excel(excel_file, sheet_name=sheet, dtype=str)
                    if not df.empty:
                        # If single sheet, label as filename; if multiple, label as filename:sheet
                        label = f"{sanitized_name} - {sheet}" if len(excel_file.sheet_names) > 1 else sanitized_name
                        result_dfs[label] = df
            except Exception as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Failed to read sheets from Excel file '{sanitized_name}': {str(e)}"
                )

        if not result_dfs:
            raise HTTPException(
                status_code=400,
                detail=f"File '{sanitized_name}' contains no readable data rows."
            )

        return result_dfs, sanitized_name, file_size

    @classmethod
    async def read_multiple_files(cls, files: List[UploadFile]) -> Tuple[Dict[str, pd.DataFrame], str, int]:
        """Reads multiple uploaded files (CSVs and/or Excels with multiple sheets).
        Returns:
            (dict of { source_key: dataframe }, combined_filename, total_bytes)
        """
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded.")

        all_dfs: Dict[str, pd.DataFrame] = {}
        total_size = 0
        names = []

        for f in files:
            dfs, fn, size = await cls.read_any_uploaded_file(f)
            total_size += size
            names.append(fn)
            all_dfs.update(dfs)

        primary_name = ", ".join(names[:3]) + (f" (+{len(names)-3} more)" if len(names) > 3 else "")
        return all_dfs, primary_name, total_size
