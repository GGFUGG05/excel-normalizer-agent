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
from agent.agent import generate_plan, revise_plan, generate_code, validate_transform, save_outputs, run_existing_transform


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Excel Normalizer Agent",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Excel Normalizer Agent")
st.caption("Upload a raw Excel file → get a documented transformation script OR Run the transformation code directly for an existing project.")

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
    # "Run Existing" mode state
    "mode": "new",               # "new" | "existing"
    "selected_project": "",      # chosen project directory name
    "run_results": [],           # results from batch execution
    "re_phase": "upload",        # "upload" | "running" | "done"
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


def get_existing_projects() -> list[str]:
    """Scan output/ for subdirectories that contain a transform.py file."""
    output_path = Path(OUTPUT_DIR)
    if not output_path.exists():
        return []
    projects = []
    for d in sorted(output_path.iterdir()):
        if d.is_dir() and (d / "transform.py").exists():
            projects.append(d.name)
    return projects


# ---------------------------------------------------------------------------
# Sidebar: settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")

    mode = st.radio("Mode", ["New Transformation", "Run Existing"],
                    horizontal=True,
                    key="mode_radio")
    is_existing_mode = mode == "Run Existing"
    st.session_state.mode = "existing" if is_existing_mode else "new"

    st.divider()

    if not is_existing_mode:
        # --- New Transformation settings ---
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
    else:
        # --- Run Existing settings ---
        projects = get_existing_projects()
        if projects:
            selected = st.selectbox("Select project", projects,
                                    key="project_dropdown")
            st.session_state.selected_project = selected

            # Show plan summary from YAML
            plan_yaml_path = Path(OUTPUT_DIR) / selected / "transform_plan.yaml"
            if plan_yaml_path.exists():
                with st.expander("📋 Plan summary", expanded=False):
                    try:
                        plan_data = yaml.safe_load(plan_yaml_path.read_text())
                        if plan_data.get("source_description"):
                            st.markdown(f"**Source:** {plan_data['source_description']}")
                        if plan_data.get("target_description"):
                            st.markdown(f"**Target:** {plan_data['target_description']}")
                        if plan_data.get("steps"):
                            st.markdown("**Steps:**")
                            for step in plan_data["steps"]:
                                st.markdown(f"- {step.get('step', '?')}. {step.get('action', '')}")
                    except Exception:
                        st.warning("Could not parse plan YAML.")

            # Check if transform.py uses env vars
            transform_path = Path(OUTPUT_DIR) / selected / "transform.py"
            if transform_path.exists():
                code_text = transform_path.read_text()
                if "os.environ" not in code_text and "INPUT_FILE" not in code_text:
                    st.warning(
                        "This script may have hardcoded file paths instead of "
                        "using `INPUT_FILE`/`OUTPUT_FILE` environment variables. "
                        "It may need updating to work with new files."
                    )
        else:
            st.info("No existing projects found. Create one using 'New Transformation' first.")

    if st.button("🔄 Reset", use_container_width=True):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()


# =====================================================================
# "Run Existing" Mode — self-contained section
# =====================================================================
if st.session_state.mode == "existing":
    st.header("Run Existing Transformation", divider="violet")

    projects = get_existing_projects()
    selected_project = st.session_state.get("selected_project", "")

    if not projects:
        st.info("No existing projects found in `output/`. Create one using 'New Transformation' first.")
    elif not selected_project:
        st.info("Select a project from the sidebar to get started.")
    else:
        re_phase = st.session_state.re_phase

        # --- Step 1: Upload ---
        if re_phase in ("upload", "done"):
            if re_phase == "done":
                # Show results from previous run first
                st.subheader("Results")
                run_results = st.session_state.run_results
                for i, res in enumerate(run_results):
                    input_name = Path(res.get("input_file", "")).name
                    if res["success"]:
                        with st.expander(f"✅ {input_name}", expanded=(i == 0)):
                            if res.get("preview"):
                                df_preview = pd.DataFrame(res["preview"])
                                st.dataframe(df_preview, use_container_width=True)
                                st.caption(f"Showing first {len(res['preview'])} rows")
                            if res.get("stdout"):
                                with st.expander("Execution output"):
                                    st.code(res["stdout"])
                            if res.get("output_file") and Path(res["output_file"]).exists():
                                with open(res["output_file"], "rb") as f:
                                    st.download_button(
                                        f"📥 Download {Path(res['output_file']).name}",
                                        f.read(),
                                        file_name=Path(res["output_file"]).name,
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        key=f"dl_{i}",
                                    )
                    else:
                        with st.expander(f"❌ {input_name}", expanded=True):
                            st.error(res.get("error", "Unknown error"))
                            if res.get("stdout"):
                                st.code(res["stdout"])

                st.divider()
                if st.button("🔄 Run Another Batch", use_container_width=True):
                    st.session_state.re_phase = "upload"
                    st.session_state.run_results = []
                    st.rerun()

            # File uploader (shown in both upload and done phases)
            if re_phase == "upload":
                st.subheader(f"Upload files for: **{selected_project}**")
                uploaded_files = st.file_uploader(
                    "Upload raw files to transform",
                    type=["xlsx", "xls", "csv"],
                    accept_multiple_files=True,
                    key="re_file_uploader",
                )

                if uploaded_files:
                    for uf in uploaded_files:
                        with st.expander(f"👀 Preview: {uf.name}"):
                            try:
                                df_preview = pd.read_excel(uf, header=None, nrows=20, dtype=str)
                                st.dataframe(df_preview, use_container_width=True)
                                uf.seek(0)
                            except Exception as e:
                                st.error(f"Error reading file: {e}")

                    if st.button("🚀 Run Transformation", type="primary", use_container_width=True):
                        # Save uploaded files to input/
                        saved_paths = []
                        for uf in uploaded_files:
                            path = _save_uploaded(uf, uf.name)
                            saved_paths.append(path)

                        project_dir = str(Path(OUTPUT_DIR) / selected_project)

                        with st.spinner("Running transformation on uploaded files..."):
                            results = run_existing_transform(
                                project_dir=project_dir,
                                raw_files=saved_paths,
                            )

                        st.session_state.run_results = results
                        st.session_state.re_phase = "done"
                        st.rerun()


# =====================================================================
# "New Transformation" Mode — existing phases
# =====================================================================
if st.session_state.mode == "new":

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
