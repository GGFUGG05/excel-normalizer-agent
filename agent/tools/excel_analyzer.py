"""Tool: Analyze an Excel file and return a structured profile."""

from __future__ import annotations

import json
import pandas as pd
import numpy as np
from pathlib import Path
from langchain_core.tools import tool

from config import MAX_SAMPLE_ROWS, MAX_COLUMNS_TO_SHOW


def _safe_str(val) -> str:
    """Convert a value to string safely, handling NaN/NaT."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return str(val)


def _profile_excel(file_path: str, sheet_name: str | int = 0) -> dict:
    """
    Read an Excel file and produce a structured profile dict.
    Returns raw header rows + pandas-inferred data for the LLM.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    # --- Raw rows (no header inference) for detecting group headers ---
    df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None,
                           nrows=MAX_SAMPLE_ROWS + 5, dtype=str)
    raw_header_rows = []
    for _, row in df_raw.head(MAX_SAMPLE_ROWS + 5).iterrows():
        raw_header_rows.append([_safe_str(v) for v in row.values])

    # --- Pandas-inferred read ---
    df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=str)

    # Column info
    columns = []
    for col in df.columns[:MAX_COLUMNS_TO_SHOW]:
        non_null = int(df[col].notna().sum())
        samples = [_safe_str(v) for v in df[col].dropna().head(5).tolist()]
        columns.append({
            "name": str(col),
            "dtype": str(df[col].dtype),
            "non_null_count": non_null,
            "sample_values": samples,
        })

    # Sample rows
    sample_rows = []
    for _, row in df.head(MAX_SAMPLE_ROWS).iterrows():
        sample_rows.append({str(k): _safe_str(v) for k, v in row.items()})

    # Notes / observations
    notes = []
    # Check for mostly-empty rows (potential group headers)
    for idx, row in df_raw.head(len(df_raw)).iterrows():
        non_empty = sum(1 for v in row.values if _safe_str(v).strip())
        total = len(row.values)
        if 0 < non_empty <= 2 and total > 3:
            notes.append(
                f"Row {idx} has only {non_empty}/{total} non-empty cells – "
                f"possible group header: '{_safe_str(row.values[0])}'"
            )

    # Check for repeated patterns in first column
    first_col_vals = df_raw.iloc[:, 0].dropna().tolist()
    unique_ratio = len(set(first_col_vals)) / max(len(first_col_vals), 1)
    if unique_ratio < 0.5:
        notes.append("First column has many repeated values – possible repeating group structure")

    # Get sheet names
    xls = pd.ExcelFile(file_path)
    if len(xls.sheet_names) > 1:
        notes.append(f"Workbook has {len(xls.sheet_names)} sheets: {xls.sheet_names}")

    return {
        "file_path": str(file_path),
        "sheet_name": str(xls.sheet_names[sheet_name] if isinstance(sheet_name, int) else sheet_name),
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": columns,
        "sample_rows": sample_rows,
        "raw_header_rows": raw_header_rows,
        "notes": notes,
    }


@tool
def analyze_excel(file_path: str, sheet_name: str = "0") -> str:
    """Analyze an Excel file and return a structured profile.

    Use this tool to understand the structure of a raw input file,
    a target template, or an example output file.

    Args:
        file_path: Path to the Excel file (.xlsx, .xls, .csv).
        sheet_name: Sheet name or index (as string). Defaults to "0" (first sheet).

    Returns:
        JSON string with file profile including columns, sample rows,
        raw header rows, and structural observations.
    """
    sn: str | int = sheet_name
    try:
        sn = int(sheet_name)
    except ValueError:
        pass

    result = _profile_excel(file_path, sn)
    return json.dumps(result, indent=2, ensure_ascii=False)
