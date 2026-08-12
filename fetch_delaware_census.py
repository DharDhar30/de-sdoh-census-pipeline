import pandas as pd
import requests
import os

# 1. Load Blueprint
excel_files = [f for f in os.listdir('.') if f.endswith('.xlsx') and 'Rural Health' in f]
if not excel_files:
    raise FileNotFoundError("Could not find Rural Health Strategy Excel file.")

df_strategy = pd.read_excel(excel_files[0], sheet_name="Second Draft")

if 'SDOH Domain' in df_strategy.columns:
    df_strategy['SDOH Domain'] = df_strategy['SDOH Domain'].ffill()
if 'Concept' in df_strategy.columns:
    df_strategy['Concept'] = df_strategy['Concept'].ffill()

df_strategy['Clean_Code'] = (
    df_strategy["Code (if available)"]
    .dropna()
    .astype(str)
    .str.strip()
    .str.rstrip(',')
)

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

# Exclude race-iterated tables and detailed language table B16001
all_codes = sorted(list(code_to_label.keys()))
valid_tract_codes = [
    c for c in all_codes 
    if not (len(c.split('_')[0]) > 6 and c.split('_')[0][6].isalpha())
    and not c.startswith("B16001_")
]

# 2. Resilient API Retrieval
base_url = "https://api.census.gov/data/2022/acs/acs5"
chunk_size = 20
dfs = []

print(f"Downloading {len(valid_tract_codes)} tract metrics for Delaware...")

for i in range(0, len(valid_tract_codes), chunk_size):
    chunk = valid_tract_codes[i:i + chunk_size]
    params = {"get": f"NAME,{','.join(chunk)}", "for": "tract:*", "in": "state:10"}
    resp = requests.get(base_url, params=params)
    
    if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
        data = resp.json()
        df_chunk = pd.DataFrame(data[1:], columns=data[0])
        df_chunk["GEOID"] = df_chunk["state"] + df_chunk["county"] + df_chunk["tract"]
        keep_cols = ["GEOID"] + [c for c in chunk if c in df_chunk.columns]
        dfs.append(df_chunk[keep_cols].set_index("GEOID"))
    else:
        # Fallback: Process chunk individually if batch query fails
        for code in chunk:
            p = {"get": f"NAME,{code}", "for": "tract:*", "in": "state:10"}
            r = requests.get(base_url, params=p)
            if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
                d = r.json()
                df_single = pd.DataFrame(d[1:], columns=d[0])
                df_single["GEOID"] = df_single["state"] + df_single["county"] + df_single["tract"]
                if code in df_single.columns:
                    dfs.append(df_single[["GEOID", code]].set_index("GEOID"))

# 3. Merge and Save Dataset
if dfs:
    final_df = pd.concat(dfs, axis=1)
    final_df = final_df.loc[:, ~final_df.columns.duplicated()].reset_index()
    
    metric_cols = [c for c in final_df.columns if c != "GEOID"]
    final_df[metric_cols] = final_df[metric_cols].apply(pd.to_numeric, errors='coerce')
    renamed_df = final_df.rename(columns=code_to_label)
    
    output_filename = "Real_Delaware_Health_Force_Tracts.csv"
    renamed_df.to_csv(output_filename, index=False)
    print(f"\nSUCCESS! File saved to '{output_filename}' ({len(renamed_df)} tracts, {len(renamed_df.columns)-1} columns).")
else:
    print("Error: No data frames were collected from the API.")
