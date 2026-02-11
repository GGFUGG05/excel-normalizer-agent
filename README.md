# Excel Normalizer Agent

**Transform messy Excel files into clean, normalized data with an Agent.**

Scale the data transformation process! Describe what you want in natural language, and let the AI agent generate a documented, reusable transformation pipeline.

---

## Why This Tool?

Data teams spend countless hours wrangling Excel files from different sources:
- Sales reports with merged cells and subtotals
- Vendor data with months spread across columns
- Legacy exports with inconsistent formatting

**Traditional approach:** Write custom pandas code for each file format. Time-consuming, error-prone, and hard to maintain.

**With Excel Normalizer Agent:**
1. Upload your messy file + show the target format
2. Describe the transformation in natural language
3. Get a working Python script + editable transformation plan
4. **Re-run on new files** — select a saved project, upload new files, and execute instantly with no LLM needed

---

## Key Features

| Feature | Benefit |
|---------|---------|
| **Natural Language Instructions** | Describe transformations in plain English — no coding required to start |
| **Human-in-the-Loop Review** | Preview results before saving; iterate until it's right |
| **Editable Transformation Plans** | YAML-based plans you can version control, edit, and reuse |
| **Standalone Python Scripts** | Generated code runs anywhere — no vendor lock-in |
| **Run Existing Projects** | Re-run saved transformations on new files — no LLM needed, batch upload supported |
| **Step-by-Step Documentation** | Every transformation is documented for future reference |

---

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

### Run Existing Mode

Once you've created a transformation project, you can re-run it on new files without any LLM calls:

```
Sidebar: "Run Existing" mode
         │
         ▼
Scan output/ → dropdown of saved projects (with transform.py)
         │
         ▼
Pick project → see plan summary from YAML
         │
         ▼
Upload one or more raw files (batch)
         │
         ▼
[Run Transformation] → executes saved transform.py per file
         │
         ▼
Results: per-file status + preview + download
         Output: output/{project}/output_{name}_{timestamp}.xlsx
```

This is useful when the same file format arrives regularly (e.g., monthly reports) — build the transformation once, then re-run on each new batch.

---

## Quick Start

### 1. Setup

**Prerequisites:** Python 3.10+

```bash
# Clone the repository
git clone https://github.com/GGFUGG05/excel-normalizer-agent.git
cd excel-normalizer-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Set your API key
cp .env.example .env      # Linux/Mac
copy .env.example .env    # Windows
# Edit .env and add your Anthropic API key
```

### 2. Run

```bash
streamlit run app.py
```

### 3. Transform (New)

1. **Upload** your raw Excel file and target template
2. **Describe** what needs to happen (e.g., "unpivot month columns, extract package size from product name")
3. **Review** the generated plan and adjust if needed
4. **Execute** and preview the results
5. **Download** your transformation script and documentation

### 4. Re-Run on New Files

1. Switch to **"Run Existing"** mode in the sidebar
2. **Select** a saved project from the dropdown
3. **Upload** one or more new raw files
4. **Click** "Run Transformation" — outputs are saved with timestamps into the project folder

---

## Example: Coca-Cola Sellout Transformation

See [`examples/coca-cola-mockup/`](examples/coca-cola-mockup/) for a complete working example.

**Before:** Wide-format sellout data with months as columns

| Product Name | Product Code | POS Code | Jan | Feb | ... |
|--------------|--------------|----------|-----|-----|-----|
| Coca-Cola PET 50cl x 24 | CC-PET50-24 | POS-001 | 100 | 150 | ... |

**After:** Normalized long-format table (15 rows x 12 months = 180 rows)

| productname | productcode | numperpackage | poscode | month | amount |
|-------------|-------------|---------------|---------|-------|--------|
| Coca-Cola PET 50cl | CC-PET50-24 | 24 | POS-001 | 1 | 100 |

**What the agent figured out:**
- Extract package quantity ("x 24") from product name
- Unpivot 12 month columns into rows
- Convert month names to numbers (Jan=1, Feb=2, ...)
- Cast all columns to appropriate types

```bash
# Run the example
cd examples/coca-cola-mockup/output
python transform.py
```

---

## The Transformation Plan

The plan is the **source of truth** — a structured YAML file that describes every transformation step. This design means:

- **Readable**: Each step has a plain-English description
- **Editable**: Modify the YAML directly without regenerating
- **Version-controllable**: Track changes in git
- **Reusable**: Copy and adapt plans for similar files

### Example Plan

```yaml
source_description: >
  Wide-format sellout report with monthly columns

target_description: >
  One row per SKU × outlet × month

steps:
  - step: 1
    action: split_column
    description: Extract package quantity from Product Name
    params:
      source: Product Name
      delimiter: ' x '
      into: [productname, numperpackage]

  - step: 2
    action: unpivot
    description: Melt month columns into rows
    params:
      id_vars: [productname, productcode, poscode]
      var_name: month
      value_name: amount
```

### Editing Options

| Method | Best For |
|--------|----------|
| **Natural Language Feedback** | "Step 1 is wrong — the header is in row 3, not row 1" |
| **Direct YAML Editing** | Precise parameter changes without LLM round-trip |
| **Offline Editing** | Edit `.yaml` files in any text editor and re-upload |

---

## Supported Transformations

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

---

## Project Structure

```
excel-normalizer-agent/
├── app.py                    # Streamlit UI
├── config.py                 # Settings (model, timeouts)
├── requirements.txt
│
├── agent/
│   ├── agent.py              # Core orchestrator (plan, codegen, validate, re-run)
│   ├── tools/                # Excel analysis, code execution
│   └── prompts/              # System prompts for each phase
│
├── models/
│   └── transform_plan.py     # Pydantic models
│
├── examples/                 # Working examples
│   └── coca-cola-mockup/
│
├── input/                    # Uploaded files (gitignored)
└── output/                   # Generated artifacts (gitignored)
```

---

## Configuration

Edit `config.py` to customize:

| Setting | Default | Description |
|---------|---------|-------------|
| `MODEL_NAME` | `claude-haiku-4-5-20251001` | Model to use |
| `EXECUTION_TIMEOUT` | 120 | Script execution timeout (seconds) |
| `MAX_RETRIES` | 3 | Retry count for failed operations |
| `MAX_SAMPLE_ROWS` | 50 | Rows to sample during analysis |

---

## Use Cases

- **Sales & Marketing**: Normalize sellout reports from different retailers
- **Finance**: Transform bank statements and transaction exports
- **Supply Chain**: Standardize vendor data feeds
- **Analytics**: Prepare data for dashboards and BI tools
- **Data Migration**: Convert legacy Excel formats to modern schemas

---

## Tech Stack

- **Frontend**: Streamlit
- **AI**: Claude (Anthropic) via LangChain - can be adapted to other LLMs
- **Data Processing**: pandas, openpyxl
- **Validation**: Pydantic

---

## License

MIT

---

## Contributing

Contributions welcome! Please open an issue to discuss major changes before submitting a PR.
