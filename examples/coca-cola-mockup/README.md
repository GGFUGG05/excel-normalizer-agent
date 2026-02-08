# Example: Coca-Cola Sellout Data Transformation

This example demonstrates transforming a wide-format sellout report into a normalized long-format table.

## The Problem

The raw data contains monthly sellout amounts in columns (wide format):

| Product Name | Product Code | POS Code | Jan | Feb | Mar | ... | Dec |
|--------------|--------------|----------|-----|-----|-----|-----|-----|
| Coca-Cola PET 50cl x 24 | CC-PET50-24 | POS-001 | 100 | 150 | 200 | ... | 180 |

**Issues to solve:**
- Package quantity ("x 24") embedded in Product Name
- Monthly data spread across columns (wide format)
- Need to normalize to one row per SKU-POS-Month

## The Solution

The agent generates a transformation plan that:

1. **Drops** the empty first column
2. **Splits** Product Name to extract `numperpackage` (e.g., "24")
3. **Renames** columns to lowercase target schema
4. **Unpivots** month columns into rows (wide → long)
5. **Converts** month names to numbers (Jan=1, Feb=2, ...)
6. **Casts** data types appropriately
7. **Sorts** for consistent output

## Result

The output is a normalized table:

| productname | productcode | numperpackage | poscode | month | amount |
|-------------|-------------|---------------|---------|-------|--------|
| Coca-Cola PET 50cl | CC-PET50-24 | 24 | POS-001 | 1 | 100 |
| Coca-Cola PET 50cl | CC-PET50-24 | 24 | POS-001 | 2 | 150 |
| ... | ... | ... | ... | ... | ... |

15 original rows × 12 months = **180 normalized rows**

## Files

```
input/
├── raw_coca_cola_sellout_mockup.xlsx      # Raw wide-format data
├── template_taget_templage.xlsx            # Target column structure
└── example_coca_cola_sellout_mockup_output.xlsx  # Expected output sample

output/
├── transform.py              # Generated Python script
├── transform_plan.yaml       # Transformation plan (editable)
├── transform_doc.md          # Human-readable documentation
└── output.xlsx               # Transformed result
```

## Running the Example

```bash
cd examples/coca-cola-mockup/output
python transform.py
```

Or use the Streamlit UI and upload the files from the `input/` folder.
