import os
import pandas as pd
import pygris
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# ---------------------------------------------------------------------------
load_dotenv()  # Reads the .env file in your current folder
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

if not CENSUS_API_KEY:
    raise SystemExit(
        "CENSUS_API_KEY not found! Please check your .env file."
    )

STATE_FIPS = "10"  # Delaware FIPS code
YEAR = 2022  # ACS 5-Year Estimates year

# Map ACS API variable codes to human-readable Tableau column names
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


# ---------------------------------------------------------------------------
# 1. FETCH SPATIAL BOUNDARIES VIA PYGRIS
# ---------------------------------------------------------------------------
def fetch_spatial_boundaries():
    print("Fetching Delaware Census Tract boundaries using Pygris...")
    de_tracts = pygris.tracts(state=STATE_FIPS, year=2020, cache=True)
    de_tracts["GEOID"] = de_tracts["GEOID"].astype(str)
    return de_tracts[["GEOID", "NAMELSAD", "COUNTYFP", "geometry"]]


# ---------------------------------------------------------------------------
# 2. PROGRAMMATIC ACS DATA EXTRACT VIA CENSUS API
# ---------------------------------------------------------------------------
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

    if response.status_code != 200:
        print(f"\nCensus API Error ({response.status_code}):")
        print(response.text)
        raise SystemExit(
            "Please check your CENSUS_API_KEY in .env and verify parameter validity."
        )

    data = response.json()
    headers = data[0]
    rows = data[1:]

    df = pd.DataFrame(rows, columns=headers)

    # Build 11-digit GEOID (State[2] + County[3] + Tract[6])
    df["GEOID"] = df["state"] + df["county"] + df["tract"]

    # Clean geography headers
    name_parts = df["NAME"].str.split(",", expand=True)
    df["Geography_Name"] = name_parts[0].str.strip()
    df["County"] = name_parts[1].str.strip() if name_parts.shape[1] > 1 else ""
    df["State"] = name_parts[2].str.strip() if name_parts.shape[1] > 2 else ""

    # Rename variables to readable column names
    df = df.rename(columns=VARIABLE_MAP)

    # Clean missing values and suppress null placeholders
    metric_cols = list(VARIABLE_MAP.values())
    for col in metric_cols:
        df[col] = df[col].replace(NULL_CODES, pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    keep_cols = ["GEOID", "Geography_Name", "County", "State"] + metric_cols
    return df[keep_cols]


# ---------------------------------------------------------------------------
# 3. MERGE & EXPORT
# ---------------------------------------------------------------------------
def main():
    gdf_boundaries = fetch_spatial_boundaries()
    df_metrics = fetch_acs_data(CENSUS_API_KEY)

    print("Merging spatial boundaries with ACS health metrics...")

    # Export Tabular CSV
    output_csv = "Delaware_Tract_Health_Data_Programmatic.csv"
    df_metrics.to_csv(output_csv, index=False)
    print(f"Successfully generated {output_csv} ({len(df_metrics)} tracts).")

    # Export Spatial GeoJSON for Tableau / GIS mapping
    output_geojson = "Delaware_Tracts_Spatial_Health.geojson"
    gdf_merged = gdf_boundaries.merge(df_metrics, on="GEOID", how="inner")
    gdf_merged.to_file(output_geojson, driver="GeoJSON")
    print(f"Successfully generated {output_geojson} for spatial mapping.")


if __name__ == "__main__":
    main()