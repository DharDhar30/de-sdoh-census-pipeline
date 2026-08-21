import os
import geopandas as gpd
import pandas as pd
import pygris
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# CONFIGURATION & SETUP
# ---------------------------------------------------------------------------
load_dotenv()
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

if not CENSUS_API_KEY:
    raise SystemExit("CENSUS_API_KEY not found! Please check your .env file.")

STATE_FIPS = "10"  
STATE_ABBR = "DE"
YEAR = 2022

# Standardizing ACS API keys to descriptive Tableau field names
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

# Known Census sentinel/null values to suppress
NULL_CODES = [
    "-", "**", "***", "(X)", "N", "null", 
    "-666666666", -666666666, -666666666.0,
    "-888888888", -888888888, -888888888.0,
    "-999999999", -999999999, -999999999.0
]


# ---------------------------------------------------------------------------
# 1. SPATIAL GEOMETRY PROCESSING
# ---------------------------------------------------------------------------
def fetch_spatial_boundaries():
    print("Downloading Delaware boundary & National ZCTA map...")
    de_boundary = pygris.states(cb=True, year=2020, cache=True)
    de_boundary = de_boundary[de_boundary["STATEFP"] == STATE_FIPS]

    all_zctas = pygris.zctas(year=2020, cache=True)
    
    print("Clipping ZCTAs to Delaware and dropping water tracts...")
    de_zctas = gpd.clip(all_zctas, de_boundary)

    # Clean map: Exclude pure-water geometries
    de_zctas["ALAND"] = pd.to_numeric(de_zctas["ALAND20"], errors="coerce").fillna(0)
    de_zctas = de_zctas[de_zctas["ALAND"] > 0].copy()

    # Standardize 5-digit ZCTA string code
    de_zctas["ZCTA"] = de_zctas["ZCTA5CE20"].astype(str).str.zfill(5)
    de_zctas["AWATER"] = pd.to_numeric(de_zctas["AWATER20"], errors="coerce").fillna(0)

    return de_zctas[["ZCTA", "ALAND", "AWATER", "geometry"]]


# ---------------------------------------------------------------------------
# 2. ACS CENSUS DATA EXTRACTION
# ---------------------------------------------------------------------------
def fetch_acs_data(api_key: str):
    print("Extracting ACS Data Profile metrics...")
    var_list = ",".join(VARIABLE_MAP.keys())
    url = f"https://api.census.gov/data/{YEAR}/acs/acs5/profile"

    params = {
        "get": f"NAME,{var_list}",
        "for": "zip code tabulation area:*",
        "key": api_key,
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise SystemExit(f"Census API Error ({response.status_code}): {response.text}")

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])

    # Standardize ZCTA format
    df["ZCTA"] = df["zip code tabulation area"].astype(str).str.zfill(5)
    df = df.rename(columns=VARIABLE_MAP)

    # Sanitize null values and cast metrics to numeric
    metric_cols = list(VARIABLE_MAP.values())
    for col in metric_cols:
        df[col] = df[col].replace(NULL_CODES, pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[["ZCTA"] + metric_cols]


# ---------------------------------------------------------------------------
# 3. PYTHON-SIDE CALCULATIONS & TABLEAU WIDE MASTER BUILD
# ---------------------------------------------------------------------------
def main():
    gdf_boundaries = fetch_spatial_boundaries()
    df_metrics = fetch_acs_data(CENSUS_API_KEY)

    print("Merging spatial data with ACS metrics...")
    master_gdf = gdf_boundaries.merge(df_metrics, on="ZCTA", how="inner")

    print("Executing Python-side transformations and metric calculations...")
    
    # 1. Convert square meters (ALAND) to square miles for easy density calculations
    master_gdf["Land_Area_SqMi"] = (master_gdf["ALAND"] / 2_589_988.110336).round(2)
    master_gdf["Water_Area_SqMi"] = (master_gdf["AWATER"] / 2_589_988.110336).round(2)

    # 2. Derive estimated population counts to avoid Tableau calculations
    master_gdf["Population_Density_SqMi"] = (
        master_gdf["Total_Population"] / master_gdf["Land_Area_SqMi"]
    ).round(1)

    master_gdf["Uninsured_Population_Count"] = (
        (master_gdf["Pct_No_Health_Insurance"] / 100) * master_gdf["Total_Population"]
    ).round(0)

    master_gdf["Poverty_Population_Count"] = (
        (master_gdf["Pct_Below_Poverty"] / 100) * master_gdf["Total_Population"]
    ).round(0)

    master_gdf["Seniors_65_Plus_Count"] = (
        (master_gdf["Pct_Age_65_Plus"] / 100) * master_gdf["Total_Population"]
    ).round(0)

    numeric_cols = master_gdf.select_dtypes(include=["number"]).columns
    for col in numeric_cols:
        master_gdf[col] = master_gdf[col].apply(lambda x: pd.NA if x in NULL_CODES else x)

    # 4. Export Wide CSV
    output_csv = "Delaware_ZCTA_Health_Master_Wide.csv"
    df_out = master_gdf.drop(columns=["geometry"])
    df_out.to_csv(output_csv, index=False)
    print(f"--> Saved Wide Master CSV: {output_csv} ({len(df_out)} rows)")

    # 5. Export Spatial GeoJSON
    output_geojson = "Delaware_ZCTA_Health_Master_Spatial.geojson"
    master_gdf.to_file(output_geojson, driver="GeoJSON")
    print(f"--> Saved Master GeoJSON: {output_geojson}")


if __name__ == "__main__":
    main()