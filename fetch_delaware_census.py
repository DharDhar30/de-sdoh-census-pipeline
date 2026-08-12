import pandas as pd
import requests
import os

# 1. Load Strategy Blueprint Excel file
excel_files = [f for f in os.listdir('.') if f.endswith('.xlsx') and 'Rural Health' in f]
if not excel_files:
    raise FileNotFoundError("Could not find Rural Health Strategy Excel file.")

file_path = excel_files[0]
print(f"Reading strategy blueprint from: {file_path}")
df_strategy = pd.read_excel(file_path, sheet_name="Second Draft")

# Forward fill category hierarchies
if 'SDOH Domain' in df_strategy.columns:
    df_strategy['SDOH Domain'] = df_strategy['SDOH Domain'].ffill()
if 'Concept' in df_strategy.columns:
    df_strategy['Concept'] = df_strategy['Concept'].ffill()

# Clean code strings
df_strategy['Clean_Code'] = (
    df_strategy["Code (if available)"]
    .dropna()
    .astype(str)
    .str.strip()
    .str.rstrip(',')
)

# Build Mapping Dictionary: Code -> Descriptive Label
code_to_label = {}
for _, row in df_strategy.iterrows():
    code = row['Clean_Code']
    if pd.notna(code) and "_" in code:
        code_e = f"{code}E" if not code.endswith('E') else code
        domain = str(row.get('SDOH Domain', '')).strip() if pd.notna(row.get('SDOH Domain')) else ""
        concept = str(row.get('Concept', '')).strip() if pd.notna(row.get('Concept')) else ""
        variable = str(row.get('Variable', '')).strip() if pd.notna(row.get('Variable')) else code
        
        label_parts = [p for p in [domain, concept, variable] if p and p != "nan"]
        label = " | ".join(label_parts) if label_parts else code_e
        code_to_label[code_e] = label

candidate_vars = sorted(list(code_to_label.keys()))
print(f"Extracted {len(candidate_vars)} candidate variables from blueprint.")

# 2. Adaptive Census API Fetcher
base_url = "https://api.census.gov/data/2022/acs/acs5"
dfs = []

def fetch_variable_batch(vars_list):
    """Fetch variables from Census API. Recursively split batches if API rejects invalid codes."""
    if not vars_list:
        return
    
    params = {
        "get": f"NAME,{','.join(vars_list)}",
        "for": "tract:*",
        "in": "state:10",
    }
    
    resp = requests.get(base_url, params=params)
    
    if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
        try:
            data = resp.json()
            df_chunk = pd.DataFrame(data[1:], columns=data[0])
            df_chunk["GEOID"] = df_chunk["state"] + df_chunk["county"] + df_chunk["tract"]
            
            keep_cols = ["GEOID"] + [c for c in vars_list if c in df_chunk.columns]
            dfs.append(df_chunk[keep_cols].set_index("GEOID"))
            print(f" Successfully fetched {len(vars_list)} variables.")
        except Exception:
            pass
    else:
        # If batch contains invalid tract codes, divide batch in half
        if len(vars_list) > 1:
            mid = len(vars_list) // 2
            fetch_variable_batch(vars_list[:mid])
            fetch_variable_batch(vars_list[mid:])
        else:
            print(f" Skipping variable {vars_list[0]} (not available at Census Tract level).")

# Process in initial chunks of 25
chunk_size = 25
print("Starting adaptive API retrieval...")
for i in range(0, len(candidate_vars), chunk_size):
    fetch_variable_batch(candidate_vars[i:i + chunk_size])

# 3. Merge, Format Data Types, and Save
if dfs:
    final_df = pd.concat(dfs, axis=1).reset_index()
    final_df = final_df.loc[:, ~final_df.columns.duplicated()]
    
    # Convert numerical metric columns from strings to numbers
    metric_cols = [c for c in final_df.columns if c != "GEOID"]
    final_df[metric_cols] = final_df[metric_cols].apply(pd.to_numeric, errors='coerce')
    
    # Apply human-readable column headers
    renamed_df = final_df.rename(columns=code_to_label)
    
    output_filename = "Real_Delaware_Health_Force_Tracts.csv"
    renamed_df.to_csv(output_filename, index=False)
    print(f"\nSUCCESS! Retained {len(renamed_df.columns) - 1} valid metrics across {len(renamed_df)} Delaware Census Tracts.")
    print(f"Saved formatted dataset to '{output_filename}'")
else:
    print("\nNo valid data retrieved.")
