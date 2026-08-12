import pandas as pd
import requests

# 1. Read your Excel Strategy File
file_path = "Data Sources_ Rural Health Strategy for Delaware.xlsx"
df_strategy = pd.read_excel(file_path, sheet_name="Second Draft")

# Extract non-empty ACS variable codes from your spreadsheet
variable_codes = (
    df_strategy["Code (if available)"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
    .tolist()
)

# Convert ACS table codes into Census API variable format (e.g., 'B08105A_001E')
census_vars = [f"{code.rstrip(',')}E" for code in variable_codes if "_" in code][:40]

print(f"Extracted {len(census_vars)} ACS variables from your Excel file...")

# 2. Query US Census Bureau API for all Census Tracts in Delaware (State FIPS '10')
base_url = "https://api.census.gov/data/2022/acs/acs5"
params = {
    "get": f"NAME,{','.join(census_vars)}",
    "for": "tract:*",
    "in": "state:10",
}

print("Fetching real Census data from US Census Bureau...")
response = requests.get(base_url, params=params)

if response.status_code == 200:
    data = response.json()
    
    # 3. Format into a clean Pandas DataFrame
    headers = data[0]
    rows = data[1:]
    
    df_census = pd.DataFrame(rows, columns=headers)
    
    # Combine state + county + tract FIPS into a 11-digit GEOID for Tableau Mapping
    df_census["GEOID"] = df_census["state"] + df_census["county"] + df_census["tract"]
    
    # Move GEOID and NAME to the front
    cols = ["GEOID", "NAME"] + [c for c in headers if c not in ["state", "county", "tract", "NAME"]]
    df_final = df_census[cols]
    
    # 4. Save to CSV for Tableau
    output_filename = "Real_Delaware_Health_Force_Tracts.csv"
    df_final.to_csv(output_filename, index=False)
    print(f"Success! Saved real census dataset to '{output_filename}'")

else:
    print(f"API Request Failed (Status Code: {response.status_code})")
    print(response.text)