"""Excel Normalizer Agent – orchestrates analysis, planning, codegen, and validation."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import yaml
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from config import MODEL_NAME, MAX_RETRIES
from agent.tools import analyze_excel
from agent.prompts import SYSTEM_PROMPT_PLAN, SYSTEM_PROMPT_CODEGEN, SYSTEM_PROMPT_REVIEW
from models import TransformPlan


def _get_model() -> ChatAnthropic:
    return ChatAnthropic(model=MODEL_NAME)


def _extract_json_from_text(text: str) -> dict | None:
    """Try to extract a JSON object from LLM text output."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Try to find JSON block in markdown fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try to find any JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _get_last_text(result: dict) -> str:
    """Extract the last text content from agent result messages."""
    messages = result.get("messages", [])
    for msg in reversed(messages):
        # Handle both dict and message objects
        if hasattr(msg, "content"):
            content = msg.content
        elif isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            continue
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"].strip()
    return ""


# ---------------------------------------------------------------------------
# Phase 1+2: Analyze files and generate plan
# ---------------------------------------------------------------------------

def generate_plan(
    raw_file: str,
    template_file: str,
    example_file: str | None,
    user_instructions: str,
) -> tuple[TransformPlan | None, str, str]:
    """
    Analyze input files and generate a transformation plan.

    Returns:
        (plan, plan_json_str, raw_llm_response)
    """
    agent = create_agent(
        model=_get_model(),
        tools=[analyze_excel],
        system_prompt=SYSTEM_PROMPT_PLAN,
    )

    # Build the user message
    parts = [
        f"I need to transform a raw Excel file into normalized tabular data.\n",
        f"**Raw input file**: `{raw_file}`",
        f"**Target template file**: `{template_file}`",
    ]
    if example_file:
        parts.append(f"**Example output file**: `{example_file}`")
    parts.append(f"\n**My instructions**:\n{user_instructions}")
    parts.append(
        "\nPlease analyze all the provided files using the analyze_excel tool, "
        "then produce the transformation plan as a JSON object."
    )

    user_msg = "\n".join(parts)
    result = agent.invoke({"messages": [HumanMessage(content=user_msg)]})
    raw_response = _get_last_text(result)

    # Parse plan from response
    plan_dict = _extract_json_from_text(raw_response)
    if plan_dict:
        try:
            plan = TransformPlan(**plan_dict)
            plan_json = plan.model_dump_json(indent=2)
            return plan, plan_json, raw_response
        except Exception as e:
            return None, "", f"Plan parsing error: {e}\n\nRaw response:\n{raw_response}"

    return None, "", f"Could not extract plan from response:\n{raw_response}"


# ---------------------------------------------------------------------------
# Phase 2b: Revise plan based on user feedback
# ---------------------------------------------------------------------------

def revise_plan(
    current_plan_json: str,
    user_feedback: str,
    raw_file: str,
    template_file: str,
    example_file: str | None,
) -> tuple[TransformPlan | None, str, str]:
    """
    Revise a transformation plan based on user feedback.

    Returns:
        (revised_plan, plan_json_str, raw_llm_response)
    """
    agent = create_agent(
        model=_get_model(),
        tools=[analyze_excel],
        system_prompt=SYSTEM_PROMPT_REVIEW,
    )

    user_msg = (
        f"Here is the current transformation plan:\n```json\n{current_plan_json}\n```\n\n"
        f"User feedback:\n{user_feedback}\n\n"
        f"Files available for re-analysis if needed:\n"
        f"- Raw: `{raw_file}`\n"
        f"- Template: `{template_file}`\n"
    )
    if example_file:
        user_msg += f"- Example output: `{example_file}`\n"
    user_msg += "\nPlease revise the plan. Return the updated JSON."

    result = agent.invoke({"messages": [HumanMessage(content=user_msg)]})
    raw_response = _get_last_text(result)

    plan_dict = _extract_json_from_text(raw_response)
    if plan_dict:
        try:
            plan = TransformPlan(**plan_dict)
            plan_json = plan.model_dump_json(indent=2)
            return plan, plan_json, raw_response
        except Exception as e:
            return None, "", f"Plan parsing error: {e}\n\nRaw response:\n{raw_response}"

    return None, "", f"Could not extract revised plan:\n{raw_response}"


# ---------------------------------------------------------------------------
# Phase 3: Generate code from plan
# ---------------------------------------------------------------------------

def generate_code(
    plan_json: str,
    raw_file: str,
    output_file: str,
) -> tuple[str, str]:
    """
    Generate a standalone Python script from a transformation plan.

    Returns:
        (code_string, raw_llm_response)
    """
    agent = create_agent(
        model=_get_model(),
        tools=[],
        system_prompt=SYSTEM_PROMPT_CODEGEN,
    )

    user_msg = (
        f"Generate a Python transformation script based on this plan:\n"
        f"```json\n{plan_json}\n```\n\n"
        f"The script should read from INPUT_FILE environment variable "
        f"and write to OUTPUT_FILE environment variable.\n"
        f"Return ONLY the Python code."
    )

    result = agent.invoke({"messages": [HumanMessage(content=user_msg)]})
    raw_response = _get_last_text(result)

    # Extract code – strip markdown fences if present
    code = raw_response
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw_response, re.DOTALL)
    if match:
        code = match.group(1)

    # Ensure it starts with an import (sanity check)
    if "import" not in code[:200]:
        code = "import os\nimport pandas as pd\n\n" + code

    return code, raw_response


# ---------------------------------------------------------------------------
# Phase 4: Validate by executing code and returning results for user review
# ---------------------------------------------------------------------------

def validate_transform(
    code: str,
    raw_file: str,
    output_file: str,
) -> dict:
    """
    Execute the generated code directly and return results for user review.

    Returns:
        {
            "success": bool,
            "output_file": str | None,
            "error": str | None,
            "stdout": str | None,
            "preview": list[dict] | None,  # first N rows for frontend display
        }
    """
    import subprocess
    import pandas as pd

    # Write code to temp file in output directory
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    code_path = output_path.parent / "_temp_transform.py"
    code_path.write_text(code)

    # Execute directly with environment variables
    env = os.environ.copy()
    env["INPUT_FILE"] = raw_file
    env["OUTPUT_FILE"] = output_file

    try:
        result = subprocess.run(
            [sys.executable, str(code_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Execution timed out after 120 seconds",
            "stdout": None,
            "output_file": None,
            "preview": None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to execute code: {e}",
            "stdout": None,
            "output_file": None,
            "preview": None,
        }

    if result.returncode != 0:
        return {
            "success": False,
            "error": result.stderr,
            "stdout": result.stdout,
            "output_file": None,
            "preview": None,
        }

    # Check if output file was created
    if not output_path.exists():
        return {
            "success": False,
            "error": "Code executed but output file was not created",
            "stdout": result.stdout,
            "output_file": None,
            "preview": None,
        }

    # Load preview for frontend display
    try:
        df = pd.read_excel(output_file)
        preview = df.head(20).to_dict(orient="records")
    except Exception as e:
        preview = None

    return {
        "success": True,
        "error": None,
        "stdout": result.stdout,
        "output_file": output_file,
        "preview": preview,
    }


# ---------------------------------------------------------------------------
# Run existing project on new files
# ---------------------------------------------------------------------------

def run_existing_transform(
    project_dir: str,
    raw_files: list[str],
    output_dir: str | None = None,
) -> list[dict]:
    """
    Execute an existing project's transform.py against one or more raw files.

    Args:
        project_dir: Path to the project directory containing transform.py
        raw_files: List of paths to raw input files
        output_dir: Override output directory (defaults to project_dir)

    Returns:
        List of result dicts (one per file), each matching validate_transform() output
        with an additional "input_file" key.
    """
    from datetime import datetime

    project_path = Path(project_dir)
    code_path = project_path / "transform.py"
    if not code_path.exists():
        return [{"success": False, "error": f"No transform.py found in {project_dir}",
                 "stdout": None, "output_file": None, "preview": None, "input_file": f}
                for f in raw_files]

    code = code_path.read_text()
    dest_dir = Path(output_dir) if output_dir else project_path

    results = []
    for raw_file in raw_files:
        stem = Path(raw_file).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = str(dest_dir / f"output_{stem}_{timestamp}.xlsx")

        result = validate_transform(code=code, raw_file=raw_file, output_file=output_file)
        result["input_file"] = raw_file
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Utility: Save outputs
# ---------------------------------------------------------------------------

def save_outputs(
    job_name: str,
    plan: TransformPlan,
    code: str,
    output_dir: str = "output",
) -> dict[str, str]:
    """Save the plan (YAML + MD) and generated code to the output directory."""
    job_dir = Path(output_dir) / job_name
    job_dir.mkdir(parents=True, exist_ok=True)

    paths = {}

    # Save plan as YAML
    yaml_path = job_dir / "transform_plan.yaml"
    plan_dict = plan.model_dump()
    with open(yaml_path, "w") as f:
        yaml.dump(plan_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    paths["plan_yaml"] = str(yaml_path)

    # Save code
    code_path = job_dir / "transform.py"
    with open(code_path, "w") as f:
        f.write(code)
    paths["code"] = str(code_path)

    # Save documentation as Markdown
    md_path = job_dir / "transform_doc.md"
    md_lines = [
        f"# Transformation Documentation: {job_name}\n",
        f"## Source Description\n{plan.source_description}\n",
        f"## Target Description\n{plan.target_description}\n",
    ]
    if plan.assumptions:
        md_lines.append("## Assumptions\n")
        for a in plan.assumptions:
            md_lines.append(f"- {a}")
        md_lines.append("")
    md_lines.append("## Transformation Steps\n")
    for step in plan.steps:
        md_lines.append(f"### Step {step.step}: {step.action}")
        md_lines.append(f"{step.description}\n")
        if step.params:
            md_lines.append(f"**Parameters:**\n```yaml\n{yaml.dump(step.params, default_flow_style=False)}```\n")
    md_lines.append(f"\n## Generated Script\nSee `transform.py` in the same directory.\n")

    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))
    paths["doc"] = str(md_path)

    return paths
