import argparse
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(ROOT, "raw")
MANIFEST_PATH = os.path.join(RAW_DIR, "sources.json")
SOURCES_MD_PATH = os.path.join(RAW_DIR, "SOURCES.md")

load_dotenv(os.path.join(ROOT, ".env"))
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")

# --- Source 1: Census ACS 5-Year Data Profile (same variables as the ETL) ----
# Most-current vintage: 2024 5-year (2020-2024). Verified live 2026-10-05.
ACS_PROFILE_URL = "https://api.census.gov/data/2024/acs/acs5/profile"
ACS_VARS = [
    "DP05_0001E",
    "DP05_0018E",
    "DP05_0024PE",
    "DP03_0062E",
    "DP03_0128PE",
    "DP03_0099PE",
    "DP03_0021PE",
    "DP02_0154PE",
    "DP02_0114PE",
]

# --- Source 2: CDC BRFSS Prevalence (identical query to extract_census.py) ---
BRFSS_URL = (
    "https://chronicdata.cdc.gov/resource/dttw-5yxu.csv"
    "?$where=locationabbr='DE' and break_out_category='Overall' and year=2024"
    "&$limit=10000"
)

# --- Source 3: County Health Rankings 2025 release workbook ----------------
# Most-current release: 2025 Annual Data Release, v4 file. Note the filename
# uses spaces ("2025 County Health Rankings Data - v4.xlsx"), NOT the old
# underscore pattern ("2024_county_health_release_data_-_v1.xlsx" -> 404).
# Health-behavior measures (smoking, obesity, inactivity, drinking, STIs,
# teen births, alcohol-impaired deaths) moved from "Select Measure Data" to
# the "Additional Measure Data" sheet in the 2025 release, so BOTH sheets are
# parsed and merged on FIPS. "Low Birthweight" was renamed "Low Birth Weight".
CHR_URL = (
    "https://www.countyhealthrankings.org/"
    "sites/default/files/media/document/"
    "2025%20County%20Health%20Rankings%20Data%20-%20v4.xlsx"
)
CHR_SHEET = "Select Measure Data"
CHR_ADDL_SHEET = "Additional Measure Data"
DE_COUNTY_FIPS = {"10001", "10003", "10005"}  # Kent, New Castle, Sussex

# --- Source 4: CDC PLACES city/place-level estimates -----------------------
# Use the SODA 2.1 resource endpoint ($where filters server-side). The v3
# query.json root ignores $where/$limit, which would dump the whole nation.
PLACES_URL = "https://data.cdc.gov/resource/eav7-hnsx.json"
PLACES_QUERY = {"$where": "statedesc='Delaware'", "$limit": 50000}

# --- Source 5/6: Census TIGER (cartographic boundary) via pygris -----------
TIGER_LANDING = "https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html"

# Delaware ZIPs are exactly 197xx / 198xx / 199xx, so a ZCTA prefix is a
# reliable, publisher-intended test for "is this ZCTA in Delaware?".
DE_ZCTA_PREFIXES = ("197", "198", "199")

# --- Source 7: HRSA Area Health Resources Files (AHRF) --------------------
# AHRF is a FREE, public-domain federal provider-supply dataset. It is the
# *primary* source behind the population-to-provider ratios that County Health
# Rankings publishes, so it lets the ratios be recomputed from first-party
# counts instead of taken on trust. Direct zip, no login, no agreement.
AHRF_URL = "https://data.hrsa.gov/DataDownload/AHRF/AHRF_2024-2025_CSV.zip"
AHRF_LANDING = "https://data.hrsa.gov/topics/health-workforce/ahrf"
AHRF_POP_FILE = "AHRF2025pop.csv"
AHRF_HP_FILE = "AHRF2025hp.csv"

# --- Source 8: CDC PLACES ZCTA-level estimates -----------------------------
# PLACES publishes SEPARATE datasets per geography. The project originally used
# the place/city release, which forces chronic-disease measures onto a city
# geography. The ZCTA release (4r2x-hcfq) gives the same measures directly on
# the ZCTAs the rest of the master is keyed to.
PLACES_ZCTA_URL = "https://data.cdc.gov/resource/4r2x-hcfq.json"
PLACES_ZCTA_QUERY = {
    "$where": "locationname like '197%' OR locationname like '198%' OR locationname like '199%'",
    "$limit": 50000,
}

TIMEOUT = 300


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact(url: str) -> str:
    """Strip the Census API key out of a manifest URL before committing it."""
    if CENSUS_API_KEY:
        return url.replace(CENSUS_API_KEY, "***REDACTED***")
    return url


def _write_raw_bytes(filename: str, payload: bytes) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, filename)
    with open(path, "wb") as fh:
        fh.write(payload)
    return path


def _write_raw_frame(filename: str, frame: pd.DataFrame) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, filename)
    frame.to_csv(path, index=False)
    return path


def _count(path: str) -> tuple:
    """Row/column counts of an archived CSV (rows excludes the header)."""
    import csv as _csv

    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        reader = _csv.reader(fh)
        header = next(reader, [])
        columns = max(len(header), 1)
        rows = sum(1 for _ in reader)
    return rows, columns


def _zcta_id_column(frame: pd.DataFrame) -> str:
    for col in ("ZCTA5CE20", "GEOID20", "ZCTA5CE10", "GEOID"):
        if col in frame.columns:
            return col
    raise ValueError(f"No ZCTA id column found in {list(frame.columns)}")


def _fips_series(series: pd.Series) -> pd.Series:
    """Normalise a FIPS column to 5-char strings without touching the original."""
    return series.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)


# ---------------------------------------------------------------------------
# Source 5/6 - Census TIGER cartographic boundaries (ZCTA + county)
# ---------------------------------------------------------------------------
def fetch_tiger_de_zctas() -> tuple:
    """TIGER/Line 2020 ZCTA cartographic boundaries clipped to Delaware."""
    import geopandas as gpd
    import pygris

    print("  Downloading TIGER ZCTA + state boundaries via pygris (this is the big one)...")
    de_state = pygris.states(cb=True, resolution="20m").query("STUSPS == 'DE'")
    zctas = pygris.zctas(year=2020, cb=True)
    if zctas.crs != de_state.crs:
        zctas = zctas.to_crs(de_state.crs)
    de_zctas = gpd.clip(zctas, de_state)

    id_col = _zcta_id_column(de_zctas)
    # gpd.clip splits polygons at the state border, which drags in pieces of
    # ZCTAs from neighbouring states. Two filters are needed, because Delaware's
    # north-east corner touches Maryland and Pennsylvania:
    #   1. keep only ZCTAs whose CENTROID sits in Delaware (project first, so
    #      the centroid math is done in metres, not degrees); and
    #   2. keep only ZCTAs whose ZIP belongs to Delaware at all (197/198/199).
    # The centroid test alone let 30 Maryland/Pennsylvania/New Jersey ZCTAs
    # through - border ZCTAs keep their full multi-state polygon, so ZCTA 21921
    # (Annapolis, MD) arrived with 245 km2 of land area and its ACS population
    # was later merged into the master, inflating Delaware's total by ~21%.
    projected = de_zctas.to_crs(epsg=3857)
    centroids = projected.set_geometry(projected.geometry.centroid)
    inside = gpd.sjoin(
        centroids, de_state.to_crs(epsg=3857)[["geometry"]], how="left", predicate="within"
    )
    keep = inside.dropna(subset=["index_right"]).index.unique()
    de_zctas = de_zctas.loc[keep].copy()

    ids = de_zctas[id_col].astype(str).str.zfill(5)
    de_prefixed = ids.str.startswith(DE_ZCTA_PREFIXES)
    dropped = int((~de_prefixed).sum())
    de_zctas = de_zctas.loc[de_prefixed].copy()
    if dropped:
        print(f"  Dropped {dropped} non-Delaware ZCTAs (centroid fell inside DE but ZIP is not 197/198/199).")
    if de_zctas.empty:
        raise RuntimeError("The Delaware ZCTA filter removed every ZCTA; aborting.")

    attributes = [c for c in de_zctas.columns if c != "geometry"]
    frame = pd.DataFrame(de_zctas[attributes]).sort_values(id_col).reset_index(drop=True)
    path = _write_raw_frame("census_tiger_2020_de_zctas_raw.csv", frame)
    return path, {
        "zcta_ids": set(frame[id_col].astype(str).str.zfill(5)),
        "note": (
            "Every attribute column the TIGER ZCTA shapefile ships with, geometry dropped "
            "so it can be archived as CSV. Clipped to the Delaware state boundary and "
            "restricted to ZCTAs whose centroid is inside Delaware AND whose ZIP is a "
            f"Delaware ZIP ({'/'.join(DE_ZCTA_PREFIXES)}). Both filters are required: the "
            "centroid test alone keeps border ZCTAs belonging to MD/PA/NJ."
        ),
    }


def fetch_tiger_de_counties() -> tuple:
    """TIGER/Line 2020 county cartographic boundaries for Delaware."""
    import pygris

    print("  Downloading TIGER county boundaries via pygris...")
    counties = pygris.counties(state="DE", cb=True)
    attributes = [c for c in counties.columns if c != "geometry"]
    frame = pd.DataFrame(counties[attributes]).reset_index(drop=True)
    path = _write_raw_frame("census_tiger_2020_de_counties_raw.csv", frame)
    return path, {
        "note": "All 3 Delaware counties; source of County_FIPS / County_Name in the master."
    }


# ---------------------------------------------------------------------------
# Source 1 - Census ACS 5-Year Data Profile
# ---------------------------------------------------------------------------
def fetch_census_acs_2024(de_zcta_ids: set) -> tuple:
    """Raw ACS 2024 5-year profile response, filtered to the Delaware ZCTAs."""
    print("  Querying the Census ACS 2024 5-year profile API...")
    url = (
        f"{ACS_PROFILE_URL}?get={','.join(ACS_VARS)}"
        "&for=zip%20code%20tabulation%20area:*"
    )
    if CENSUS_API_KEY:
        url += f"&key={CENSUS_API_KEY}"

    resp = requests.get(url, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Census API returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    payload = resp.json()
    frame = pd.DataFrame(payload[1:], columns=payload[0])
    downloaded = len(frame)

    # Keep the API's own ZCTA values untouched; use a throwaway series to filter.
    id_col = "zip code tabulation area"
    if id_col in frame.columns and de_zcta_ids:
        mask = frame[id_col].astype(str).str.zfill(5).isin(de_zcta_ids)
        frame = frame[mask].reset_index(drop=True)

    path = _write_raw_frame("census_acs_2024_zcta_de_raw.csv", frame)
    return path, {
        "note": (
            f"API variable codes retained (no renaming). {downloaded:,} ZCTAs were returned "
            "nationwide; the snapshot keeps the Delaware rows used by the pipeline."
        ),
        "rows_downloaded_total": downloaded,
        "url": _redact(url),
    }


# ---------------------------------------------------------------------------
# Source 2 - CDC BRFSS prevalence (state level)
# ---------------------------------------------------------------------------
def fetch_cdc_brfss_2024_de() -> tuple:
    """Byte-for-byte copy of the CDC BRFSS Socrata CSV response for Delaware.

    NOTE on row counts: Socrata pretty-prints a row index inside long
    ``geolocation`` cells, so the response body carries extra physical newlines
    folded inside quoted fields.  CSV parsers (``csv`` module, pandas) honour
    the quoting and report the true count (165 survey rows as of Oct 2026);
    naive line counting sees more.  Row counts in the manifest always follow
    the parsed (logical) rows, not physical newlines.
    """
    print("  Downloading CDC BRFSS 2024 Delaware prevalence...")
    resp = requests.get(BRFSS_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    path = _write_raw_bytes("cdc_brfss_2024_de_raw.csv", resp.content)
    return path, {
        "note": (
            "Byte-for-byte copy of the CDC Socrata CSV response (no re-encoding, "
            "no column renaming). This is a STATE-level survey, so every row here "
            "describes Delaware as a whole - not an individual ZCTA."
        )
    }


# ---------------------------------------------------------------------------
# Source 3 - County Health Rankings 2025 release workbook
# ---------------------------------------------------------------------------
def _parse_chr_sheet(content: bytes, sheet: str) -> pd.DataFrame:
    """Parse one CHR workbook sheet (two header rows joined with '__')."""
    grid = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)
    group = grid.iloc[0].ffill()
    measure = grid.iloc[1]
    columns = []
    for group_cell, measure_cell in zip(group, measure):
        head = "" if pd.isna(group_cell) else str(group_cell).strip()
        leaf = "" if pd.isna(measure_cell) else str(measure_cell).strip()
        columns.append(f"{head}__{leaf}" if head and leaf else (head or leaf or "column"))

    body = grid.iloc[2:].copy()
    body.columns = columns
    return body.reset_index(drop=True)


def fetch_chr_2025_de_counties() -> tuple:
    """Delaware county rows from the official 2025 CHR release workbook.

    The 2025 release split measures across two sheets: "Select Measure Data"
    (outcomes + clinical care) and "Additional Measure Data" (health
    behaviors: smoking, obesity, inactivity, drinking, STIs, teen births,
    alcohol-impaired deaths). Both are parsed and merged on FIPS so the
    Delaware snapshot keeps the same measure coverage as the 2024 one.
    """
    print("  Downloading the 2025 County Health Rankings release workbook (~16 MB)...")
    resp = requests.get(CHR_URL, timeout=TIMEOUT)
    resp.raise_for_status()

    select = _parse_chr_sheet(resp.content, CHR_SHEET)
    try:
        addl = _parse_chr_sheet(resp.content, CHR_ADDL_SHEET)
    except ValueError:
        addl = None

    def _fips_col(frame: pd.DataFrame, sheet: str) -> str:
        col = next((c for c in frame.columns if c.strip().endswith("FIPS")), None)
        if col is None:
            raise RuntimeError(
                f"No FIPS column in '{sheet}'; first columns were {list(frame.columns[:5])}"
            )
        return col

    select_fips = _fips_col(select, CHR_SHEET)
    select["_join_fips"] = _fips_series(select[select_fips])
    de_select = select[select["_join_fips"].isin(DE_COUNTY_FIPS)].reset_index(drop=True)
    if de_select.empty:
        raise RuntimeError("No Delaware county rows found in the CHR workbook.")

    if addl is not None:
        addl_fips = _fips_col(addl, CHR_ADDL_SHEET)
        addl["_join_fips"] = _fips_series(addl[addl_fips])
        de_addl = addl[addl["_join_fips"].isin(DE_COUNTY_FIPS)].reset_index(drop=True)
        # Keep Select-sheet columns as-is; add only Additional columns not
        # already present (FIPS/State/County overlap). State row (FIPS 10000)
        # is dropped by the FIPS filter either way.
        extra = [c for c in de_addl.columns if c not in de_select.columns and c != "_join_fips"]
        de_rows = de_select.merge(
            de_addl[["_join_fips"] + extra], on="_join_fips", how="left"
        ).drop(columns=["_join_fips"])
        sheets_note = f"'{CHR_SHEET}' + '{CHR_ADDL_SHEET}' merged on FIPS"
    else:
        de_rows = de_select.drop(columns=["_join_fips"])
        sheets_note = f"'{CHR_SHEET}'"

    path = _write_raw_frame("chr_2025_de_counties_raw.csv", de_rows)
    return path, {
        "note": (
            f"Workbook sheets {sheets_note}, every measure column kept, Delaware counties "
            "only (FIPS 10001/10003/10005). The two header rows the publisher ships are "
            "joined with '__'; no values are altered or rounded."
        )
    }


# ---------------------------------------------------------------------------
# Source 4 - CDC PLACES city/place-level estimates
# ---------------------------------------------------------------------------
def fetch_cdc_places_de_city() -> tuple:
    """Raw CDC PLACES rows for Delaware places (one row per place x measure)."""
    print("  Querying the CDC PLACES API for Delaware place-level estimates...")
    resp = requests.get(PLACES_URL, params=PLACES_QUERY, timeout=TIMEOUT)
    resp.raise_for_status()
    records = resp.json()
    if not records:
        raise RuntimeError("CDC PLACES returned no rows for Delaware.")
    frame = pd.DataFrame(records)
    path = _write_raw_frame("cdc_places_2024_de_city_raw.csv", frame)
    prepared = requests.Request("GET", PLACES_URL, params=PLACES_QUERY).prepare().url
    return path, {
        "url": prepared,
        "note": (
            "Untouched API rows - one row per place x measure with the publisher's own "
            "field names. PLACES publishes place/city, county, census-tract and ZCTA "
            "files as SEPARATE datasets; this endpoint is the place/city release."
        ),
    }


# ---------------------------------------------------------------------------
# Source 7 - HRSA Area Health Resources Files: provider counts + population
# ---------------------------------------------------------------------------
def fetch_hrsa_ahrf_de_counties() -> tuple:
    """Delaware county rows from the HRSA AHRF 2024-2025 CSV release.

    AHRF is the federal (HRSA) provider-supply file that County Health Rankings
    draws its population-to-provider ratios from. It is free and public domain:
    a direct .zip download with no login and no data-use agreement. This keeps
    the raw provider counts AND the population denominators side by side so a
    ratio can be recomputed independently rather than trusted as published.
    """
    import zipfile

    print("  Downloading the AHRF 2024-2025 CSV release (~23 MB)...")
    resp = requests.get(AHRF_URL, timeout=TIMEOUT)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        hp_name = next((n for n in names if n.endswith(AHRF_HP_FILE)), None)
        pop_name = next((n for n in names if n.endswith(AHRF_POP_FILE)), None)
        if not hp_name or not pop_name:
            raise RuntimeError(f"AHRF zip is missing {AHRF_HP_FILE}/{AHRF_POP_FILE}: {names[:9]}")
        hp = pd.read_csv(zf.open(hp_name), dtype=str, low_memory=False)
        pop = pd.read_csv(zf.open(pop_name), dtype=str, low_memory=False)

    fips = "fips_st_cnty"
    if fips not in hp.columns or fips not in pop.columns:
        raise RuntimeError(f"AHRF is missing the '{fips}' key; got {list(hp.columns[:3])}")

    de_hp = hp[_fips_series(hp[fips]).isin(DE_COUNTY_FIPS)].reset_index(drop=True)
    de_pop = pop[_fips_series(pop[fips]).isin(DE_COUNTY_FIPS)].reset_index(drop=True)
    if de_hp.empty:
        raise RuntimeError("No Delaware county rows found in the AHRF release.")

    # Prefix the population columns so the two files' short names (which overlap)
    # cannot collide once they sit side by side in one snapshot.
    pop_cols = [c for c in de_pop.columns if c != fips]
    de_pop = de_pop.rename(columns={c: f"pop_{c}" for c in pop_cols})
    merged = de_hp.merge(de_pop, on=fips, how="left", suffixes=("", "_pop_dup"))

    path = _write_raw_frame("hrsa_ahrf_2025_de_counties_raw.csv", merged)
    return path, {
        "rows_downloaded_total": len(hp),
        "url": AHRF_URL,
        "note": (
            f"Delaware county rows (FIPS {', '.join(sorted(DE_COUNTY_FIPS))}) from the "
            f"'{AHRF_HP_FILE}' health-professional file joined to '{AHRF_POP_FILE}' on "
            "fips_st_cnty. Health-professional columns carry the publisher's own "
            "names and vintage suffix (e.g. md_nf_prim_care_pc_excl_rsdnt_23); "
            "population columns are prefixed 'pop_' so the two files' overlapping "
            "short names stay distinct. Values are exactly as published - AHRF "
            "suppresses small counts, so blanks mean 'suppressed', not zero."
        ),
    }


# ---------------------------------------------------------------------------
# Source 8 - CDC PLACES ZCTA-level chronic disease / health estimates
# ---------------------------------------------------------------------------
def fetch_cdc_places_de_zcta() -> tuple:
    """Raw CDC PLACES rows for Delaware ZCTAs (one row per ZCTA x measure)."""
    print("  Querying the CDC PLACES ZCTA API for Delaware...")
    resp = requests.get(PLACES_ZCTA_URL, params=PLACES_ZCTA_QUERY, timeout=TIMEOUT)
    resp.raise_for_status()
    records = resp.json()
    if not records:
        raise RuntimeError("CDC PLACES ZCTA returned no rows for Delaware.")
    frame = pd.DataFrame(records)
    path = _write_raw_frame("cdc_places_2024_de_zcta_raw.csv", frame)
    prepared = requests.Request("GET", PLACES_ZCTA_URL, params=PLACES_ZCTA_QUERY).prepare().url
    n_zctas = frame["locationname"].nunique()
    return path, {
        "url": prepared,
        "rows_downloaded_total": len(frame),
        "note": (
            f"Untouched API rows - one row per ZCTA x measure with the publisher's own "
            f"field names. {n_zctas} Delaware ZCTAs x {frame['measure'].nunique()} measures. "
            "This is the ZCTA release of PLACES, so the chronic-disease measures "
            "(diabetes, hypertension, asthma, COPD, depression, ...) are reported ON the "
            "ZCTAs rather than being borrowed from a city-level file and broadcast."
        ),
    }


# ---------------------------------------------------------------------------
# Source registry - order matters (the ACS feed is filtered to the TIGER ZCTAs)
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "id": "census_tiger_2020_de_zctas",
        "label": "Census TIGER 2020 ZCTA Boundaries (DE)",
        "publisher": "U.S. Census Bureau",
        "dataset": "TIGER/Line Cartographic Boundary File - 2020 ZCTA (cb_2020_us_zcta520_500k), clipped to Delaware",
        "vintage": "2020",
        "geography": "ZCTA (Delaware)",
        "geo_level": "ZCTA",
        "access": "Python client (pygris) over the Census TIGER web service",
        "url": "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip",
        "landing_page": TIGER_LANDING,
        "license": "Public domain (U.S. Government work)",
        "fetch": fetch_tiger_de_zctas,
    },
    {
        "id": "census_tiger_2020_de_counties",
        "label": "Census TIGER 2020 County Boundaries (DE)",
        "publisher": "U.S. Census Bureau",
        "dataset": "TIGER/Line Cartographic Boundary File - 2020 counties (cb_2020_us_county_500k), Delaware",
        "vintage": "2020",
        "geography": "County (Delaware)",
        "geo_level": "County",
        "access": "Python client (pygris) over the Census TIGER web service",
        "url": "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_500k.zip",
        "landing_page": TIGER_LANDING,
        "license": "Public domain (U.S. Government work)",
        "fetch": fetch_tiger_de_counties,
    },
    {
        "id": "census_acs_2024_zcta_de",
        "label": "Census ACS 2024 5-Year Profile (ZCTA)",
        "publisher": "U.S. Census Bureau",
        "dataset": "American Community Survey 5-Year Data Profile (DP02 / DP03 / DP05)",
        "vintage": "2024 5-year estimates (2020-2024)",
        "geography": "ZCTA (Delaware rows of a national response)",
        "geo_level": "ZCTA",
        "access": "REST API (JSON) - requires CENSUS_API_KEY in .env",
        "url": (
            f"{ACS_PROFILE_URL}?get={','.join(ACS_VARS)}"
            "&for=zip code tabulation area:*&key=***REDACTED***"
        ),
        "landing_page": "https://data.census.gov/",
        "license": "Public domain (U.S. Government work)",
        "fetch": fetch_census_acs_2024,
        "args": ("de_zcta_ids",),
    },
    {
        "id": "cdc_brfss_2024_de",
        "label": "CDC BRFSS 2024 Prevalence (DE, state level)",
        "publisher": "U.S. Centers for Disease Control and Prevention",
        "dataset": "Behavioral Risk Factor Surveillance System - Prevalence Data (Socrata resource dttw-5yxu)",
        "vintage": "2024",
        "geography": "State (Delaware) - broadcast onto ZCTA rows downstream",
        "geo_level": "State",
        "access": "REST API (CSV), Socrata SODA",
        "url": BRFSS_URL,
        "landing_page": "https://chronicdata.cdc.gov/",
        "license": "Public domain (U.S. Government work)",
        "fetch": fetch_cdc_brfss_2024_de,
    },
    {
        "id": "chr_2025_de_counties",
        "label": "County Health Rankings 2025 (DE counties)",
        "publisher": "County Health Rankings & Roadmaps (Univ. of Wisconsin Population Health Institute)",
        "dataset": "2025 County Health Rankings Data v4 (`Select Measure Data` + `Additional Measure Data` sheets, merged on FIPS)",
        "vintage": "2025 release (clinical-care source year 2022; see Sources & Years sheets)",
        "geography": "County (Kent, New Castle, Sussex) - broadcast onto ZCTA rows downstream",
        "geo_level": "County",
        "access": "Direct file download (.xlsx)",
        "url": CHR_URL,
        "landing_page": "https://www.countyhealthrankings.org/health-data/methodology-and-sources/data-documentation",
        "license": "Free for public use with attribution (CHR&R / UW PHI)",
        "fetch": fetch_chr_2025_de_counties,
    },
    {
        "id": "cdc_places_2024_de_city",
        "label": "CDC PLACES 2024 Place-Level (DE cities)",
        "publisher": "U.S. Centers for Disease Control and Prevention",
        "dataset": "PLACES: Local Data for Better Health - place/city release (Socrata eav7-hnsx)",
        "vintage": "2024 release",
        "geography": "City / place (Delaware)",
        "geo_level": "City / place",
        "access": "REST API (JSON), Socrata SODA 3.0",
        "url": PLACES_URL,
        "landing_page": "https://www.cdc.gov/places/index.html",
        "license": "Public domain (U.S. Government work)",
        "fetch": fetch_cdc_places_de_city,
    },
    {
        "id": "hrsa_ahrf_2025_de_counties",
        "label": "HRSA AHRF 2024-2025 (DE counties, provider supply)",
        "publisher": "Health Resources & Services Administration (HRSA), U.S. Dept. of Health & Human Services",
        "dataset": "Area Health Resources Files (AHRF) 2024-2025 CSV release - health professional (AHRF2025hp) + population (AHRF2025pop)",
        "vintage": "2024-2025 release (counts carry per-column vintage suffixes, e.g. _23)",
        "geography": "County (Kent, New Castle, Sussex)",
        "geo_level": "County",
        "access": "Direct .zip file download - no login, no data-use agreement",
        "url": AHRF_URL,
        "landing_page": AHRF_LANDING,
        "license": "Public domain (U.S. Government work)",
        "fetch": fetch_hrsa_ahrf_de_counties,
    },
    {
        "id": "cdc_places_2024_de_zcta",
        "label": "CDC PLACES 2024 ZCTA-Level (DE chronic disease & prevention)",
        "publisher": "U.S. Centers for Disease Control and Prevention",
        "dataset": "PLACES: Local Data for Better Health - ZCTA release (Socrata 4r2x-hcfq)",
        "vintage": "2024 release",
        "geography": "ZCTA (Delaware) - directly reported, NOT broadcast from a city file",
        "geo_level": "ZCTA",
        "access": "REST API (JSON), Socrata SODA 3.0",
        "url": PLACES_ZCTA_URL,
        "landing_page": "https://www.cdc.gov/places/index.html",
        "license": "Public domain (U.S. Government work)",
        "fetch": fetch_cdc_places_de_zcta,
    },
]

SOURCE_BY_ID = {spec["id"]: spec for spec in SOURCES}

# Keys of the fetch() result that get carried into the next source's arguments.
_CONTEXT_KEYS = ("zcta_ids",)


def _read_manifest() -> dict:
    if not os.path.exists(MANIFEST_PATH):
        return {"sources": []}
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _existing_zcta_ids() -> set:
    """Fall back to the archived TIGER snapshot when running with --only."""
    path = os.path.join(RAW_DIR, "census_tiger_2020_de_zctas_raw.csv")
    if not os.path.exists(path):
        return set()
    frame = pd.read_csv(path)
    for col in ("ZCTA5CE20", "GEOID20", "ZCTA5CE10", "GEOID"):
        if col in frame.columns:
            return set(frame[col].astype(str).str.zfill(5))
    return set()


def _entry_from(spec: dict, path: str, extra: dict) -> dict:
    """Build one manifest entry from a freshly downloaded snapshot."""
    rows, columns = _count(path)
    entry = {
        "id": spec["id"],
        "label": spec["label"],
        "publisher": spec["publisher"],
        "dataset": spec["dataset"],
        "vintage": spec["vintage"],
        "geography": spec["geography"],
        "geo_level": spec["geo_level"],
        "access": spec["access"],
        "url": extra.get("url") or spec["url"],
        "landing_page": spec.get("landing_page", ""),
        "license": spec.get("license", ""),
        "file": os.path.basename(path),
        "rows": rows,
        "columns": columns,
        "sha256": _sha256_file(path),
        "retrieved_utc": _now_utc(),
        "note": extra.get("note", ""),
    }
    if "rows_downloaded_total" in extra:
        entry["rows_downloaded_total"] = extra["rows_downloaded_total"]
    return entry


def run_download(only=None) -> list:
    """Download every (or selected) source and return the ordered manifest."""
    previous = {s["id"]: s for s in _read_manifest().get("sources", [])}
    context = {"de_zcta_ids": _existing_zcta_ids()}
    entries = []

    for spec in SOURCES:
        if only and spec["id"] not in only:
            if spec["id"] in previous:
                entries.append(previous[spec["id"]])
            continue

        print(f"[{spec['id']}]")
        try:
            path, extra = spec["fetch"](**{k: context[k] for k in spec.get("args", ())})
        except Exception as exc:
            print(f"  FAILED - {type(exc).__name__}: {exc}")
            if spec["id"] in previous:
                print("  keeping the previously archived snapshot")
                entries.append(previous[spec["id"]])
            continue

        for key in _CONTEXT_KEYS:
            if key in extra:
                context[key] = extra[key]

        entry = _entry_from(spec, path, extra)
        old = previous.get(spec["id"])
        if old and old.get("sha256"):
            if old["sha256"] != entry["sha256"]:
                print("  CHANGED - the publisher updated this dataset since the last archive")
            else:
                print("  unchanged since the last archive")
        print(f"  {entry['rows']:,} rows x {entry['columns']} cols -> raw/{entry['file']}")
        entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Manifest + citation output
# ---------------------------------------------------------------------------
def write_manifest(entries: list) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    manifest = {
        "generated_utc": _now_utc(),
        "generated_by": "fetch_raw_data.py",
        "note": (
            "Snapshots of public datasets exactly as published. No values in this "
            "directory are modelled, imputed or edited by this project."
        ),
        "sources": entries,
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    return MANIFEST_PATH


def write_sources_md(entries: list) -> str:
    os.makedirs(RAW_DIR, exist_ok=True)
    lines = [
        "# Raw Data Sources",
        "",
        "Proof-of-provenance index for every dataset this pipeline consumes. Each file in this",
        "directory is an **unmodified copy** of what a public publisher served - original column",
        "names, original values, no cleaning, no renaming and no cross-source joins.",
        "",
        f"Manifest generated: **{_now_utc()}** by `fetch_raw_data.py`.",
        "",
        "Re-verify everything at any time:",
        "",
        "```bash",
        "python3 fetch_raw_data.py --verify",
        "```",
        "",
        "## Archived datasets",
        "",
        "| # | Dataset | Publisher | Geography | Rows x Cols | Snapshot |",
        "|---|---|---|---|---|---|",
    ]
    for i, src in enumerate(entries, start=1):
        lines.append(
            f"| {i} | {src['label']} | {src['publisher']} | {src['geo_level']} | "
            f"{src['rows']:,} x {src['columns']} | `raw/{src['file']}` |"
        )

    lines += ["", "## Per-source detail", ""]
    for i, src in enumerate(entries, start=1):
        lines += [
            f"### {i}. {src['label']}",
            "",
            f"- **Publisher:** {src['publisher']}",
            f"- **Dataset:** {src['dataset']}",
            f"- **Vintage:** {src['vintage']}",
            f"- **Geography:** {src['geography']}",
            f"- **Retrieved (UTC):** {src['retrieved_utc']}",
            f"- **File:** `raw/{src['file']}` ({src['rows']:,} rows x {src['columns']} columns)",
            f"- **Source URL:** `{src['url']}`",
        ]
        if src.get("landing_page"):
            lines.append(f"- **Landing page:** {src['landing_page']}")
        if src.get("license"):
            lines.append(f"- **License / terms:** {src['license']}")
        if src.get("rows_downloaded_total"):
            lines.append(
                f"- **Rows downloaded before regional filter:** {src['rows_downloaded_total']:,}"
            )
        if src.get("sha256"):
            lines.append(f"- **SHA-256:** `{src['sha256']}`")
        if src.get("note"):
            lines.append(f"- **Note:** {src['note']}")
        lines.append("")

    lines += _sources_md_footer()
    with open(SOURCES_MD_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return SOURCES_MD_PATH


def _sources_md_footer() -> list:
    return [
        "## Notes on geography",
        "",
        "- ACS 2024, the TIGER boundaries and the PLACES ZCTA release are genuinely",
        "  ZCTA-level.",
        "- PLACES values are **model-based estimates** produced from BRFSS survey data by",
        "  small-area modelling - they are not direct counts of conditions. The publisher's",
        "  confidence limits are archived alongside every measure. PLACES does not publish an",
        "  estimate for every ZCTA; those rows are NULL rather than filled in.",
        "- BRFSS is a **state** survey, so its Delaware figures describe the whole state and",
        "  are broadcast onto every ZCTA row downstream (identical across ZCTAs).",
        "- CHR and the HRSA AHRF provider ratios report at **county** level, so their figures",
        "  are broadcast onto the ZCTAs in that county via `County_FIPS`.",
        "- The `Geography_Level` field in `Delaware_ZCTA_Health_Master_Column_Provenance.csv`",
        "  (also the `Column_Provenance` sheet of the master workbook) labels each measure,",
        "  and the UI's 'geography they were actually collected at' filter uses the same field,",
        "  so non-ZCTA measures can be filtered out in the UI or in Tableau.",
        "",
        "## Delaware ZCTA selection",
        "",
        "The master contains **68** ZCTAs. Getting that number right needed two filters, not",
        "one. Clipping the TIGER ZCTAs to the Delaware state boundary keeps every ZCTA that",
        "*touches* Delaware, and border ZCTAs keep their full multi-state polygon - Delaware's",
        "north-east corner touches Maryland and Pennsylvania. A centroid test alone therefore",
        "let 25 Maryland, Pennsylvania and New Jersey ZCTAs through, including ZCTA 21921",
        "(Annapolis, MD). Their ACS populations were merged in, inflating the master's total",
        "population from 982,285 to 1,190,837 - an overstatement of about 21%, with the NJ and",
        "Philadelphia-area rows assigned to Kent, New Castle and Sussex counties.",
        "",
        "So `fetch_raw_data.py` and `extract_census.py` both require **both** conditions:",
        "",
        "1. the ZCTA's centroid falls inside the Delaware state polygon, and",
        "2. the ZCTA's ZIP is a Delaware ZIP (`197`, `198` or `199`).",
        "",
        "Either test on its own is insufficient.",
        "",
    ]


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify(entries: list) -> int:
    """Re-check live URLs and stored checksums. Returns a process exit code."""
    print("Verifying archived raw sources against the publishers...\n")
    header = f"{'status':<10}{'source':<34}{'rows':>8}  detail"
    print(header)
    print("-" * len(header))

    failures = 0
    for src in entries:
        path = os.path.join(RAW_DIR, src["file"])
        if not os.path.exists(path):
            print(f"{'MISSING':<10}{src['id']:<34}{'':>8}  raw/{src['file']} not found")
            failures += 1
            continue

        digest = _sha256_file(path)
        if src.get("sha256") and digest != src["sha256"]:
            print(
                f"{'DRIFT':<10}{src['id']:<34}{src['rows']:>8}  "
                f"sha256 {digest[:12]}... != manifest {src['sha256'][:12]}..."
            )
            failures += 1
            continue

        try:
            resp = requests.get(src["url"], timeout=60, stream=True)
            status = resp.status_code
            resp.close()
        except Exception as exc:
            print(f"{'ERROR':<10}{src['id']:<34}{src['rows']:>8}  {type(exc).__name__}: {exc}")
            failures += 1
            continue

        if status == 200:
            print(
                f"{'OK':<10}{src['id']:<34}{src['rows']:>8}  "
                f"HTTP 200 - live {_pretty_bytes(resp.headers.get('Content-Length'))}, "
                f"sha256 {digest[:12]}..."
            )
        else:
            print(f"{'UNREACHABLE':<10}{src['id']:<34}{src['rows']:>8}  HTTP {status}")
            failures += 1

    print("-" * len(header))
    if failures:
        print(f"{failures} of {len(entries)} source(s) need attention.")
    else:
        print(f"All {len(entries)} archived sources verified: live URLs resolve and checksums match.")
    return 1 if failures else 0


def _pretty_bytes(value) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return "size unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "size unknown"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Archive the raw public datasets this pipeline uses, with citations and checksums."
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="re-check live URLs and stored checksums instead of downloading",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="SOURCE_ID",
        help="restrict to one source id (repeatable); other snapshots are left untouched",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the known source ids and exit",
    )
    parser.add_argument(
        "--rewrite-docs",
        action="store_true",
        help="regenerate raw/SOURCES.md + raw/sources.json from the existing manifest (no downloads)",
    )
    args = parser.parse_args(argv)

    if args.list:
        for spec in SOURCES:
            print(f"{spec['id']:<32} {spec['label']}")
        return 0

    if args.rewrite_docs:
        entries = _read_manifest().get("sources", [])
        if not entries:
            print("Nothing to rewrite - raw/sources.json is missing. Run fetch_raw_data.py first.")
            return 1
        print(f"Rewrote {os.path.relpath(write_sources_md(entries), ROOT)}")
        return 0

    if not args.list and not os.path.exists(MANIFEST_PATH) and args.only:
        print(
            "No manifest yet. Run without --only once so the archive (and its citations) "
            "is built in full.\n",
            file=sys.stderr,
        )
        return 1

    if args.verify:
        entries = _read_manifest().get("sources", [])
        if not entries:
            print("Nothing to verify - raw/sources.json is missing. Run fetch_raw_data.py first.")
            return 1
        return verify(entries)

    entries = run_download(only=set(args.only) if args.only else None)
    if not entries:
        print("No sources were archived.", file=sys.stderr)
        return 1

    manifest_path = write_manifest(entries)
    md_path = write_sources_md(entries)
    print(f"\nWrote {os.path.relpath(manifest_path, ROOT)}")
    print(f"Wrote {os.path.relpath(md_path, ROOT)}")
    print(
        "\nEvery file under ./raw is an untouched publisher snapshot. "
        "Run with --verify to re-check the live URLs and checksums."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())