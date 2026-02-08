# Transformation Documentation: coca-cola-mockup

## Source Description
The raw Excel file contains a wide-format sellout report starting at B1 (row 0 in 0-indexed). Each row represents a SKU-POS combination with:
- Column B: Product Name (contains package information, e.g., 'Coca-Cola PET 50cl x 24')
- Column C: Product Code (e.g., 'CC-PET50-24')
- Column D: POS Code (e.g., 'POS-001')
- Columns E-P: Monthly sellout amounts (Jan through Dec)
The Product Name contains the unit packaging count (e.g., 'x 24') that needs to be extracted.

## Target Description
The target format is a normalized long-format table with 6 columns:
1. productname: Product description without packaging count (e.g., 'Coca-Cola PET 50cl')
2. productcode: Product SKU code (e.g., 'CC-PET50-24')
3. numperpackage: Package quantity extracted from product name (e.g., '24')
4. poscode: Point of Sale location code (e.g., 'POS-001')
5. month: Month number as integer (1-12 representing Jan-Dec)
6. amount: Sellout amount for that SKU-POS-Month combination
Each original row expands into 12 rows (one per month).

## Assumptions

- The Product Name always follows the pattern '[Brand/Description] x [number]' where the number at the end after ' x ' is the package quantity
- Month columns are always ordered chronologically from Jan (column E) to Dec (column P)
- The first empty column (A) should be dropped
- All 15 data rows should be processed (no summary rows)
- Month values in output should be numeric (1-12) not text month names
- Amount values are currently text and should be converted to numeric

## Transformation Steps

### Step 1: drop_non_data_rows
Remove the first empty column (Unnamed: 0 / column A) which contains no data

**Parameters:**
```yaml
rules:
- Column A is empty for all rows - drop this column
```

### Step 2: split_column
Extract the package quantity from Product Name. Split 'Coca-Cola PET 50cl x 24' into two parts:
- Product base name: 'Coca-Cola PET 50cl' (everything before ' x ')
- Package number: '24' (everything after ' x ')

**Parameters:**
```yaml
delimiter: ' x '
into:
- Product Name
- numperpackage
source: Product Name
```

### Step 3: rename_columns
Rename columns to match target schema (all lowercase)

**Parameters:**
```yaml
mapping:
  POS Code: poscode
  Product Code: productcode
  Product Name: productname
  numperpackage: numperpackage
```

### Step 4: unpivot
Convert wide format (months as columns) to long format. Keep productname, productcode, numperpackage, poscode as identifier columns. Unpivot the 12 month columns (Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec) into two new columns:
- month: the month name (Jan-Dec)
- amount: the corresponding sellout value

**Parameters:**
```yaml
id_vars:
- productname
- productcode
- numperpackage
- poscode
value_name: amount
value_vars_pattern: Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec
var_name: month
```

### Step 5: custom
Convert month names to numeric month numbers (1-12). Create a mapping: Jan=1, Feb=2, Mar=3, Apr=4, May=5, Jun=6, Jul=7, Aug=8, Sep=9, Oct=10, Nov=11, Dec=12. Replace the month column values with these numbers.

**Parameters:**
```yaml
logic: 'Create a dictionary mapping {''Jan'': ''1'', ''Feb'': ''2'', ''Mar'': ''3'',
  ''Apr'': ''4'', ''May'': ''5'', ''Jun'': ''6'', ''Jul'': ''7'', ''Aug'': ''8'',
  ''Sep'': ''9'', ''Oct'': ''10'', ''Nov'': ''11'', ''Dec'': ''12''} and apply to
  the month column'
```

### Step 6: cast_types
Convert data types to appropriate formats

**Parameters:**
```yaml
amount: int
month: int
numperpackage: int
poscode: string
productcode: string
productname: string
```

### Step 7: custom
Verify row order: Result should have 180 rows (15 SKU-POS combinations ¡Á 12 months). Rows should be ordered by productname, productcode, numperpackage, poscode, month (ascending).

**Parameters:**
```yaml
logic: 'Sort by: productname, productcode, numperpackage, poscode, month ascending
  to ensure consistent output order'
```


## Generated Script
See `transform.py` in the same directory.
