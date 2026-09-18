"""Registry of every raw data source that can be merged into a master dataset.

Each source declares the geography level(s) it can be merged at and the join key
it uses at that level, so master_builder.build_master() can assemble a master
from any user-selected subset of sources without hand-written join logic.

Geography levels
    zcta   - ZIP Code Tabulation Area
    tract  - Census tract
    city   - Census place (city / town)
    county - County

A join key of BROADCAST means the source carries a single statewide row that is
copied onto every row of the master (CDC BRFSS state prevalence).

Loaders return raw pandas / geopandas frames. Column hygiene for Tableau
happens downstream in master_builder.
"""

import os
import re
from dataclasses import dataclass
from typing import Callable, Mapping

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Source file locations
# ---------------------------------------------------------------------------
CHR_CSV_PATH = os.path.join(ROOT, "CHR_Delaware.csv")
BRFSS_CSV_PATH = os.path.join(ROOT, "BRFSS_Delaware.csv")
BRFSS_ZCTA_CSV_PATH = os.path.join(ROOT, "data/brfss/Delaware_BRFSS_ZCTA_Cleaned.csv")
PLACES_CITY_PATH = os.path.join(ROOT, "PLACES_Delaware_City.csv")
PLACES_TRACT_PATH = os.path.join(ROOT, "data/census_tract/Delaware_CensusTract_PLACES.csv")
COUNTY_CHR_PATH = os.path.join(ROOT, "Delaware_County_CHR.csv")
GEOJSON_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Spatial.geojson")

# Columns that belong to a raw file but only clutter a Tableau data pane.
# They are dropped from every export unless raw columns are explicitly requested.
JUNK_COLUMNS = (
    "AFFGEOID20",
    "GEOID20",
    "NAME20",
    "LSAD20",
    "ZCTA5CE20",
    "zip code tabulation area",
    "index_right",
)

# Sentinel join key: one statewide row copied onto every master row.
BROADCAST: None = None

NULL_CODES = ["-666666666", "-888888888", "-999999999", "(X)", "N", "null", "None", ""]

LEVELS: dict[str, dict] = {
    "zcta": {
        "label": "ZCTA (ZIP Code Tabulation Area)",
        "key_column": "ZCTA",
        "row_noun": "ZCTAs",
        "base_order": ("spatial_zcta", "acs"),
        "supports_geometry": True,
    },
    "tract": {
        "label": "Census Tract",
        "key_column": "CensusTractFIPS",
        "row_noun": "tracts",
        "base_order": ("places_tract",),
        "supports_geometry": False,
    },
    "city": {
        "label": "City / Place",
        "key_column": "City_Name",
        "row_noun": "cities",
        "base_order": ("places_city",),
        "supports_geometry": False,
    },
    "county": {
        "label": "County",
        "key_column": "County_Name",
        "row_noun": "counties",
        "base_order": ("chr_county", "county_chr"),
        "supports_geometry": False,
    },
}

# The composition of the historical hardcoded master, used as the UI default.
DEFAULT_SOURCES = ("spatial_zcta", "acs", "brfss_state", "chr_county", "metrics")


def sanitize_column_name(name: str) -> str:
    """Return an ASCII-only, Tableau-safe column name."""
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", str(name)).strip("_")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    return cleaned or "column"


def sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Apply sanitize_column_name to every column, keeping names unique."""
    seen: dict[str, int] = {}
    renamed: dict[str, str] = {}
    for col in df.columns:
        base = sanitize_column_name(col)
        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 0
        renamed[col] = base
    return df.rename(columns=renamed)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
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

ACS_API_URL = (
    "https://api.census.gov/data/2021/acs/acs5/profile"
    "?get={vars}&for=zip%20code%20tabulation%20area:*&key={key}"
)

# BRFSS state-level measures: (column stem, question substring, exact response).
BRFSS_STATE_MEASURES = [
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


def load_spatial_boundaries() -> pd.DataFrame:
    """ZCTA polygons clipped to Delaware plus land/water area and county link.

    Requires network access (pygris downloads Census cartographic boundaries).
    """
    import geopandas as gpd
    import pygris

    print("Fetching spatial boundaries via pygris...")
    de_state = pygris.states(cb=True, resolution="20m").query("STUSPS == 'DE'")
    zctas = pygris.zctas(year=2020, cb=True)

    if zctas.crs != de_state.crs:
        zctas = zctas.to_crs(de_state.crs)

    de_zctas = gpd.clip(zctas, de_state)

    aland_col = "ALAND20" if "ALAND20" in de_zctas.columns else "ALAND"
    awater_col = "AWATER20" if "AWATER20" in de_zctas.columns else "AWATER"
    zcta_col = (
        "ZCTA5CE20"
        if "ZCTA5CE20" in de_zctas.columns
        else ("GEOID20" if "GEOID20" in de_zctas.columns else "GEOID")
    )

    de_zctas = de_zctas[de_zctas[aland_col] > 0].copy()
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
        predicate="intersects",
    )
    return joined.drop_duplicates(subset=["ZCTA"]).drop(columns=["index_right"], errors="ignore")


def load_acs(api_key: str | None = None) -> pd.DataFrame:
    """Census ACS 5-Year Data Profile metrics keyed on ZCTA.

    Requires network access (Census API). Set CENSUS_API_KEY in .env to avoid
    throttling.
    """
    import requests

    if api_key is None:
        try:
            from dotenv import load_dotenv

            load_dotenv(os.path.join(ROOT, ".env"))
        except Exception:
            pass
        api_key = os.getenv("CENSUS_API_KEY", "")

    print("Fetching Census ACS 5-Year demographic metrics...")
    url = ACS_API_URL.format(vars=",".join(ACS_VARS.keys()), key=api_key)
    response = requests.get(url, timeout=180)
    if response.status_code != 200:
        raise ValueError(
            f"Census API request failed with status code {response.status_code}: {response.text[:300]}"
        )

    payload = response.json()
    df = pd.DataFrame(payload[1:], columns=payload[0])
    df = df.rename(columns=ACS_VARS)
    df["ZCTA"] = df["zip code tabulation area"].astype(str).str.zfill(5)
    # The raw response key duplicates ZCTA; drop it so it never reaches Tableau.
    df = df.drop(columns=["zip code tabulation area"], errors="ignore")
    df = _to_numeric(df, ACS_VARS.values())
    return df[["ZCTA"] + list(ACS_VARS.values())]


def load_brfss_state() -> pd.DataFrame:
    """CDC BRFSS 2024 Delaware state prevalence: one statewide row (broadcast).

    Uses the bundled BRFSS_Delaware.csv when present, otherwise the live CDC
    BRFSS Prevalence API.
    """
    if os.path.exists(BRFSS_CSV_PATH):
        print("Loading CDC BRFSS 2024 Delaware state prevalence...")
        return pd.read_csv(BRFSS_CSV_PATH)

    import io

    import requests

    print("Fetching CDC BRFSS 2024 Delaware prevalence from API...")
    url = (
        "https://chronicdata.cdc.gov/resource/dttw-5yxu.csv"
        "?$where=locationabbr='DE' and break_out_category='Overall' and year=2024"
        "&$limit=10000"
    )
    response = requests.get(url, timeout=180)
    response.raise_for_status()

    raw = pd.read_csv(io.StringIO(response.text))
    raw.columns = [c.lower() for c in raw.columns]
    out: dict = {"State": "Delaware", "BRFSS_Year": 2024}
    problems = []
    for name, qsub, resp_exact in BRFSS_STATE_MEASURES:
        question = raw["question"].fillna("").astype(str).str.contains(qsub, case=False, regex=False)
        answer = (
            raw["response"].fillna("").astype(str).str.strip().str.lower().eq(resp_exact.lower())
        )
        hits = raw[question & answer]
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
    return pd.DataFrame([out])


def load_brfss_zcta() -> pd.DataFrame:
    """CDC BRFSS ZCTA-level estimates pivoted wide, one row per ZCTA.

    The source file is long format (one row per ZCTA x MeasureId); it is pivoted
    on MeasureId so the result joins 1:1 on ZCTA and can never duplicate master
    rows.
    """
    if not os.path.exists(BRFSS_ZCTA_CSV_PATH):
        raise FileNotFoundError(
            f"{BRFSS_ZCTA_CSV_PATH} not found. Expected the cleaned BRFSS ZCTA extract."
        )
    print("Loading CDC BRFSS ZCTA-level estimates...")
    long_df = pd.read_csv(BRFSS_ZCTA_CSV_PATH)
    long_df["ZCTA"] = long_df["LocationID"].astype(str).str.zfill(5)
    long_df["MeasureId"] = long_df["MeasureId"].astype(str).str.strip()

    wide = long_df.pivot_table(index="ZCTA", columns="MeasureId", values="Data_Value", aggfunc="first")
    wide.columns = [f"BRFSS_ZCTA_{sanitize_column_name(col)}" for col in wide.columns]

    for statistic, suffix in (
        ("Low_Confidence_Limit", "_CI_Low"),
        ("High_Confidence_Limit", "_CI_High"),
    ):
        extra = long_df.pivot_table(index="ZCTA", columns="MeasureId", values=statistic, aggfunc="first")
        extra.columns = [f"BRFSS_ZCTA_{sanitize_column_name(col)}{suffix}" for col in extra.columns]
        wide = wide.join(extra)

    wide = wide.reset_index()
    return _to_numeric(wide, [c for c in wide.columns if c != "ZCTA"])


def load_chr_county() -> pd.DataFrame:
    """County Health Rankings medical / public-health indicators keyed on County_FIPS."""
    if not os.path.exists(CHR_CSV_PATH):
        raise FileNotFoundError(
            f"{CHR_CSV_PATH} not found. Run gen_health_data.py to download the "
            "official County Health Rankings data."
        )
    print("Loading County Health Rankings (CHR) metrics...")
    chr_df = pd.read_csv(CHR_CSV_PATH)
    chr_df["County_FIPS"] = _zfill_fips(chr_df["County_FIPS"])
    return chr_df


def load_places_tract() -> pd.DataFrame:
    """CDC PLACES model-based estimates at census tract level."""
    if not os.path.exists(PLACES_TRACT_PATH):
        raise FileNotFoundError(f"{PLACES_TRACT_PATH} not found.")
    print("Loading CDC PLACES census tract estimates...")
    df = sanitize_columns(pd.read_csv(PLACES_TRACT_PATH))
    df["CensusTractFIPS"] = df["CensusTractFIPS"].astype(str).str.zfill(11)
    if "CountyFIPS" in df.columns:
        df["CountyFIPS"] = _zfill_fips(df["CountyFIPS"])
    return df


def load_places_city() -> pd.DataFrame:
    """CDC PLACES model-based estimates at city / place level."""
    if not os.path.exists(PLACES_CITY_PATH):
        raise FileNotFoundError(f"{PLACES_CITY_PATH} not found. Run fetch_places.py to download it.")
    print("Loading CDC PLACES city-level estimates...")
    return sanitize_columns(pd.read_csv(PLACES_CITY_PATH))


def load_county_chr() -> pd.DataFrame:
    """County-level CHR rollup produced from the ZCTA master by generate_county_chr.py.

    This is a derived artifact rather than a raw source, hence its exclusion
    from the default master composition.
    """
    if not os.path.exists(COUNTY_CHR_PATH):
        raise FileNotFoundError(f"{COUNTY_CHR_PATH} not found. Run generate_county_chr.py first.")
    print("Loading county-level CHR rollup...")
    df = sanitize_columns(pd.read_csv(COUNTY_CHR_PATH))
    if "County_FIPS" in df.columns:
        df["County_FIPS"] = _zfill_fips(df["County_FIPS"])
    return df


@dataclass(frozen=True)
class Source:
    """One raw data source and the contract for merging it into a master."""

    key: str
    label: str
    levels: tuple[str, ...]
    join_keys: Mapping[str, str | None]
    loader: Callable[[], pd.DataFrame] | None
    provides_geometry: bool = False
    derived: bool = False
    note: str = ""

    def join_key(self, level: str) -> str | None:
        """Column to join on at `level`, or BROADCAST/None for statewide rows."""
        return self.join_keys.get(level)

    def available(self, level: str) -> bool:
        return level in self.levels


SOURCES: tuple[Source, ...] = (
    Source(
        key="spatial_zcta",
        label="ZCTA boundaries (Census cartographic, pygris)",
        levels=("zcta",),
        join_keys={"zcta": "ZCTA"},
        loader=load_spatial_boundaries,
        provides_geometry=True,
        note="Polygon boundaries plus land/water area and county link. Requires network.",
    ),
    Source(
        key="acs",
        label="Census ACS 5-Year Data Profile",
        levels=("zcta",),
        join_keys={"zcta": "ZCTA"},
        loader=load_acs,
        note="Demographics, socioeconomic and health-access indicators. Requires network.",
    ),
    Source(
        key="brfss_state",
        label="CDC BRFSS state prevalence (2024)",
        levels=("zcta", "tract", "county"),
        join_keys={"zcta": BROADCAST, "tract": BROADCAST, "county": BROADCAST},
        loader=load_brfss_state,
        note="Single statewide row, copied onto every master row.",
    ),
    Source(
        key="chr_county",
        label="County Health Rankings (CHR)",
        levels=("zcta", "tract", "county"),
        join_keys={"zcta": "County_FIPS", "tract": "CountyFIPS", "county": "County_FIPS"},
        loader=load_chr_county,
        note="County indicators, repeated across every row of that county.",
    ),
    Source(
        key="brfss_zcta",
        label="CDC BRFSS ZCTA-level estimates",
        levels=("zcta",),
        join_keys={"zcta": "ZCTA"},
        loader=load_brfss_zcta,
        note="40 measures with confidence limits, pivoted 1:1 onto ZCTA.",
    ),
    Source(
        key="places_tract",
        label="CDC PLACES census tract estimates",
        levels=("tract",),
        join_keys={"tract": "CensusTractFIPS"},
        loader=load_places_tract,
        note="Model-based tract estimates. Base geography for the tract level.",
    ),
    Source(
        key="places_city",
        label="CDC PLACES city-level estimates",
        levels=("city",),
        join_keys={"city": "City_Name"},
        loader=load_places_city,
        note="Model-based estimates per Delaware place. Base geography for the city level.",
    ),
    Source(
        key="county_chr",
        label="County CHR rollup (derived from ZCTA master)",
        levels=("county",),
        join_keys={"county": "County_FIPS"},
        loader=load_county_chr,
        derived=True,
        note="Produced by generate_county_chr.py from the ZCTA master, not a raw source.",
    ),
    Source(
        key="metrics",
        label="Derived metrics (density and population counts)",
        levels=("zcta",),
        join_keys={"zcta": None},
        loader=None,
        derived=True,
        note="Computed from ACS plus land area. Needs Total_Population and Land_Area_SqMi.",
    ),
)

SOURCE_INDEX: dict[str, Source] = {source.key: source for source in SOURCES}


def source_by_key(key: str) -> Source:
    if key not in SOURCE_INDEX:
        raise KeyError(f"Unknown data source: {key}")
    return SOURCE_INDEX[key]


def sources_for_level(level: str) -> list[Source]:
    """Every source that can be merged at `level`, registry order preserved."""
    if level not in LEVELS:
        raise KeyError(f"Unknown geography level: {level}")
    return [source for source in SOURCES if source.available(level)]


def sources_requiring_network(keys) -> list[Source]:
    """Selected sources that need a live API call (used for UI warnings)."""
    network_keys = {"spatial_zcta", "acs"}
    return [source_by_key(k) for k in keys if k in network_keys]


def default_sources_for_level(level: str) -> list[str]:
    """Sensible default selection for each level."""
    if level == "zcta":
        return list(DEFAULT_SOURCES)
    return [source.key for source in sources_for_level(level) if not source.derived]


def _zfill_fips(series: pd.Series) -> pd.Series:
    """Normalise a FIPS column that may arrive as float or string into 5 digits."""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        text = numeric.dropna().astype("int64").astype(str).str.zfill(5)
        return numeric.astype("Int64").astype(str).where(numeric.isna(), text).replace("<NA>", pd.NA)
    return series.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)


def _to_numeric(df: pd.DataFrame, columns) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            cleaned = df[col].replace(NULL_CODES, pd.NA)
            df[col] = pd.to_numeric(cleaned, errors="coerce")
    return df
