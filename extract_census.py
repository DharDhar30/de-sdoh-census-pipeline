import os
import requests
import pandas as pd
import geopandas as gpd
import pygris
from dotenv import load_dotenv

# Per-column provenance (which raw source each measure comes from and at what
# true geography) - see sector_definitions.SECTOR_SOURCES and raw/SOURCES.md.
from sector_definitions import provenance_rows

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

# BRFSS state-level indicators pulled from the CDC BRFSS Prevalence dataset
# (Chronic disease / PUBLIC HEALTH measures only - no demographics, education,
# employment, income, or commute noise).
BRFSS_MEASURES = [
    ("BRFSS_Pct_Cigarette_Smoking", "Adults who are current smokers", "Yes"),
    ("BRFSS_Pct_Smoke_Every_Day", "Four Level Smoking Status", "Smoke everyday"),
    ("BRFSS_Pct_Ecigarette_Use", "Adults who are current e-cigarette users", "Current E-cigarette user"),
    ("BRFSS_Pct_Binge_Drinking", "Binge drinkers", "Yes"),
    ("BRFSS_Pct_Heavy_Drinking", "Heavy drinkers", "Meet criteria for heavy drinking"),
    ("BRFSS_Pct_Adult_Obesity", "Weight classification by Body Mass Index", "Obese (BMI 30.0 - 99.8)"),
    ("BRFSS_Pct_Adult_Overweight", "Weight classification by Body Mass Index", "Overweight (BMI 25.0-29.9)"),
    ("BRFSS_Pct_No_Physical_Activity", "During the past month, did you participate in any physical activities", "No"),
    ("BRFSS_Pct_Arthritis", "Adults who have been told they have arthritis", "Yes"),
    ("BRFSS_Pct_Current_Asthma", "Adults who have been told they currently have asthma", "Yes"),
    ("BRFSS_Pct_Ever_Asthma", "Adults who have ever been told they have asthma", "Yes"),
    ("BRFSS_Pct_COPD", "Ever told you have COPD?", "Yes"),
    ("BRFSS_Pct_Coronary_Heart_Disease", "Respondents that have ever reported having coronary heart disease", "Reported having MI or CHD"),
    ("BRFSS_Pct_Had_Stroke", "Ever told you had a stroke?", "Yes"),
    ("BRFSS_Pct_Diabetes", "Have you ever been told by a doctor that you have diabetes?", "Yes"),
    ("BRFSS_Pct_Kidney_Disease", "Ever told you have kidney disease?", "Yes"),
    ("BRFSS_Pct_Depression", "Ever told you that you have a form of depression?", "Yes"),
    ("BRFSS_Pct_Skin_Cancer", "Ever told you had skin cancer?", "Yes"),
    ("BRFSS_Pct_Other_Cancer", "Ever told you had any other types of cancer?", "Yes"),
    ("BRFSS_Pct_Fair_Poor_Health", "Health Status", "Fair or Poor Health"),
    ("BRFSS_Pct_Frequent_Mental_Distress", "Days when mental health status not good", "14+ days when mental health not good"),
    ("BRFSS_Pct_Frequent_Physical_Distress", "Days when physical health status not good", "14+ days when physical health not good"),
    ("BRFSS_Pct_Uninsured", "Adults who had some form of health insurance", "Do not have some form of health insurance"),
    ("BRFSS_Pct_Uninsured_18_64", "Adults aged 18-64 who have any kind of health care coverage", "Do not have some form of health insurance"),
    ("BRFSS_Pct_Cost_Barrier_Medical_Care", "Was there a time in the past 12 months when you needed to see a doctor", "Yes"),
    ("BRFSS_Pct_No_Personal_Doctor", "Do you have one person (or a group of doctors)", "No"),
    ("BRFSS_Pct_Routine_Checkup_Past_Year", "About how long has it been since you last visited a doctor for a routine checkup?", "Within the past year"),
    ("BRFSS_Pct_Colorectal_Screening_45_75", "Respondents aged 45-75 who have fully met the USPSTF recommendation", "Received one or more of the recommended CRC tests within the recommended time interval"),
    ("BRFSS_Pct_Mammography_40_74", "Women aged 40-74 who have had a mammogram within the past two years", "Received a mammogram within the past 2 years"),
    ("BRFSS_Pct_Flu_Vaccinated_65_Plus", "Adults aged 65+ who have had a flu shot within the past year", "Yes"),
    ("BRFSS_Pct_Pneumonia_Vaccinated_65_Plus", "Adults aged 65+ who have ever had a pneumonia vaccination", "Yes"),
    ("BRFSS_Pct_HIV_Tested_Ever", "Have you ever been tested for HIV?", "Yes"),
    ("BRFSS_Pct_Permanent_Teeth_Removed", "Adults that have had any permanent teeth extracted", "Yes"),
    ("BRFSS_Pct_All_Teeth_Removed_65_Plus", "Adults aged 65+ who have had all their natural teeth extracted", "Yes"),
    ("BRFSS_Pct_Walking_Difficulty", "Do you have serious difficulty walking or climbing stairs?", "Yes"),
    ("BRFSS_Pct_Seeing_Difficulty", "Are you blind or do you have serious difficulty seeing", "Yes"),
    ("BRFSS_Pct_Cognitive_Difficulty", "Do you have serious difficulty concentrating, remembering, or making decisions?", "Yes"),
]

# ---------------------------------------------------------------------------
# 2. SPATIAL BOUNDARIES (PYGRIS)
# ---------------------------------------------------------------------------
# Delaware ZIPs are exactly 197xx / 198xx / 199xx.
DE_ZCTA_PREFIXES = ("197", "198", "199")


def _de_zctas_only(de_zctas, zcta_col: str):
    """Restrict clipped ZCTA polygons to ZCTAs that genuinely belong to Delaware.

    ``gpd.clip`` to the Delaware state boundary keeps any ZCTA that *touches*
    Delaware, and border ZCTAs retain their full multi-state polygon. Delaware's
    north-east corner touches Maryland and Pennsylvania, so 30 MD/PA/NJ ZCTAs
    (including 21921 / Annapolis, MD) survived the clip and their ACS
    populations were merged into the master, inflating Delaware's total
    population by ~21%. Two filters are required together:

    1. the ZCTA's centroid must fall inside the Delaware state polygon; and
    2. the ZCTA's ZIP must be a Delaware ZIP (197/198/199).

    Filter 1 alone is not sufficient; filter 2 alone would keep ZCTAs that are
    Delaware ZIPs but whose centroid the clip moved.
    """
    projected = de_zctas.to_crs(epsg=3857)
    centroids = projected.set_geometry(projected.geometry.centroid)
    de_state = pygris.states(cb=True, resolution="20m").query("STUSPS == 'DE'")
    if de_state.crs != centroids.crs:
        de_state = de_state.to_crs(centroids.crs)
    inside = gpd.sjoin(
        centroids, de_state[["geometry"]], how="left", predicate="within"
    )
    keep = inside.dropna(subset=["index_right"]).index.unique()

    out = de_zctas.loc[de_zctas.index.intersection(keep)].copy()
    before = len(out)
    out = out.loc[out[zcta_col].astype(str).str.zfill(5).str.startswith(DE_ZCTA_PREFIXES)]
    dropped = before - len(out)
    if dropped:
        print(f"  Dropped {dropped} non-Delaware ZCTAs (centroid inside DE, ZIP not 197/198/199).")
    if out.empty:
        raise RuntimeError("The Delaware ZCTA filter removed every ZCTA; aborting.")
    return out


def fetch_spatial_boundaries():
    """Downloads Delaware state & ZCTA boundaries and computes area metrics."""
    print("Fetching spatial boundaries via pygris...")
    de_state = pygris.states(cb=True, resolution="20m").query("STUSPS == 'DE'")
    zctas = pygris.zctas(year=2020, cb=True)
    
    if zctas.crs != de_state.crs:
        zctas = zctas.to_crs(de_state.crs)
        
    de_zctas = gpd.clip(zctas, de_state)
    
    aland_col = "ALAND20" if "ALAND20" in de_zctas.columns else "ALAND"
    awater_col = "AWATER20" if "AWATER20" in de_zctas.columns else "AWATER"
    zcta_col = "ZCTA5CE20" if "ZCTA5CE20" in de_zctas.columns else ("GEOID20" if "GEOID20" in de_zctas.columns else "GEOID")
    
    de_zctas = de_zctas[de_zctas[aland_col] > 0].copy()
    # Drop out-of-state border ZCTAs before any population is attached.
    de_zctas = _de_zctas_only(de_zctas, zcta_col)
    de_zctas["ZCTA"] = de_zctas[zcta_col].astype(str).str.zfill(5)
    de_zctas["Land_Area_SqMi"] = de_zctas[aland_col] / 2589988.11
    de_zctas["Water_Area_SqMi"] = de_zctas[awater_col] / 2589988.11
    
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
# 2b. CDC PLACES ZCTA-LEVEL CHRONIC DISEASE (model-based estimates)
# ---------------------------------------------------------------------------
# PLACES publishes SEPARATE datasets per geography: place/city, county,
# census-tract and ZCTA. The ZCTA release is the one that shares this master's
# geography, so chronic-disease measures land on the same ZCTA rows as the ACS
# demographics instead of being broadcast from a city or county geography.
PLACES_ZCTA_URL = "https://data.cdc.gov/resource/4r2x-hcfq.json"
PLACES_ZCTA_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "raw", "cdc_places_2024_de_zcta_raw.csv"
)


def load_places_zcta(filepath: str = PLACES_ZCTA_SNAPSHOT) -> pd.DataFrame:
    """Wide ZCTA-level chronic-disease estimates from the archived PLACES snapshot.

    Returns one row per ZCTA with a ``PLACES_Pct_*`` column per measure plus its
    confidence limits. Values are the publisher's model-based estimates
    (BRFSS-derived, small-area modelled) - they are NOT direct counts, so the
    confidence limits published alongside them are carried through.
    """
    from fetch_places import MEASURE_COLUMNS

    print("Loading CDC PLACES ZCTA-level chronic disease estimates...")
    if not os.path.exists(filepath):
        print(f"  WARNING: {filepath} not found - run "
              "`python3 fetch_raw_data.py --only cdc_places_2024_de_zcta` first.")
        return pd.DataFrame(columns=["ZCTA"])

    raw = pd.read_csv(filepath, low_memory=False)
    raw = raw[raw["measure"].isin(MEASURE_COLUMNS.keys())].copy()
    for col in ("data_value", "low_confidence_limit", "high_confidence_limit"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")

    raw["ZCTA"] = raw["locationname"].astype(str).str.zfill(5)

    wide = raw.pivot_table(
        index="ZCTA", columns="measure", values="data_value", aggfunc="first"
    )
    out = pd.DataFrame(index=wide.index)
    # Build every column first, then assign once - assigning 120 columns one at
    # a time leaves the frame highly fragmented and triggers pandas warnings.
    value_cols, ci_low_cols, ci_high_cols = {}, {}, {}
    for measure, col_name in MEASURE_COLUMNS.items():
        if measure not in wide.columns:
            continue
        value_cols[col_name] = wide[measure]
        subset = raw[raw["measure"] == measure].set_index("ZCTA")
        ci_low_cols[f"{col_name}_CI_Low"] = out.index.to_series().map(
            subset["low_confidence_limit"]
        )
        ci_high_cols[f"{col_name}_CI_High"] = out.index.to_series().map(
            subset["high_confidence_limit"]
        )
    out = pd.concat(
        [pd.DataFrame(value_cols), pd.DataFrame(ci_low_cols), pd.DataFrame(ci_high_cols)],
        axis=1,
    )

    out = out.reset_index()
    measures = [c for c in out.columns if c.startswith("PLACES_Pct_") and not c.endswith(("_CI_Low", "_CI_High"))]
    print(f"  {len(out)} ZCTAs x {len(measures)} PLACES measures")
    return out

# ---------------------------------------------------------------------------
# 3. CENSUS ACS DEMOGRAPHIC DATA API
# ---------------------------------------------------------------------------
def fetch_acs_data(api_key):
    """Fetches 5-Year ACS profile metrics from the Census API (2024 5-year)."""
    print("Fetching Census ACS 2024 5-Year demographic metrics...")
    var_string = ",".join(ACS_VARS.keys())
    url = f"https://api.census.gov/data/2024/acs/acs5/profile?get={var_string}&for=zip%20code%20tabulation%20area:*&key={api_key}"
    
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
    """Loads County Health Rankings dataset (medical / public-health outcomes,
    behaviors, and clinical-care measures only).

    Reads exclusively from the bundled CHR_Delaware.csv, which is generated
    from the official County Health Rankings & Roadmaps 2025 release
    (see gen_health_data.py for the full reproducible download script).
    """
    print("Loading County Health Rankings (CHR) 2025 metrics...")
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"{filepath} not found. Run gen_health_data.py first to download "
            "the official County Health Rankings 2025 data."
        )
    chr_df = pd.read_csv(filepath)
    chr_df["County_FIPS"] = chr_df["County_FIPS"].astype(str).str.zfill(5)
    return chr_df


# ---------------------------------------------------------------------------
# 4b. CDC BRFSS STATE-LEVEL PREVALENCE (2024)
# ---------------------------------------------------------------------------
BRFSS_CSV_PATH = "BRFSS_Delaware.csv"
BRFSS_API_URL = (
    "https://chronicdata.cdc.gov/resource/dttw-5yxu.csv"
    "?$where=locationabbr='DE' and break_out_category='Overall' and year=2024"
    "&$limit=10000"
)


def _brfss_row_from_api() -> dict:
    """Fetch Delaware overall-prevalence rows from the live CDC BRFSS API and
    build a single state-level record matching the bundled BRFSS_Delaware.csv."""
    print("Fetching CDC BRFSS 2024 Delaware prevalence from API...")
    response = requests.get(BRFSS_API_URL, timeout=120)
    response.raise_for_status()
    import io

    df = pd.read_csv(io.StringIO(response.text))
    df.columns = [c.lower() for c in df.columns]
    out = {"State": "Delaware", "BRFSS_Year": 2024}
    problems = []
    for name, qsub, resp_exact in BRFSS_MEASURES:
        q = df["question"].fillna("").astype(str).str.contains(qsub, case=False, regex=False)
        r = df["response"].fillna("").astype(str).str.strip().str.lower().eq(resp_exact.lower())
        hits = df[q & r]
        if len(hits) != 1:
            problems.append((name, len(hits)))
            continue
        row = hits.iloc[0]
        out[f"{name}_Sample_Size"] = int(row["sample_size"])
        for suffix, src in (
            ("", "data_value"),
            ("_CI_Low", "confidence_limit_low"),
            ("_CI_High", "confidence_limit_high"),
        ):
            out[f"{name}{suffix}"] = round(float(row[src]), 1)
    if problems:
        raise ValueError(f"BRFSS API extract incomplete for: {problems}")
    return out


def fetch_brfss_state_data() -> pd.DataFrame:
    """Return the Delaware state-level BRFSS 2024 record as a one-row frame.

    Uses the bundled BRFSS_Delaware.csv when available; otherwise pulls the
    same figures directly from the CDC BRFSS Prevalence API.
    """
    if os.path.exists(BRFSS_CSV_PATH):
        print("Loading CDC BRFSS 2024 Delaware state prevalence...")
        return pd.read_csv(BRFSS_CSV_PATH)
    return pd.DataFrame([_brfss_row_from_api()])

# ---------------------------------------------------------------------------
# 5. MAIN ETL WORKFLOW & EXPORT
# ---------------------------------------------------------------------------
def main():
    spatial_gdf = fetch_spatial_boundaries()
    acs_df = fetch_acs_data(CENSUS_API_KEY)
    chr_df = load_county_health_rankings()
    brfss_df = fetch_brfss_state_data()
    places_df = load_places_zcta()
    
    master_gdf = spatial_gdf.merge(acs_df, on="ZCTA", how="inner")
    
    master_gdf = master_gdf.merge(chr_df.drop(columns=["County_Name"], errors="ignore"), on="County_FIPS", how="left")

    # BRFSS is a single state-level record: broadcast every indicator to all ZCTA
    # rows so maps still work, and keep the state key explicit in the output.
    master_gdf["State"] = "Delaware"
    master_gdf = master_gdf.merge(brfss_df, on="State", how="left")
    master_gdf = master_gdf.drop(columns=["State"])

    # PLACES ZCTA: genuinely ZCTA-level model-based chronic-disease estimates.
    # Merged with how="left" so ZCTAs PLACES does not cover keep a NULL measure
    # rather than being dropped from the master.
    places_cols = [c for c in places_df.columns if c != "ZCTA"]
    if places_cols:
        master_gdf = master_gdf.merge(places_df, on="ZCTA", how="left")
        missing = master_gdf.loc[master_gdf[places_cols[0]].isna(), "ZCTA"].tolist()
        if missing:
            print(f"  NOTE: PLACES has no ZCTA estimate for {len(missing)} ZCTA(s): "
                  f"{', '.join(missing)} - their PLACES measures are NULL.")


    master_gdf["Population_Density_SqMi"] = (master_gdf["Total_Population"] / master_gdf["Land_Area_SqMi"]).round(2)
    master_gdf["Uninsured_Population_Count"] = ((master_gdf["Pct_No_Health_Insurance"] / 100) * master_gdf["Total_Population"]).round(0)
    master_gdf["Poverty_Population_Count"] = ((master_gdf["Pct_Below_Poverty"] / 100) * master_gdf["Total_Population"]).round(0)
    master_gdf["Seniors_65_Plus_Count"] = ((master_gdf["Pct_Age_65_Plus"] / 100) * master_gdf["Total_Population"]).round(0)
    master_gdf["No_Broadband_Households_Estimate"] = (
        ((100 - master_gdf["Pct_Broadband_Internet"]) / 100) * master_gdf["Total_Population"]
    ).round(0)


    print("Exporting updated master datasets...")
    tabular_df = pd.DataFrame(master_gdf.drop(columns=["geometry"]))

    # Provenance: the true geography of every measure. Only ACS + TIGER are
    # genuinely ZCTA-level; BRFSS is a statewide survey and CHR reports by
    # county, so those columns are broadcast onto ZCTA rows. Users who want
    # ZCTA-only measures filter on Geography_Level == "ZCTA".
    provenance_df = pd.DataFrame(provenance_rows(list(tabular_df.columns)))
    provenance_path = "Delaware_ZCTA_Health_Master_Column_Provenance.csv"
    provenance_df.to_csv(provenance_path, index=False)

    tabular_df.to_csv("Delaware_ZCTA_Health_Master_Wide.csv", index=False)
    with pd.ExcelWriter("Delaware_ZCTA_Health_Master_Wide.xlsx") as writer:
        tabular_df.to_excel(writer, sheet_name="Master", index=False)
        provenance_df.to_excel(writer, sheet_name="Column_Provenance", index=False)

    master_gdf.to_file("Delaware_ZCTA_Health_Master_Spatial.geojson", driver="GeoJSON")
    print(f"Wrote {provenance_path} ({len(provenance_df)} columns classified)")
    print("Successfully exported all files with County Health Rankings added!")

if __name__ == "__main__":
    main()