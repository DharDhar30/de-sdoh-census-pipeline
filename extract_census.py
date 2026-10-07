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
    # --- ZCTA-master display columns (kept stable so the app/Tableau keep working)
    "DP05_0001E": "Total_Population",
    "DP05_0018E": "Median_Age",
    "DP05_0024PE": "Pct_Age_65_Plus",
    "DP03_0062E": "Median_Household_Income",
    "DP03_0128PE": "Pct_Below_Poverty",
    "DP03_0099PE": "Pct_No_Health_Insurance",
    "DP03_0021PE": "Pct_Commute_Public_Transit",
    "DP02_0154PE": "Pct_Broadband_Internet",
    "DP02_0114PE": "Pct_NonEnglish_Language_Home",
    # --- Published counts + denominators (Issue 7: never back-calculate from
    # percentages). S1701_C02_001E/C01_001E the poverty count + universe
    # (DP03_0128E only duplicates the percent); DP03_0095E/DP03_0099E the
    # insurance universe/count; DP02_0152E/DP02_0154E broadband universe/count;
    # DP03_0018E/DP03_0021E commute universe/count; DP02_0113E/DP02_0114E the
    # language universe/count; DP05_0024E the 65+ count.
    "DP05_0024E": "Count_Age_65_Plus",
    "DP03_0095E": "Count_Insurance_Universe",
    "DP03_0099E": "Count_No_Health_Insurance",
    "DP03_0018E": "Count_Workers_16_Plus",
    "DP03_0021E": "Count_Commute_Public_Transit",
    "DP02_0152E": "Count_Households_Broadband_Universe",
    "DP02_0154E": "Count_Broadband_Internet",
    "DP02_0113E": "Count_English_Only_5Plus",
    "DP02_0114E": "Count_NonEnglish_Language_Home",
    "DP02_0001E": "Count_Total_Households",
    # NOTE: DP03_0128E intentionally NOT mapped - it duplicates the poverty
    # percent (and is suppressed at ZCTA level). Counts come from S1701.
}

# Census missing-value sentinels. The API returns them as *numbers* (e.g.
# -666666666), so they must be masked AFTER pd.to_numeric, not by string
# match. Any value <= -111111111 is a sentinel (covers -666666666,
# -888888888, -999999999, -222222222, -333333333, -555555555).
CENSUS_SENTINEL_MAX = -111111111
NULL_CODES = ["(X)", "N", "null", "None"]

# NOTE (mentor issue #5): BRFSS lives in the standalone state table
# (BRFSS_Delaware.csv, built by gen_health_data.py) and is never merged onto
# ZCTA rows. The BRFSS_MEASURES query spec below was retired with the
# broadcast helpers; the canonical spec is gen_health_data.BRFSS_MEASURES.

# ---------------------------------------------------------------------------
# 2. SPATIAL BOUNDARIES (PYGRIS)
# ---------------------------------------------------------------------------
# Delaware ZIPs are exactly 197xx / 198xx / 199xx.
DE_ZCTA_PREFIXES = ("197", "198", "199")

# 2020 Census ZCTA-to-county relationship file (archived in raw/). The
# authoritative source for "which ZCTAs belong to Delaware" and "which county
# is each ZCTA primarily in" (Issues 1+2). Never assign counties from ZIP
# prefixes, hand-made lists, or spatial intersects.
ZCTA_COUNTY_REL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "raw", "census_zcta_county_rel_2020_raw.txt"
)
DE_COUNTY_FIPS = ("10001", "10003", "10005")


def load_zcta_county_crosswalk(rel_path: str = ZCTA_COUNTY_REL_PATH) -> pd.DataFrame:
    """Primary-county assignment from the 2020 Census relationship file.

    Returns one row per ZCTA whose LARGEST land-area share lies in a Delaware
    county: ZCTA, County_FIPS, County_Name, primary_share, multi_county flag.
    ZCTAs such as 19952/19977/19938/19950/19963 span >1 county and are
    flagged; their county is the largest-share one (19952 -> Kent, not
    Sussex; 19734 -> New Castle, not Kent).
    """
    rel = pd.read_csv(rel_path, sep="|", dtype=str)
    rel["AREALAND_PART"] = pd.to_numeric(rel["AREALAND_PART"], errors="coerce")
    # Largest-share county per ZCTA, nationally first (so out-of-state ZCTAs
    # like 21842/08014/19350 resolve to their true home county, not Delaware).
    idx = rel.groupby("GEOID_ZCTA5_20")["AREALAND_PART"].idxmax()
    primary = rel.loc[idx].copy()
    primary = primary.rename(
        columns={"GEOID_ZCTA5_20": "ZCTA", "GEOID_COUNTY_20": "County_FIPS"}
    )
    primary["ZCTA"] = primary["ZCTA"].astype(str).str.zfill(5)
    primary["County_FIPS"] = primary["County_FIPS"].astype(str).str.zfill(5)
    # Multi-county flag: ZCTAs appearing on >1 county row.
    n_counties = rel.groupby("GEOID_ZCTA5_20").size()
    primary["multi_county"] = primary["ZCTA"].map(n_counties) > 1
    # Land-area share of the primary county within the ZCTA.
    zcta_land = rel.groupby("GEOID_ZCTA5_20")["AREALAND_PART"].sum()
    primary["primary_share"] = primary.apply(
        lambda r: (r["AREALAND_PART"] / zcta_land.get(r["ZCTA"], float("nan"))),
        axis=1,
    )
    fips_to_name = {"10001": "Kent", "10003": "New Castle", "10005": "Sussex"}
    primary["County_Name"] = primary["County_FIPS"].map(fips_to_name).fillna(
        primary["NAMELSAD_COUNTY_20"].str.replace(" County", "", regex=False).str.strip()
    )
    de = primary[primary["County_FIPS"].isin(DE_COUNTY_FIPS)].copy()
    return de[["ZCTA", "County_FIPS", "County_Name", "primary_share", "multi_county"]]


def _de_zctas_only(de_zctas, zcta_col: str):
    """Restrict clipped ZCTA polygons to true Delaware ZCTAs (Issue 1).

    ``gpd.clip`` to the Delaware state boundary keeps any ZCTA that *touches*
    Delaware, and border ZCTAs retain their full multi-state polygon. The
    authoritative fix is the 2020 Census ZCTA-to-county relationship file:
    only ZCTAs whose largest land-area share lies in a Delaware county are
    kept (68 ZCTAs). Out-of-state ZCTAs such as 21842/08014/19350 resolve to
    their true home county and are excluded.
    """
    de_zctas = de_zctas.copy()
    de_zctas["ZCTA"] = de_zctas[zcta_col].astype(str).str.zfill(5)
    try:
        crosswalk = load_zcta_county_crosswalk()
    except FileNotFoundError:
        crosswalk = None
    if crosswalk is None:
        # Offline fallback: centroid-in-DE + Delaware ZIP prefix.
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
        out = out.loc[
            out["ZCTA"].astype(str).str.zfill(5).str.startswith(DE_ZCTA_PREFIXES)
        ]
        print("  WARNING: relationship file missing; used centroid+ZIP fallback.")
    else:
        keep = set(crosswalk["ZCTA"])
        before = de_zctas["ZCTA"].nunique()
        out = de_zctas[de_zctas["ZCTA"].isin(keep)].copy()
        dropped = before - out["ZCTA"].nunique()
        if dropped:
            print(f"  Dropped {dropped} non-Delaware ZCTAs via relationship file.")
        # Safety net: never let an out-of-state ZCTA through even if the
        # relationship file changes upstream.
        out = out.loc[
            out["ZCTA"].astype(str).str.zfill(5).str.startswith(DE_ZCTA_PREFIXES)
        ]
    if out.empty:
        raise RuntimeError("The Delaware ZCTA filter removed every ZCTA; aborting.")
    return out


def fetch_spatial_boundaries():
    """Downloads Delaware state & ZCTA boundaries and computes area metrics.

    County assignment comes from the 2020 Census ZCTA-to-county relationship
    file (largest land-area share; Issue 2) - never from spatial intersects,
    ZIP prefixes, or hand-made lists. 19734 -> New Castle, 19952 -> Kent.
    """
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

    crosswalk = load_zcta_county_crosswalk()
    de_zctas_final = de_zctas.merge(
        crosswalk[["ZCTA", "County_FIPS", "County_Name", "multi_county"]],
        on="ZCTA",
        how="left",
    )
    n_multi = int(de_zctas_final["multi_county"].fillna(False).sum())
    if n_multi:
        flagged = sorted(
            de_zctas_final.loc[de_zctas_final["multi_county"].fillna(False), "ZCTA"].unique()
        )
        print(f"  Flagged {n_multi} multi-county ZCTA(s): {', '.join(flagged)}.")
    missing = de_zctas_final["County_FIPS"].isna().sum()
    if missing:
        raise RuntimeError(
            f"{missing} ZCTA(s) have no county in the relationship file; aborting."
        )
    return de_zctas_final.drop(columns=["multi_county"])

# ---------------------------------------------------------------------------
# 2b. CDC PLACES ZCTA-LEVEL CHRONIC DISEASE (model-based estimates)
# ---------------------------------------------------------------------------
# PLACES publishes SEPARATE datasets per geography: place/city, county,
# census-tract and ZCTA. The ZCTA release is the one that shares this master's
# geography, so chronic-disease measures land on the same ZCTA rows as the ACS
# demographics instead of being broadcast from a city or county geography.
# 2025 release = Socrata qnzd-25i4 (model years 2022-2023).
PLACES_ZCTA_URL = "https://data.cdc.gov/resource/qnzd-25i4.json"
PLACES_ZCTA_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "raw", "cdc_places_2025_de_zcta_raw.csv"
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
              "`python3 fetch_raw_data.py --only cdc_places_2025_de_zcta` first.")
        return pd.DataFrame(columns=["ZCTA"])

    raw = pd.read_csv(filepath, low_memory=False)
    raw = raw[raw["measure"].isin(MEASURE_COLUMNS.keys())].copy()
    for col in ("data_value", "low_confidence_limit", "high_confidence_limit"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")

    raw["ZCTA"] = raw["locationname"].astype(str).str.zfill(5)

    # Issue 6: keep only crude rows (datavaluetypeid == 'CrdPrv') before
    # pivoting, and require exactly one row per location x measure.
    if "datavaluetypeid" in raw.columns:
        n_before = len(raw)
        raw = raw[raw["datavaluetypeid"].eq("CrdPrv")].copy()
        print(f"  Kept {len(raw)}/{n_before} crude PLACES rows (dropped age-adjusted).")
    dupes = raw.duplicated(subset=["ZCTA", "measure"], keep=False)
    if dupes.any():
        bad = sorted(raw.loc[dupes, "measure"].unique())[:5]
        raise ValueError(
            f"PLACES ZCTA has >1 row per location x measure for: {bad}. "
            "Refusing to pivot ambiguously."
        )

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
# S1701 subject-table variables merged into fetch_acs_data: the Data
# Profile's DP03_0128E duplicates the poverty percent (suppressed at ZCTA
# level), so the true published count + universe come from S1701.
S1701_VARS = {
    "S1701_C02_001E": "Count_Below_Poverty",
    "S1701_C01_001E": "Count_Poverty_Universe",
}


# ---------------------------------------------------------------------------
def fetch_acs_data(api_key):
    """Fetches 5-Year ACS profile metrics from the Census API (2024 5-year).

    Issue 3: the API returns missing-value sentinels as NUMBERS
    (-666666666, -888888888, ...). Columns are converted with pd.to_numeric
    FIRST, then any value <= -111111111 is set to NaN. A string match can
    never catch them because they already arrive as ints.

    Issue 7: poverty counts come from subject table S1701 (published count),
    not DP03_0128E (a duplicate of the percent).
    """
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

    print("Fetching ACS subject table S1701 (poverty count + universe)...")
    svar_string = ",".join(S1701_VARS.keys())
    surl = f"https://api.census.gov/data/2024/acs/acs5/subject?get={svar_string}&for=zip%20code%20tabulation%20area:*&key={api_key}"
    sresp = requests.get(surl, timeout=120)
    if sresp.status_code != 200:
        raise ValueError(f"Census S1701 request failed: {sresp.status_code}: {sresp.text[:300]}")
    sdata = sresp.json()
    sdf = pd.DataFrame(sdata[1:], columns=sdata[0])
    sdf["ZCTA"] = sdf["zip code tabulation area"].astype(str).str.zfill(5)
    sdf = sdf.rename(columns=S1701_VARS)
    df = df.merge(sdf[["ZCTA"] + list(S1701_VARS.values())], on="ZCTA", how="left")

    for col in list(ACS_VARS.values()) + list(S1701_VARS.values()):
        # Rare non-numeric tokens first ("(X)", "N"), then numeric coercion.
        df[col] = df[col].replace(NULL_CODES, pd.NA)
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # Numeric sentinel mask (Issue 3): covers -666666666, -888888888,
        # -999999999, -222222222, -333333333, -555555555.
        n_masked = int((df[col] <= CENSUS_SENTINEL_MAX).sum())
        df.loc[df[col] <= CENSUS_SENTINEL_MAX, col] = pd.NA
        if n_masked:
            print(f"  Masked {n_masked} Census sentinel(s) in {col}.")

    # Issue 3 guard: no published measure may be negative after cleaning.
    nonneg = [c for c in ACS_VARS.values() if not c.startswith("Count_") or True]
    neg = {c: int((df[c] < 0).sum()) for c in ACS_VARS.values() if (df[c] < 0).any()}
    if neg:
        raise ValueError(f"Negative published ACS values remain after cleaning: {neg}")

    return df


def fetch_acs_state_total(api_key) -> float:
    """State-level ACS DP05_0001E for Delaware (Issue 1 population check)."""
    url = (
        "https://api.census.gov/data/2024/acs/acs5/profile"
        f"?get=DP05_0001E&for=state:10&key={api_key}"
    )
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    data = response.json()
    return float(data[1][0])

# ---------------------------------------------------------------------------
# 4. REFERENCE TABLES (NOT merged onto ZCTA rows - mentor issue #5)
#
# County Health Rankings (CHR_Delaware.csv / Delaware_County_CHR.csv) and
# CDC BRFSS (BRFSS_Delaware.csv) live in their own state/county tables.
# The retired helpers that broadcast them onto every ZCTA row were removed:
# use gen_health_data.py (BRFSS/CHR downloads) and generate_county_chr.py
# (county table) instead.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 5. MAIN ETL WORKFLOW & EXPORT
# ---------------------------------------------------------------------------
def main():
    spatial_gdf = fetch_spatial_boundaries()
    acs_df = fetch_acs_data(CENSUS_API_KEY)
    places_df = load_places_zcta()

    # Issue 1: keep exactly the 68 Delaware ZCTAs from the relationship file.
    crosswalk = load_zcta_county_crosswalk()
    if len(crosswalk) != 68:
        raise ValueError(
            f"Relationship file yields {len(crosswalk)} DE ZCTAs, expected 68."
        )
    acs_df = acs_df[acs_df["ZCTA"].isin(set(crosswalk["ZCTA"]))].copy()
    master_gdf = spatial_gdf.merge(acs_df, on="ZCTA", how="inner")
    if len(master_gdf) != 68:
        raise ValueError(f"Master has {len(master_gdf)} ZCTAs, expected 68.")

    # Issue 1 check: ZCTA population total within ~1% of the state ACS total.
    zcta_pop = float(master_gdf["Total_Population"].sum(skipna=True))
    state_pop = fetch_acs_state_total(CENSUS_API_KEY)
    if abs(zcta_pop - state_pop) / state_pop > 0.01:
        raise ValueError(
            f"ZCTA pop total {zcta_pop:,.0f} differs >1% from state ACS {state_pop:,.0f}."
        )
    print(f"  ZCTA pop {zcta_pop:,.0f} vs state ACS {state_pop:,.0f} (within 1%).")

    # Issue 5: BRFSS (state) and CHR (county) are NOT merged onto ZCTA rows.
    # They live in their own reference tables: BRFSS_Delaware.csv (state) and
    # Delaware_County_CHR.csv / CHR_Delaware.csv (county). ZCTA maps use ACS +
    # PLACES only, both genuinely ZCTA-level.
    places_cols = [c for c in places_df.columns if c != "ZCTA"]
    if places_cols:
        master_gdf = master_gdf.merge(places_df, on="ZCTA", how="left")
        missing = master_gdf.loc[master_gdf[places_cols[0]].isna(), "ZCTA"].tolist()
        if missing:
            print(f"  NOTE: PLACES has no ZCTA estimate for {len(missing)} ZCTA(s): "
                  f"{', '.join(missing)} - their PLACES measures are NULL.")


    master_gdf["Population_Density_SqMi"] = (master_gdf["Total_Population"] / master_gdf["Land_Area_SqMi"]).round(2)
    # Issue 7: use PUBLISHED ACS counts - never back-calculate from percents.
    # DP03_0099E/DP03_0095E: uninsured count + civilian-noninstitutionalized
    # universe. S1701_C02_001E/C01_001E: poverty count + poverty universe.
    # DP05_0024E: 65+ count. DP02_0154E/DP02_0152E: broadband count +
    # household universe, so the no-broadband figure is households (not people).
    master_gdf["Uninsured_Population_Count"] = master_gdf["Count_No_Health_Insurance"]
    master_gdf["Poverty_Population_Count"] = master_gdf["Count_Below_Poverty"]
    master_gdf["Seniors_65_Plus_Count"] = master_gdf["Count_Age_65_Plus"]
    master_gdf["No_Broadband_Households_Estimate"] = (
        master_gdf["Count_Households_Broadband_Universe"] - master_gdf["Count_Broadband_Internet"]
    )

    # Issue 3 guard on derived columns: no published measure may be negative.
    for col in ("Uninsured_Population_Count", "Poverty_Population_Count",
                "Seniors_65_Plus_Count", "No_Broadband_Households_Estimate"):
        neg = master_gdf[col].dropna()
        if (neg < 0).any():
            raise ValueError(f"Derived column {col} has negative values.")

    # Drop the Count_* helper denominators from the shipped master (they stay
    # in the raw ACS snapshot); the four derived counts above are the outputs.
    helpers = [c for c in master_gdf.columns if c.startswith("Count_")]
    master_gdf = master_gdf.drop(columns=helpers)


    print("Exporting updated master datasets...")
    tabular_df = pd.DataFrame(master_gdf.drop(columns=["geometry"]))

    # Provenance: the true geography of every measure. The ZCTA master holds
    # only genuinely ZCTA-level measures (ACS + TIGER + PLACES ZCTA); BRFSS
    # (state) and CHR (county) live in their own reference tables, never on
    # ZCTA rows. Users who want ZCTA-only measures filter on
    # Geography_Level == "ZCTA".
    provenance_df = pd.DataFrame(provenance_rows(list(tabular_df.columns)))
    provenance_path = "Delaware_ZCTA_Health_Master_Column_Provenance.csv"
    provenance_df.to_csv(provenance_path, index=False)

    tabular_df.to_csv("Delaware_ZCTA_Health_Master_Wide.csv", index=False)
    with pd.ExcelWriter("Delaware_ZCTA_Health_Master_Wide.xlsx") as writer:
        tabular_df.to_excel(writer, sheet_name="Master", index=False)
        provenance_df.to_excel(writer, sheet_name="Column_Provenance", index=False)

    master_gdf.to_file("Delaware_ZCTA_Health_Master_Spatial.geojson", driver="GeoJSON")
    print(f"Wrote {provenance_path} ({len(provenance_df)} columns classified)")
    print("Successfully exported the ZCTA master (ACS + PLACES ZCTA only).")

if __name__ == "__main__":
    main()