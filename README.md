# Excel Normalizer Agent

An AI-powered tool that generates documented Python transformation scripts to normalize
raw/formatted Excel files into clean tabular data.

## How It Works

```
Raw Excel + Template + Instructions
        │
        ▼
   ┌─────────┐
   │ ANALYZE │  Agent profiles all input files
   └────┬────┘
        ▼
   ┌─────────┐
   │  PLAN   │  Agent creates a structured transformation plan
   └────┬────┘
        ▼
   ┌─────────┐
   │ REVIEW  │  You review, give feedback, or edit the plan directly
   └────┬────┘
        ▼
   ┌─────────┐
   │ CODEGEN │  Agent generates a standalone pandas script
   └────┬────┘
        ▼
   ┌─────────┐
   │ EXECUTE │  Script runs directly, output previewed in UI
   └────┬────┘
        ▼
   ┌─────────┐
   │ APPROVE │  You review results: Approve, Edit Plan, or Regenerate
   └────┬────┘
        ▼
   transform.py + transform_plan.yaml + transform_doc.md
```

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set your API key (option 1: environment variable)
export ANTHROPIC_API_KEY=your-key-here  # Linux/Mac
set ANTHROPIC_API_KEY=your-key-here     # Windows

# Set your API key (option 2: .env file)
cp .env.example .env
# Then edit .env and add your key
```

You can also enter your API key directly in the Streamlit sidebar when running the app.

## Usage

```bash
streamlit run app.py
```

Then in the browser:

1. **Upload** your raw Excel file, target template, and (optionally) example output rows
2. **Write instructions** describing the transformation logic
3. **Review the plan** — the agent shows its understanding and step-by-step plan
4. **Edit if needed** — type natural language feedback or toggle to edit the YAML directly
5. **Generate code** — the agent creates a Python script
6. **Review results** — the script executes and you see the output preview
   - **Approve & Save** — save all artifacts if the output looks correct
   - **Edit Plan** — go back to modify the transformation plan
   - **Regenerate Code** — generate a new script from the current plan
7. **Download** the script, plan YAML, and documentation

## Project Structure

```
excel-normalizer-agent/
├── app.py                          # Streamlit UI
├── config.py                       # Settings (model, timeouts, paths)
├── requirements.txt
│
├── agent/
│   ├── agent.py                    # Core orchestrator (plan, codegen, execute)
│   ├── tools/
│   │   ├── excel_analyzer.py       # Tool: profile Excel files
│   │   ├── code_executor.py        # Tool: run generated scripts
│   │   └── output_comparator.py    # Tool: compare outputs (utility)
│   └── prompts/
│       └── system.py               # System prompts for each phase
│
├── models/
│   └── transform_plan.py           # Pydantic models (TransformPlan, FileProfile, etc.)
│
├── input/                          # Uploaded files (auto-created)
├── output/                         # Generated artifacts per job
│   └── <job_name>/
│       ├── transform.py            # Standalone transformation script
│       ├── transform_plan.yaml     # Editable plan (source of truth)
│       ├── transform_doc.md        # Human-readable documentation
│       └── output.xlsx             # Transformed output
```

## The Transformation Plan

The plan is the **source of truth** — a structured YAML file that describes every
transformation step. This design means:

- **Humans can read it**: Each step has a plain-English description
- **Humans can edit it**: Modify the YAML and re-run codegen without the LLM
- **It's version-controllable**: Track changes to transformation logic in git
- **It's reusable**: Copy and adapt plans for similar files

### Example Plan

```yaml
source_description: >
  Product sellout file at POS level. Each POS has a header row
  followed by SKU detail rows with monthly columns.

target_description: >
  One row per SKU × outlet × month with columns:
  outlet_name, sku_code, sku_name, month, sellout

assumptions:
  - POS header rows identified by having only column A populated
  - Month columns follow pattern like 'Jan-24', 'Feb-24'

steps:
  - step: 1
    action: detect_group_headers
    description: Identify POS header rows where only column A has a value
    params:
      detection_rule: "row where columns[1:] are all NaN"
      extract_field: outlet_name

  - step: 2
    action: forward_fill_group
    description: Assign each SKU row to its parent POS
    params:
      field: outlet_name

  - step: 3
    action: unpivot
    description: Melt month columns into rows
    params:
      id_vars: [outlet_name, sku_code, sku_name]
      var_name: month
      value_name: sellout
```

## Plan Editing Options

### Natural Language Feedback
> "Step 1 is wrong — the POS header is not identified by empty columns,
> it's any row where column A starts with 'Store:'"

The agent revises the plan and shows you the updated version.

### Direct YAML Editing
Toggle "Edit plan directly" in the UI to modify the YAML. Useful for
precise parameter changes without going through the LLM.

### Offline Editing
Plans are saved as `.yaml` files. You can edit them in any text editor
and re-upload, or use them as templates for new transformations.

## Supported Transformation Actions

| Action | Description |
|--------|-------------|
| `skip_rows` | Skip N rows from the top |
| `set_header_row` | Use a specific row as column headers |
| `detect_group_headers` | Identify section/group header rows |
| `forward_fill_group` | Forward-fill group values to child rows |
| `drop_non_data_rows` | Remove non-data rows (headers, totals, blanks) |
| `rename_columns` | Map raw column names to target names |
| `split_column` | Split one column into multiple |
| `unpivot` | Melt wide columns into rows |
| `cast_types` | Set column data types |
| `filter` | Filter rows by condition |
| `add_column` | Add computed or constant column |
| `custom` | Free-form transformation logic |

## Configuration

Edit `config.py` to change:
- `MODEL_NAME`: Default is `claude-haiku-4-5-20251001` (cost-efficient)
- `EXECUTION_TIMEOUT`: Script execution timeout in seconds
- `MAX_RETRIES`: Retry count for failed validation
- `MAX_SAMPLE_ROWS`: Rows to sample during analysis
