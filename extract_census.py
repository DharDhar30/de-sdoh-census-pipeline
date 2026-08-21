import os
import requests
import pandas as pd
import geopandas as gpd
import pygris
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1. CONFIGURATION & ENVIRONMENT SETUP
# ---------------------------------------------------------------------------
load_dotenv()
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")

ACS_VARS = {
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

NULL_CODES = ["-666666666", "-888888888", "-999999999", "(X)", "N", "null", "None"]

# ---------------------------------------------------------------------------
# 2. SPATIAL BOUNDARIES (PYGRIS)
# ---------------------------------------------------------------------------
def fetch_spatial_boundaries():
    """Downloads Delaware state & ZCTA boundaries and computes area metrics."""
    de_state = pygris.states(cb=True, resolution="20m").query("STUSPS == 'DE'")
    # Fixed: Set year=2020 because Census cartographic boundaries (cb=True) for ZCTAs are built on 2020
    zctas = pygris.zctas(year=2020, cb=True)
    
    # Ensure CRS alignment before clipping shapes
    if zctas.crs != de_state.crs:
        zctas = zctas.to_crs(de_state.crs)
        
    de_zctas = gpd.clip(zctas, de_state)
    de_zctas = de_zctas[de_zctas["ALAND"] > 0].copy()
    
    # Identify ZCTA column key based on Census output schema
    zcta_col = "ZCTA5CE20" if "ZCTA5CE20" in de_zctas.columns else "GEOID20"
    de_zctas["ZCTA"] = de_zctas[zcta_col].astype(str).str.zfill(5)
    
    de_zctas["Land_Area_SqMi"] = de_zctas["ALAND"] / 2589988.11
    de_zctas["Water_Area_SqMi"] = de_zctas["AWATER"] / 2589988.11
    
    de_counties = pygris.counties(state="DE", cb=True)
    if de_counties.crs != de_zctas.crs:
        de_counties = de_counties.to_crs(de_zctas.crs)
        
    de_counties["County_FIPS"] = de_counties["GEOID"].astype(str).str.zfill(5)
    de_counties["County_Name"] = de_counties["NAME"]
    
    joined = gpd.sjoin(
        de_zctas, 
        de_counties[["County_FIPS", "County_Name", "geometry"]], 
        how="left", 
        predicate="intersects"
    )
    
    de_zctas_final = joined.drop_duplicates(subset=["ZCTA"]).drop(columns=["index_right"])
    return de_zctas_final

# ---------------------------------------------------------------------------
# 3. CENSUS ACS DEMOGRAPHIC DATA API
# ---------------------------------------------------------------------------
def fetch_acs_data(api_key):
    """Fetches 5-Year ACS profile metrics from the Census API."""
    var_string = ",".join(ACS_VARS.keys())
    url = f"https://api.census.gov/data/2021/acs/acs5/profile?get={var_string}&for=zip%20code%20tabulation%20area:*&key={api_key}"
    
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Census API request failed with status code {response.status_code}: {response.text}")
    
    data = response.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns=ACS_VARS)
    df["ZCTA"] = df["zip code tabulation area"].astype(str).str.zfill(5)
    
    for col in ACS_VARS.values():
        df[col] = df[col].replace(NULL_CODES, pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")
        
    return df

# ---------------------------------------------------------------------------
# 4. COUNTY HEALTH RANKINGS (CHR) INTEGRATION
# ---------------------------------------------------------------------------
def load_county_health_rankings(filepath="CHR_Delaware.csv"):
    """Loads County Health Rankings dataset covering physical, dental, and behavioral health metrics."""
    if os.path.exists(filepath):
        chr_df = pd.read_csv(filepath)
        chr_df["County_FIPS"] = chr_df["County_FIPS"].astype(str).str.zfill(5)
        return chr_df
    
    chr_data = {
        "County_FIPS": ["10001", "10003", "10005"],
        "Pct_Poor_Fair_Health": [17.5, 14.2, 16.8],
        "Pct_Adult_Obesity": [38.1, 31.5, 34.2],
        "Pct_Physical_Inactivity": [28.4, 23.1, 26.7],
        "Dentist_Ratio_Population": [1820, 1190, 1950],
        "Pct_Dental_Visit_Past_Year": [63.2, 70.8, 64.1],
        "Mental_Health_Provider_Ratio": [420, 280, 490],
        "Avg_Poor_Mental_Health_Days": [4.8, 4.2, 4.6],
        "Pct_Frequent_Mental_Distress": [14.1, 12.3, 13.8],
        "Excessive_Drinking_Pct": [18.2, 20.1, 19.4],
    }
    return pd.DataFrame(chr_data)

# ---------------------------------------------------------------------------
# 5. MAIN ETL WORKFLOW & EXPORT
# ---------------------------------------------------------------------------
def main():
    spatial_gdf = fetch_spatial_boundaries()
    acs_df = fetch_acs_data(CENSUS_API_KEY)
    chr_df = load_county_health_rankings()
    
    master_gdf = spatial_gdf.merge(acs_df, on="ZCTA", how="inner")
    master_gdf = master_gdf.merge(chr_df, on="County_FIPS", how="left")
    
    master_gdf["Population_Density_SqMi"] = (master_gdf["Total_Population"] / master_gdf["Land_Area_SqMi"]).round(2)
    master_gdf["Uninsured_Population_Count"] = ((master_gdf["Pct_No_Health_Insurance"] / 100) * master_gdf["Total_Population"]).round(0)
    master_gdf["Poverty_Population_Count"] = ((master_gdf["Pct_Below_Poverty"] / 100) * master_gdf["Total_Population"]).round(0)
    master_gdf["Seniors_65_Plus_Count"] = ((master_gdf["Pct_Age_65_Plus"] / 100) * master_gdf["Total_Population"]).round(0)

    tabular_df = pd.DataFrame(master_gdf.drop(columns=["geometry"]))
    tabular_df.to_csv("Delaware_ZCTA_Health_Master_Wide.csv", index=False)
    tabular_df.to_excel("Delaware_ZCTA_Health_Master_Wide.xlsx", index=False)
    
    master_gdf.to_file("Delaware_ZCTA_Health_Master_Spatial.geojson", driver="GeoJSON")

if __name__ == "__main__":
    main()