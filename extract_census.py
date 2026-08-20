import os
import pandas as pd
import pygris
import requests

CENSUS_API_KEY = "YOUR_CENSUS_API_KEY_HERE"  # Put your API key here
STATE_FIPS = "10"  # Delaware
YEAR = 2022  # Or 2024 if active

VARIABLE_MAP = {
    "DP05_0001E": "Total_Population",
    "DP05_0018E": "Median_Age",
    "DP05_0024PE": "Pct_Age_65_Plus",
    "DP03_0062E": "Median_Household_Income",
    "DP03_0128PE": "Pct_Below_Poverty",
    "DP03_0099PE": "Pct_No_Health_Insurance",
    "DP03_0021PE": "Pct_Commute_Public_Transit",
    "DP02_0154PE": "Pct_Broadband_Internet",
    "DP02_0114PE": "Pct_NonEnglish_Language_Home",
}

NULL_CODES = ["-", "**", "***", "(X)", "N", "null", "-666666666"]

def fetch_spatial_boundaries():
    print("Fetching Delaware Census Tract boundaries using Pygris...")
    de_tracts = pygris.tracts(state=STATE_FIPS, year=2020, cache=True)
    de_tracts["GEOID"] = de_tracts["GEOID"].astype(str)
    return de_tracts[["GEOID", "NAMELSAD", "COUNTYFP", "geometry"]]

def fetch_acs_data(api_key: str):
    print("Programmatically extracting ACS Data Profile metrics via Census API...")
    var_list = ",".join(VARIABLE_MAP.keys())
    url = f"https://api.census.gov/data/{YEAR}/acs/acs5/profile"
    params = {
        "get": f"NAME,{var_list}",
        "for": "tract:*",
        "in": f"state:{STATE_FIPS}",
        "key": api_key,
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()
    headers = data[0]
    rows = data[1:]

    df = pd.DataFrame(rows, columns=headers)
    df["GEOID"] = df["state"] + df["county"] + df["tract"]

    name_parts = df["NAME"].str.split(",", expand=True)
    df["Geography_Name"] = name_parts[0].str.strip()
    df["County"] = name_parts[1].str.strip() if name_parts.shape[1] > 1 else ""
    df["State"] = name_parts[2].str.strip() if name_parts.shape[1] > 2 else ""

    df = df.rename(columns=VARIABLE_MAP)

    metric_cols = list(VARIABLE_MAP.values())
    for col in metric_cols:
        df[col] = df[col].replace(NULL_CODES, pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    keep_cols = ["GEOID", "Geography_Name", "County", "State"] + metric_cols
    return df[keep_cols]

def main():
    gdf_boundaries = fetch_spatial_boundaries()
    df_metrics = fetch_acs_data(CENSUS_API_KEY)

    print("Merging spatial boundaries with ACS health metrics...")
    output_csv = "Delaware_Tract_Health_Data_Programmatic.csv"
    df_metrics.to_csv(output_csv, index=False)
    print(f"Successfully generated {output_csv} ({len(df_metrics)} tracts).")

    output_geojson = "Delaware_Tracts_Spatial_Health.geojson"
    gdf_merged = gdf_boundaries.merge(df_metrics, on="GEOID", how="inner")
    gdf_merged.to_file(output_geojson, driver="GeoJSON")
    print(f"Successfully generated {output_geojson} for spatial mapping.")

if __name__ == "__main__":
    main()
