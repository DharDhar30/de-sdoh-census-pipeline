import os
import pandas as pd
import pygris
import requests

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
CENSUS_API_KEY = "5622ad46b5377abbc9c5a0c351a78494426d5ef3" 
STATE_FIPS = "10"  # Delaware FIPS code
YEAR = 2024  # ACS 5-Year Estimates year (adjust as needed)

# Map ACS API variable codes to human-readable Tableau column names
# DP05 = Demographic, DP03 = Economic, DP02 = Social
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
    # Pull 2020 TIGER/Line tract shapefile for Delaware
    de_tracts = pygris.tracts(state=STATE_FIPS, year=2020, cache=True)

    # Clean / select key geography columns
    de_tracts["GEOID"] = de_tracts["GEOID"].astype(str)
    return de_tracts[["GEOID", "NAMELSAD", "COUNTYFP", "geometry"]]


# ---------------------------------------------------------------------------
# 2. PROGRAMMATIC ACS DATA EXTRACT VIA CENSUS API
# ---------------------------------------------------------------------------
def fetch_acs_data(api_key: str):
    print("Programmatically extracting ACS Data Profile metrics via Census API...")
    var_list = ",".join(VARIABLE_MAP.keys())

    # Build ACS 5-Year Data Profile API Endpoint
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

    # Construct the 11-digit GEOID (State[2] + County[3] + Tract[6])
    df["GEOID"] = df["state"] + df["county"] + df["tract"]

    # Parse location names
    name_parts = df["NAME"].str.split(",", expand=True)
    df["Geography_Name"] = name_parts[0].str.strip()
    df["County"] = name_parts[1].str.strip() if name_parts.shape[1] > 1 else ""
    df["State"] = name_parts[2].str.strip() if name_parts.shape[1] > 2 else ""

    # Rename metric variables
    df = df.rename(columns=VARIABLE_MAP)

    # Clean up numeric values & suppress Census null codes
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
    # Step A: Fetch spatial data
    gdf_boundaries = fetch_spatial_boundaries()

    # Step B: Fetch ACS metrics
    df_metrics = fetch_acs_data(CENSUS_API_KEY)

    # Step C: Merge on 11-digit GEOID
    print("Merging spatial boundaries with ACS health metrics...")
    merged_df = df_metrics.merge(gdf_boundaries, on="GEOID", how="inner")

    # Step D: Save output
    output_csv = "Delaware_Tract_Health_Data_Programmatic.csv"
    df_metrics.to_csv(output_csv, index=False)
    print(f"Successfully generated {output_csv} ({len(df_metrics)} tracts).")

    # Optional GeoJSON export with spatial boundaries embedded
    output_geojson = "Delaware_Tracts_Spatial_Health.geojson"
    gdf_merged = gdf_boundaries.merge(df_metrics, on="GEOID", how="inner")
    gdf_merged.to_file(output_geojson, driver="GeoJSON")
    print(f"Successfully generated {output_geojson} for spatial mapping.")


if __name__ == "__main__":
    main()