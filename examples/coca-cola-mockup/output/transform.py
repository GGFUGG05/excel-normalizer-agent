import os
import pandas as pd
import numpy as np

# # Get file paths from environment variables
# INPUT_FILE = os.environ["INPUT_FILE"]
# OUTPUT_FILE = os.environ["OUTPUT_FILE"]

INPUT_FILE = 'coca_cola_sellout_mockup.xlsx'
OUTPUT_FILE = 'coca_cola_sellout_mockup_transformed.xlsx'

# Step 1: Read the Excel file with all columns as strings to avoid type inference issues
print("Reading input file...")
df = pd.read_excel(INPUT_FILE, dtype=str)

# Step 1: Drop the first empty column (Unnamed: 0 / column A)
print("Step 1: Dropping empty column A...")
if df.columns[0].startswith('Unnamed'):
    df = df.drop(columns=[df.columns[0]])

# Reset column index for easier handling
df = df.reset_index(drop=True)

# Step 2: Extract package quantity from Product Name
# Split on ' x ' delimiter
print("Step 2: Extracting package quantity from Product Name...")
product_col = 'Product Name'
if product_col in df.columns:
    split_data = df[product_col].str.split(' x ', n=1, expand=True)
    df[product_col] = split_data[0].str.strip()
    df['numperpackage'] = split_data[1].str.strip()

# Step 3: Rename columns to match target schema
print("Step 3: Renaming columns to lowercase target schema...")
rename_mapping = {
    'Product Name': 'productname',
    'Product Code': 'productcode',
    'POS Code': 'poscode',
    'numperpackage': 'numperpackage'
}
df = df.rename(columns=rename_mapping)

# Step 4: Unpivot from wide to long format
# Identify month columns (should be Jan through Dec in columns E-P)
print("Step 4: Unpivoting wide format to long format...")
month_columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Filter to only include month columns that exist in the dataframe
available_months = [m for m in month_columns if m in df.columns]

# Unpivot the dataframe
id_vars = ['productname', 'productcode', 'numperpackage', 'poscode']
df = df.melt(id_vars=id_vars, value_vars=available_months, var_name='month', value_name='amount')

# Step 5: Convert month names to numeric month numbers (1-12)
print("Step 5: Converting month names to numeric values...")
month_mapping = {
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12
}
df['month'] = df['month'].map(month_mapping)

# Step 6: Cast data types to appropriate formats
print("Step 6: Casting data types...")
df['productname'] = df['productname'].astype('string')
df['productcode'] = df['productcode'].astype('string')
df['numperpackage'] = pd.to_numeric(df['numperpackage'], errors='coerce').astype('Int64')
df['poscode'] = df['poscode'].astype('string')
df['month'] = pd.to_numeric(df['month'], errors='coerce').astype('Int64')
df['amount'] = pd.to_numeric(df['amount'], errors='coerce').astype('Int64')

# Step 7: Sort by productname, productcode, numperpackage, poscode, month (ascending)
print("Step 7: Sorting rows for consistent output order...")
df = df.sort_values(by=['productname', 'productcode', 'numperpackage', 'poscode', 'month'], 
                     ascending=True).reset_index(drop=True)

# Write the transformed data to output file
print("Writing output file...")
df.to_excel(OUTPUT_FILE, index=False, engine='openpyxl')

# Print summary
print(f"\nTransformation complete!")
print(f"Total rows: {len(df)}")
print(f"Columns: {', '.join(df.columns.tolist())}")
print(f"Output written to: {OUTPUT_FILE}")