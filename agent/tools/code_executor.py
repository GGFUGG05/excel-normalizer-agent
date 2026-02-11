"""Tool: Execute a generated Python transformation script in a subprocess."""

from __future__ import annotations

import os
import sys
import subprocess
import tempfile
import json
from pathlib import Path
from langchain_core.tools import tool

from config import EXECUTION_TIMEOUT


@tool
def execute_transform_code(code: str, input_file: str, output_file: str) -> str:
    """Execute a Python transformation script against an input Excel file.

    The code should read from the input_file path, perform transformations,
    and write the result to the output_file path. The code must be a
    standalone Python script using pandas/openpyxl.

    Args:
        code: The complete Python script to execute.
        input_file: Path to the raw input Excel file.
        output_file: Path where the transformed output should be written.

    Returns:
        JSON string with execution result: success/failure, stdout, stderr,
        and first few rows of output if successful.
    """
    # Write the code to a temp file (use system default temp dir for cross-platform compat)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(code)
        script_path = f.name

    try:
        # Inherit the full environment so the subprocess can find all
        # installed packages (venv, conda, pyenv, etc.), then inject
        # the input/output paths for the generated script.
        env = os.environ.copy()
        env["INPUT_FILE"] = input_file
        env["OUTPUT_FILE"] = output_file

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT,
            env=env,
        )

        output = {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[:3000] if result.stdout else "",
            "stderr": result.stderr[:3000] if result.stderr else "",
        }

        # If successful, try to read a preview of the output
        if result.returncode == 0 and Path(output_file).exists():
            try:
                import pandas as pd
                df = pd.read_excel(output_file)
                output["output_preview"] = df.head(10).to_string()
                output["output_shape"] = list(df.shape)
                output["output_columns"] = list(df.columns)
            except Exception as e:
                output["output_preview_error"] = str(e)

        return json.dumps(output, indent=2, ensure_ascii=False)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "error": f"Script timed out after {EXECUTION_TIMEOUT} seconds",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        })
    finally:
        Path(script_path).unlink(missing_ok=True)
