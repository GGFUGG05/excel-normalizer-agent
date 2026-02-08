"""Streamlit UI for the Excel Normalizer Agent."""
from dotenv import load_dotenv
load_dotenv()


import sys
import os
import json
import shutil
from pathlib import Path

import streamlit as st
import yaml
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import INPUT_DIR, OUTPUT_DIR
from models import TransformPlan
from agent.agent import generate_plan, revise_plan, generate_code, validate_transform, save_outputs


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Excel Normalizer Agent",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Excel Normalizer Agent")
st.caption("Upload a raw Excel file → get a documented transformation script")

# Ensure directories exist
Path(INPUT_DIR).mkdir(exist_ok=True)
Path(OUTPUT_DIR).mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
defaults = {
    "plan": None,            # TransformPlan object
    "plan_json": "",         # JSON string of the plan
    "raw_response": "",      # Raw LLM response (for debugging)
    "code": "",              # Generated Python code
    "validation_result": "", # Validation output
    "output_paths": {},      # Saved file paths
    "phase": "upload",       # upload | plan_review | codegen | done
    "raw_file_path": "",
    "template_file_path": "",
    "example_file_path": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def _save_uploaded(uploaded_file, filename: str) -> str:
    """Save an uploaded file to the input directory and return its path."""
    path = Path(INPUT_DIR) / filename
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(path)


# ---------------------------------------------------------------------------
# Sidebar: settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Anthropic API Key", type="password",
                            value=os.environ.get("ANTHROPIC_API_KEY", ""))
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    job_name = st.text_input("Job name", value="my_transform",
                             help="Used for output folder naming")

    st.divider()
    st.markdown("### How it works")
    st.markdown("""
    1. **Upload** raw file + template + example output
    2. **Describe** your transformation instructions
    3. **Review** the generated plan (edit if needed)
    4. **Generate** the Python script
    5. **Download** script + documentation
    """)

    if st.button("🔄 Reset", use_container_width=True):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()


# =====================================================================
# PHASE 1: Upload & Instructions
# =====================================================================
st.header("1. Upload Files & Instructions", divider="blue")

col1, col2, col3 = st.columns(3)

with col1:
    raw_file = st.file_uploader("📥 Raw input file", type=["xlsx", "xls", "csv"],
                                 help="The messy/formatted file to transform")
with col2:
    template_file = st.file_uploader("📋 Target template", type=["xlsx", "xls", "csv"],
                                      help="Excel file showing the target column structure")
with col3:
    example_file = st.file_uploader("📝 Example output (optional)", type=["xlsx", "xls", "csv"],
                                     help="A few rows showing expected output from the raw file")

instructions = st.text_area(
    "🔧 Transformation instructions",
    height=150,
    placeholder=(
        "Describe how the raw file should be transformed. For example:\n"
        "- The raw file has POS-level aggregated headers followed by SKU rows\n"
        "- Each POS header is a row where only column A has a value\n"
        "- Month columns (Jan-24, Feb-24, ...) should be unpivoted into rows\n"
        "- Output should have one row per SKU × outlet × month"
    ),
)

# Preview uploaded files
if raw_file:
    with st.expander("👀 Preview: Raw file"):
        try:
            df_preview = pd.read_excel(raw_file, header=None, nrows=20, dtype=str)
            st.dataframe(df_preview, use_container_width=True)
            raw_file.seek(0)  # Reset for later use
        except Exception as e:
            st.error(f"Error reading file: {e}")

if template_file:
    with st.expander("👀 Preview: Template"):
        try:
            df_preview = pd.read_excel(template_file, nrows=5, dtype=str)
            st.dataframe(df_preview, use_container_width=True)
            template_file.seek(0)
        except Exception as e:
            st.error(f"Error reading file: {e}")

if example_file:
    with st.expander("👀 Preview: Example output"):
        try:
            df_preview = pd.read_excel(example_file, nrows=10, dtype=str)
            st.dataframe(df_preview, use_container_width=True)
            example_file.seek(0)
        except Exception as e:
            st.error(f"Error reading file: {e}")


# Analyze & Plan button
can_proceed = raw_file and template_file and instructions.strip() and api_key
if st.button("🚀 Analyze & Generate Plan", disabled=not can_proceed,
             use_container_width=True, type="primary"):
    # Save files
    st.session_state.raw_file_path = _save_uploaded(raw_file, f"raw_{raw_file.name}")
    st.session_state.template_file_path = _save_uploaded(template_file, f"template_{template_file.name}")
    st.session_state.example_file_path = ""
    if example_file:
        st.session_state.example_file_path = _save_uploaded(example_file, f"example_{example_file.name}")

    with st.spinner("🔍 Analyzing files and generating transformation plan..."):
        plan, plan_json, raw_resp = generate_plan(
            raw_file=st.session_state.raw_file_path,
            template_file=st.session_state.template_file_path,
            example_file=st.session_state.example_file_path or None,
            user_instructions=instructions,
        )

    if plan:
        st.session_state.plan = plan
        st.session_state.plan_json = plan_json
        st.session_state.raw_response = raw_resp
        st.session_state.phase = "plan_review"
        st.rerun()
    else:
        st.error("Failed to generate plan. See details below.")
        st.code(raw_resp, language="text")


# =====================================================================
# PHASE 2: Plan Review
# =====================================================================
if st.session_state.phase in ("plan_review", "codegen", "done"):
    st.header("2. Review Transformation Plan", divider="green")

    plan: TransformPlan = st.session_state.plan

    if plan:
        # Display plan as readable Markdown
        st.subheader("📄 Source Understanding")
        st.info(plan.source_description)

        st.subheader("🎯 Target Understanding")
        st.info(plan.target_description)

        if plan.assumptions:
            st.subheader("⚠️ Assumptions")
            for a in plan.assumptions:
                st.warning(f"• {a}")

        st.subheader("📋 Transformation Steps")
        for step in plan.steps:
            with st.expander(f"Step {step.step}: **{step.action}**", expanded=True):
                st.markdown(step.description)
                if step.params:
                    st.code(yaml.dump(step.params, default_flow_style=False), language="yaml")

        # --- Edit options ---
        st.divider()

        edit_mode = st.toggle("✏️ Edit plan directly (YAML)", value=False)

        if edit_mode:
            edited_yaml = st.text_area(
                "Edit plan YAML",
                value=yaml.dump(plan.model_dump(), default_flow_style=False,
                                allow_unicode=True, sort_keys=False),
                height=400,
            )
            if st.button("💾 Apply YAML edits"):
                try:
                    edited_dict = yaml.safe_load(edited_yaml)
                    new_plan = TransformPlan(**edited_dict)
                    st.session_state.plan = new_plan
                    st.session_state.plan_json = new_plan.model_dump_json(indent=2)
                    st.success("Plan updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Invalid YAML: {e}")
        else:
            # Natural language feedback
            feedback = st.text_area(
                "💬 Feedback (describe what needs to change)",
                placeholder="e.g. 'Step 2 is wrong – the POS header is identified by merged cells in row, not by empty columns'",
            )
            if st.button("🔄 Revise Plan", disabled=not feedback.strip()):
                with st.spinner("Revising plan..."):
                    new_plan, new_json, raw_resp = revise_plan(
                        current_plan_json=st.session_state.plan_json,
                        user_feedback=feedback,
                        raw_file=st.session_state.raw_file_path,
                        template_file=st.session_state.template_file_path,
                        example_file=st.session_state.example_file_path or None,
                    )
                if new_plan:
                    st.session_state.plan = new_plan
                    st.session_state.plan_json = new_json
                    st.success("Plan revised!")
                    st.rerun()
                else:
                    st.error("Failed to revise plan.")
                    st.code(raw_resp, language="text")

        # Approve button
        st.divider()
        if st.button("✅ Approve Plan & Generate Code", use_container_width=True, type="primary"):
            st.session_state.phase = "codegen"
            st.rerun()

    # Debug expander
    with st.expander("🔧 Debug: Raw LLM response"):
        st.code(st.session_state.raw_response, language="text")
    with st.expander("🔧 Debug: Plan JSON"):
        st.code(st.session_state.plan_json, language="json")


# =====================================================================
# PHASE 3: Code Generation & Validation
# =====================================================================
if st.session_state.phase in ("codegen", "done") and st.session_state.plan:
    st.header("3. Generate & Validate Code", divider="orange")

    if st.session_state.phase == "codegen":
        output_file = str(Path(OUTPUT_DIR) / job_name / "output.xlsx")
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with st.spinner("🔨 Generating transformation code..."):
            code, raw_resp = generate_code(
                plan_json=st.session_state.plan_json,
                raw_file=st.session_state.raw_file_path,
                output_file=output_file,
            )
        st.session_state.code = code

        # Execute and validate
        with st.spinner("🧪 Executing transformation..."):
            validation_result = validate_transform(
                code=code,
                raw_file=st.session_state.raw_file_path,
                output_file=output_file,
            )
        st.session_state.validation_result = validation_result
        st.session_state.output_file = output_file
        st.session_state.job_name = job_name
        st.session_state.phase = "review"
        st.rerun()


# =====================================================================
# PHASE 4: Review Execution Result
# =====================================================================
if st.session_state.phase == "review":
    st.header("4. Review Transformation Result", divider="blue")

    validation_result = st.session_state.validation_result

    if validation_result["success"]:
        st.success("✅ Transformation executed successfully!")

        # Show output preview
        st.subheader("📊 Output Preview")
        if validation_result.get("preview"):
            import pandas as pd
            df_preview = pd.DataFrame(validation_result["preview"])
            st.dataframe(df_preview, use_container_width=True)
            st.caption(f"Showing first {len(validation_result['preview'])} rows")
        elif validation_result.get("output_file") and Path(validation_result["output_file"]).exists():
            try:
                df_out = pd.read_excel(validation_result["output_file"], dtype=str)
                st.dataframe(df_out.head(20), use_container_width=True)
                st.caption(f"Shape: {df_out.shape[0]} rows × {df_out.shape[1]} columns")
            except Exception as e:
                st.warning(f"Could not preview output: {e}")

        if validation_result.get("stdout"):
            with st.expander("📄 Execution Output"):
                st.code(validation_result["stdout"])
    else:
        st.error("❌ Transformation failed!")
        if validation_result.get("error"):
            st.subheader("Error Details")
            st.code(validation_result["error"])
        if validation_result.get("stdout"):
            with st.expander("📄 Execution Output"):
                st.code(validation_result["stdout"])

    # Show generated code
    with st.expander("📝 Generated Code", expanded=False):
        st.code(st.session_state.code, language="python")

    # Action buttons
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if validation_result["success"]:
            if st.button("✅ Approve & Save", type="primary", use_container_width=True):
                # Save outputs
                paths = save_outputs(
                    job_name=st.session_state.job_name,
                    plan=st.session_state.plan,
                    code=st.session_state.code,
                    output_dir=OUTPUT_DIR,
                )
                st.session_state.output_paths = paths
                st.session_state.phase = "done"
                st.rerun()

    with col2:
        if st.button("✏️ Edit Plan", use_container_width=True):
            st.session_state.phase = "plan"
            st.rerun()

    with col3:
        if st.button("🔄 Regenerate Code", use_container_width=True):
            st.session_state.phase = "execute"
            st.rerun()


# =====================================================================
# PHASE 5: Final Results
# =====================================================================
if st.session_state.phase == "done":
    st.header("5. Download Outputs", divider="green")

    st.success("✅ Transformation complete!")

    # Output preview
    output_file = st.session_state.get("output_file")
    if output_file and Path(output_file).exists():
        st.subheader("📊 Output Preview")
        try:
            df_out = pd.read_excel(output_file, dtype=str)
            st.dataframe(df_out.head(20), use_container_width=True)
            st.caption(f"Shape: {df_out.shape[0]} rows × {df_out.shape[1]} columns")
        except Exception as e:
            st.warning(f"Could not preview output: {e}")

    # Show generated code
    with st.expander("📝 Generated Script", expanded=False):
        st.code(st.session_state.code, language="python")

    # Download section
    st.subheader("📥 Downloads")

    paths = st.session_state.output_paths
    col1, col2, col3 = st.columns(3)

    with col1:
        if paths.get("code") and Path(paths["code"]).exists():
            with open(paths["code"]) as f:
                st.download_button("📥 Download transform.py", f.read(),
                                   file_name="transform.py", mime="text/x-python",
                                   use_container_width=True)
    with col2:
        if paths.get("plan_yaml") and Path(paths["plan_yaml"]).exists():
            with open(paths["plan_yaml"]) as f:
                st.download_button("📥 Download plan.yaml", f.read(),
                                   file_name="transform_plan.yaml", mime="text/yaml",
                                   use_container_width=True)
    with col3:
        if paths.get("doc") and Path(paths["doc"]).exists():
            with open(paths["doc"]) as f:
                st.download_button("📥 Download documentation.md", f.read(),
                                   file_name="transform_doc.md", mime="text/markdown",
                                   use_container_width=True)

    if output_file and Path(output_file).exists():
        with open(output_file, "rb") as f:
            st.download_button("📥 Download transformed output.xlsx", f.read(),
                               file_name="output.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)

    # Start over button
    st.divider()
    if st.button("🔄 Start New Transformation", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
