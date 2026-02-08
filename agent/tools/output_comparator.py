"""Tool: Compare the actual transformation output with the expected example."""

from __future__ import annotations

import json
import pandas as pd
from pathlib import Path
from langchain_core.tools import tool


@tool
def compare_outputs(actual_file: str, expected_file: str) -> str:
    """Compare actual transformation output with the expected example output.

    Checks column names, data types, row counts, and sample values.

    Args:
        actual_file: Path to the file produced by the transformation script.
        expected_file: Path to the user-provided example output file.

    Returns:
        JSON string with comparison results: matched/missing/extra columns,
        row counts, dtype mismatches, and a sample comparison.
    """
    result = {
        "success": False,
        "matched_columns": [],
        "missing_columns": [],
        "extra_columns": [],
        "row_count_expected": None,
        "row_count_actual": None,
        "dtype_mismatches": [],
        "sample_comparison": "",
        "error_message": "",
    }

    if not Path(actual_file).exists():
        result["error_message"] = f"Actual output file not found: {actual_file}"
        return json.dumps(result, indent=2)

    if not Path(expected_file).exists():
        result["error_message"] = f"Expected output file not found: {expected_file}"
        return json.dumps(result, indent=2)

    try:
        df_actual = pd.read_excel(actual_file, dtype=str)
        df_expected = pd.read_excel(expected_file, dtype=str)
    except Exception as e:
        result["error_message"] = f"Error reading files: {e}"
        return json.dumps(result, indent=2)

    # Column comparison (case-insensitive, stripped)
    actual_cols = {c.strip().lower(): c for c in df_actual.columns}
    expected_cols = {c.strip().lower(): c for c in df_expected.columns}

    matched = []
    for key in expected_cols:
        if key in actual_cols:
            matched.append(expected_cols[key])
    missing = [expected_cols[k] for k in expected_cols if k not in actual_cols]
    extra = [actual_cols[k] for k in actual_cols if k not in expected_cols]

    result["matched_columns"] = matched
    result["missing_columns"] = missing
    result["extra_columns"] = extra
    result["row_count_expected"] = len(df_expected)
    result["row_count_actual"] = len(df_actual)

    # Sample comparison – show first 5 rows side by side for matched columns
    comparison_lines = []
    common_cols_expected = [c for c in df_expected.columns if c.strip().lower() in actual_cols]
    common_cols_actual = [actual_cols[c.strip().lower()] for c in common_cols_expected]

    if common_cols_expected:
        for i in range(min(5, len(df_expected), len(df_actual))):
            row_exp = {c: str(df_expected[c].iloc[i]) for c in common_cols_expected}
            row_act = {c: str(df_actual[actual_cols[c.strip().lower()]].iloc[i]) for c in common_cols_expected}
            mismatches = []
            for c in common_cols_expected:
                v_exp = row_exp[c].strip()
                v_act = row_act[c].strip()
                if v_exp != v_act:
                    mismatches.append(f"  {c}: expected='{v_exp}' actual='{v_act}'")
            if mismatches:
                comparison_lines.append(f"Row {i}: MISMATCH\n" + "\n".join(mismatches))
            else:
                comparison_lines.append(f"Row {i}: OK")

    result["sample_comparison"] = "\n".join(comparison_lines) if comparison_lines else "No common columns to compare"
    result["success"] = len(missing) == 0 and len(comparison_lines) > 0

    return json.dumps(result, indent=2, ensure_ascii=False)
