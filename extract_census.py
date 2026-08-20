import os
import geopandas as gpd
import pandas as pd
import pygris
import requests
from dotenv import load_dotenv

load_dotenv()
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

if not CENSUS_API_KEY:
    raise SystemExit("CENSUS_API_KEY not found!")

STATE_FIPS = "10"
STATE_ABBR = "DE"
YEAR = 2022

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
    # Load Delaware state boundary for spatial filtering
    de_boundary = pygris.states(cb=True, year=2020, cache=True)
    de_boundary = de_boundary[de_boundary["STATEFP"] == STATE_FIPS]

    # Download national ZCTAs and spatially clip to Delaware
    all_zctas = pygris.zctas(year=2020, cache=True)
    de_zctas = gpd.clip(all_zctas, de_boundary)

    # Filter out pure-water geometries
    de_zctas["ALAND"] = pd.to_numeric(de_zctas["ALAND20"], errors="coerce")
    de_zctas = de_zctas[de_zctas["ALAND"] > 0].copy()

    # Standardize ZCTA column name
    de_zctas["ZCTA"] = de_zctas["ZCTA5CE20"].astype(str).str.zfill(5)

    return de_zctas[["ZCTA", "ALAND", "AWATER20", "geometry"]].rename(
        columns={"AWATER20": "AWATER"}
    )


def fetch_acs_data(api_key: str):
    var_list = ",".join(VARIABLE_MAP.keys())
    url = f"https://api.census.gov/data/{YEAR}/acs/acs5/profile"

    params = {
        "get": f"NAME,{var_list}",
        "for": "zip code tabulation area:*",
        "key": api_key,
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"\nCensus API Error ({response.status_code}):\n{response.text}")
        raise SystemExit("Please check your CENSUS_API_KEY and parameters.")

    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])

    df["ZCTA"] = df["zip code tabulation area"].astype(str).str.zfill(5)
    df = df.rename(columns=VARIABLE_MAP)

    metric_cols = list(VARIABLE_MAP.values())
    for col in metric_cols:
        df[col] = df[col].replace(NULL_CODES, pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[["ZCTA"] + metric_cols]


def main():
    gdf_boundaries = fetch_spatial_boundaries()
    df_metrics = fetch_acs_data(CENSUS_API_KEY)

    master_gdf = gdf_boundaries.merge(df_metrics, on="ZCTA", how="inner")

    output_csv = "Delaware_ZCTA_Health_Data_Master.csv"
    master_gdf.drop(columns=["geometry"]).to_csv(output_csv, index=False)
    print(f"Generated {output_csv} ({len(master_gdf)} ZCTAs).")

    output_geojson = "Delaware_ZCTA_Spatial_Health_Master.geojson"
    master_gdf.to_file(output_geojson, driver="GeoJSON")
    print(f"Generated {output_geojson}.")


if __name__ == "__main__":
    main()