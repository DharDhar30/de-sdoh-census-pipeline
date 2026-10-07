# Delaware SDOH & Census Health Data Pipeline

An automated Python ETL pipeline building curated need/access datasets for healthcare analysis in Delaware: Census ACS demographics, CDC PLACES ZCTA-level chronic-disease estimates, CDC BRFSS state benchmarks, and County Health Rankings county tables — each at its own true geography.

The pipeline outputs ready-to-use tabular and spatial datasets specifically formatted for interactive mapping in Tableau, ArcGIS, and QGIS.

## Features

- Automated Spatial Extraction: Downloads official U.S. Census Bureau cartographic boundary files via pygris and clips boundaries specifically to Delaware ZCTAs.
- Census ACS Integration: Pulls 2024 5-Year ACS Data Profile metrics (2020–2024; poverty, broadband, insurance, median income, age, language) directly via the Census API.
- CDC BRFSS (Public Health): Keeps the CDC Behavioral Risk Factor Surveillance System 2024 state-level prevalence for Delaware as a **standalone state reference table** (`BRFSS_Delaware.csv`) - chronic disease, risk behaviors, health-care access, screenings, oral health, disability, each with sample size and 95% CI. Never broadcast onto ZCTA rows.
- County Health Rankings (CHR): Keeps medical / public-health indicators across Delaware's 3 counties (New Castle, Kent, Sussex) in a **standalone county table** (`Delaware_County_CHR.csv`) - health outcomes, health behaviors, clinical care. Never broadcast onto ZCTA rows or re-aggregated.
- Provider supply out of scope (mentor §3): the AHRF snapshot stays archived in `raw/` for reference but nothing consumes it — county-level counts would duplicate/conflict with the DE Health Force dashboard.
- CDC PLACES ZCTA-Level: Pulls the PLACES **ZCTA** release so chronic-disease and prevention measures are reported directly on the same ZCTAs as the master (crude prevalence only, one row per ZCTA x measure).
- Automated Transformations: Computes derived counts from published ACS `E` counts (never percent x population) and land density metrics directly in Python.
- Multi-Format Export: Generates wide-format outputs in CSV, Excel, and spatial GeoJSON formats simultaneously.

To download every raw snapshot from the app: expand **All raw sources & citations** and
use the **Download ALL snapshots (ZIP)** button, or use the per-source *Download raw
snapshot* button in each citation panel.

## Published values are used as published

The county and city tables report **the publisher's own numbers, unaltered.** Nothing
in them is averaged, weighted, re-derived or hand-edited, and both build scripts refuse
to write their output if any emitted value differs from the archived raw snapshot.

```bash
python3 generate_county_chr.py                # -> Delaware_County_CHR.csv
python3 build_city_chronic_disease_table.py   # -> Delaware_City_Chronic_Disease.csv
```

### County table — `Delaware_County_CHR.csv` (3 rows)

| Column | Source |
|---|---|
| `County_Name` | CHR 2025, published |
| `Total_Population` | **Census ACS 2024 5-year `DP05_0001E` (county)** — never summed from ZCTAs |
| `Pct_Poor_Fair_Health` (+ `_LowCI` / `_HighCI`) | CHR 2025, published |
| `CHR_PCP_Ratio_Population` | CHR 2025, published |
| `Dentist_Ratio_Population` | CHR 2025, published |
| `Mental_Health_Provider_Ratio` | CHR 2025, published |

`Total_Population` is the single column that is not CHR's. CHR publishes **no** county
population total — its `High School Completion__Population` and
`Some College__Population` columns are education cohorts, not a population total. It
comes from the Census ACS 2024 5-year county tables (`DP05_0001E`), never by summing
ZCTAs. `Population_Source` records the provenance on every row.

**A ZCTA→county aggregation was removed as unsound.** `generate_county_chr.py`
previously rebuilt this table by aggregating the ZCTA-level master back to county,
which corrupted published values: the master *used to broadcast* each county value
onto every ZCTA in that county, so averaging an identical value against itself drifted
`Pct_Poor_Fair_Health` from a published 16.4 to 19.9 in Kent, and summing a county count
across its ZCTAs inflated Kent's premature deaths from a published 3,195 to 56,892
(17.9×). The correct published value is **3,195** (not the 2,920 in the earlier
draft of this README): CHR publishes these counties directly, so the table is now a
straight projection of the raw release, and the master no longer carries county
figures at all.

### City table — `Delaware_City_Chronic_Disease.csv` (79 rows)

| Column | Source |
|---|---|
| `City_Municipality` | CDC PLACES 2024 `locationname` |
| `Adult_Obesity_Pct`, `Diabetes_Pct`, `Coronary_Heart_Disease_Pct` | PLACES, published (age-adjusted) |
| `*_CI_Low` / `*_CI_High` | PLACES, published confidence limits |
| `*_Crude_Pct` | PLACES, published crude series (carried for auditability) |

PLACES publishes each measure twice — **age-adjusted** and **crude** prevalence. The
primary columns are age-adjusted, which is the series to compare across places because
crude rates confound health with a place's age structure. The crude series is kept in
`*_Crude_Pct` columns so the choice is visible rather than hidden. (The older
`PLACES_Delaware_City.csv` resolved this with `aggfunc="first"` — whatever row the API
returned first — which happened to be age-adjusted but was never stated.) The script
asserts the vintage is uniformly 2023 and fails rather than mixing years silently.

These are CDC's **model-based small-area estimates, not observed counts.** Report them
with their confidence limits, and do not read small differences between neighbouring
places as meaningful without checking the intervals separate.

### Geography warning

Provider ratios are **county-level** (3 observations) and come from CHR. Chronic-disease
measures are **city/place-level** (79) and come from PLACES. These two tables share no
common geography and must not be joined to each other.

## Project Structure

- extract_census.py: Main ETL Pipeline Script (ZCTA master: spatial + ACS + PLACES ZCTA + published-count derived metrics; BRFSS/CHR kept in their own state/county tables)
- fetch_raw_data.py: Downloads and archives every raw public dataset into raw/ with citations + SHA-256 checksums (also `--verify`)
- PROVENANCE.md: Data provenance & licensing reference (full source inventory)
- raw_sources.py: Read-only accessor for the archived raw manifest, used by the UI
- raw/: Unmodified publisher snapshots + raw/sources.json manifest + raw/SOURCES.md citations
- gen_health_data.py: Downloads BRFSS (CDC API) and CHR (County Health Rankings website) CSV files from official sources
- generate_county_chr.py: Rebuilds Delaware_County_CHR.csv as a straight projection of the raw CHR release (verifies every value against the snapshot)
- build_city_chronic_disease_table.py: Rebuilds Delaware_City_Chronic_Disease.csv from the raw CDC PLACES snapshot (verifies every value against the snapshot)
- BRFSS_Delaware.csv: CDC BRFSS 2024 Delaware state-level prevalence (public-health measures)
- CHR_Delaware.csv: County Health Rankings 2025 medical/public-health indicators
- Delaware_County_CHR.csv: 3-county table — published CHR figures + ACS county population
- Delaware_City_Chronic_Disease.csv: 79-city table — published PLACES obesity / diabetes / coronary heart disease
- .env: API key configuration
- requirements.txt: Python dependencies
- Delaware_ZCTA_Health_Master_Spatial.geojson: Master Spatial GeoJSON for Tableau
- Delaware_ZCTA_Health_Master_Column_Provenance.csv: Per-column source + true geography of every master measure

## Installation & Local Execution Instructions

**Requirements:** Python **3.9 or newer** (3.10+ recommended). macOS ships `/usr/bin/python3` as 3.9.6, which works, but a newer python.org or Homebrew Python pulls in the newest pandas/Streamlit. Check yours with `python3 --version`.

Run the following exact terminal commands from your terminal to run the pipeline and interactive UI locally:

```bash
# 1. Clone the repository
git clone https://github.com/DharDhar30/de-sdoh-census-pipeline.git
cd de-sdoh-census-pipeline

# 2. Set up virtual environment and install Python dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure API key (optional but recommended for Census API rate limits)
# Create a .env file in the root directory with:
# CENSUS_API_KEY="your_census_api_key_here"

# 4. (Optional) Re-download BRFSS & CHR data from official sources:
python3 gen_health_data.py

# 5. Run the master ETL pipeline script
python3 extract_census.py
```

### Interactive UI (Streamlit)

```bash
# 6. Launch the Streamlit UI locally
streamlit run app.py
```

Or use the provided shortcut script:
```bash
bash start_ui.sh
```

`start_ui.sh` creates `.venv` on first run (or rebuilds it when it was built by an unsupported Python), installs `requirements.txt`, and prints the Python version it launches with - so the manual venv steps above are optional when you only need the UI.

Then open the URL printed by Streamlit (default http://localhost:8501).

## Sector Export UI Usage

1. Launch the UI with `streamlit run app.py` (or `bash start_ui.sh`).
2. Click "Run ETL & Refresh Data" to regenerate data, or upload your own Excel/CSV.
3. Select the sectors you want (Demographics, Socioeconomic, Health Access, BRFSS (State Level), CHR - Health Outcomes, CHR - Health Behaviors, CHR - Clinical Care, Calculated Metrics, Geographic) and refine individual columns as needed.
4. Preview the result in the interactive table, then export as an Excel workbook with one sheet per sector, separate per-sector CSV/Excel files, or a single combined file.

Exports are saved in `./exports/` so your workspace stays clean.

## Derived Metrics & Formulas

- Population Density: Total Population / Land Area (Sq. Miles)
- Uninsured Population Volume: published `DP03_0099E` count (never `Pct_No_Health_Insurance` × population)
- Poverty Population Volume: published `S1701_C02_001E` count (never `Pct_Below_Poverty` × population)
- Senior Population Volume: published `DP05_0024E` count (never `Pct_Age_65_Plus` × population)
- No Broadband Households: published `DP02_0152E` (household universe) − `DP02_0154E` (broadband count)

## Pipeline Output Schema

- Geographic: ZCTA, County_FIPS, County_Name (5-digit ZCTA and spatial county linkage)
- Demographics: Total_Population, Median_Age, Pct_Age_65_Plus (ACS population & age breakdown)
- Socioeconomic: Median_Household_Income, Pct_Below_Poverty (Economic prosperity indicators)
- Health Access: Pct_No_Health_Insurance, Pct_Broadband_Internet (Essential infrastructure access)
- BRFSS (State Level): CDC BRFSS 2024 Delaware prevalence - smoking, vaping, binge/heavy drinking, obesity, physical inactivity, arthritis, asthma, COPD, heart disease, stroke, diabetes, kidney disease, depression, cancer, fair/poor health, mental/physical distress, uninsured, cost barriers, checkups, colorectal & mammography screening, flu & pneumonia vaccination, HIV testing, oral health, and disability indicators (each with sample size + 95% CI) — state reference table ONLY, never on ZCTA rows
- CHR - Health Outcomes: Pct_Poor_Fair_Health, Avg Poor Physical/Mental Health Days, CHR_YPLL_Rate, CHR_Pct_Low_Birthweight, CHR_STI_Chlamydia_Rate, CHR_Teen_Birth_Rate — county reference table ONLY
- CHR - Health Behaviors: Pct_Adult_Smoking, Pct_Adult_Obesity, Pct_Physical_Inactivity, Excessive_Drinking_Pct, CHR_Food_Environment_Index, CHR_Access_Exercise_Opportunities_Pct, CHR_Alcohol_Impaired_Driving_Deaths_Pct — county reference table ONLY
- CHR - Clinical Care: CHR_Uninsured_Pct, CHR_PCP_Ratio_Population, Dentist_Ratio_Population, Mental_Health_Provider_Ratio, CHR_Preventable_Hospital_Stays_Rate, CHR_Mammography_Screening_Pct, CHR_Flu_Vaccination_Pct — county reference table ONLY
- Calculated Metrics: Population_Density_SqMi, Uninsured_Population_Count, No_Broadband_Households_Estimate (Derived volume & density counts, from published ACS E counts)

## Raw data sources (all live, all verifiable)

Every input dataset is archived **unmodified** under `raw/`, with the exact request URL,
retrieval timestamp and SHA-256 digest in `raw/sources.json` and human-readable citations
in `raw/SOURCES.md`. Re-download or re-verify everything with:

```bash
python3 fetch_raw_data.py            # refresh snapshots + manifest
python3 fetch_raw_data.py --verify   # re-check live URLs + stored checksums (exit 1 on drift)
```

| # | Dataset | Publisher | Vintage | Geography | Snapshot |
|---|---|---|---|---|---|
| 1 | TIGER/Line Cartographic Boundary File — 2020 ZCTA, clipped to DE | U.S. Census Bureau | 2020 | ZCTA | `raw/census_tiger_2020_de_zctas_raw.csv` |
| 2 | TIGER/Line Cartographic Boundary File — 2020 counties, DE | U.S. Census Bureau | 2020 | County | `raw/census_tiger_2020_de_counties_raw.csv` |
| 3 | American Community Survey 5-Year Data Profile (DP02/DP03/DP05) | U.S. Census Bureau | 2024 5-yr (2020–2024) | ZCTA | `raw/census_acs_2024_zcta_de_raw.csv` |
| 4 | BRFSS Prevalence (Socrata `dttw-5yxu`) | CDC | 2024 | State (standalone reference table) | `raw/cdc_brfss_2024_de_raw.csv` |
| 5 | 2025 County Health Rankings Data v4, `Select Measure Data` + `Additional Measure Data` sheets merged on FIPS (clinical-care source year: 2022) | County Health Rankings & Roadmaps | 2025 release | County (standalone reference table) | `raw/chr_2025_de_counties_raw.csv` |
| 6 | PLACES: Local Data for Better Health, place/city release (Socrata `eav7-hnsx`) | CDC | 2024 release | City / place | `raw/cdc_places_2024_de_city_raw.csv` |

The per-column provenance file shipped with the master outputs
(`Delaware_ZCTA_Health_Master_Column_Provenance.csv`, also the `Column_Provenance`
sheet of the master workbook) labels every measure with its source and the geography
it was collected at, so ZCTA-measured columns can be isolated in Tableau via
`Geography_Level == "ZCTA"`.

Quartile columns are no longer published in the CHR release file and are kept as empty
(NaN) columns for schema compatibility; regenerate inputs with `python3 gen_health_data.py`.

## Tableau Visualization Guide

1. Open Tableau and select Connect -> Spatial File.
2. Select Delaware_ZCTA_Health_Master_Spatial.geojson.
3. Open a new Worksheet and double-click Geometry.
4. Drag Zcta (or Zcta5Ce20) onto Detail on the Marks Card to display individual ZIP code boundaries.
5. Drag any health metric onto Color.

## Troubleshooting

- Tableau Field Mismatches Warning Icons: If red exclamation marks appear on fields when opening Tableau, clear all existing worksheet fields, navigate to Data Sources, and ensure Delaware_ZCTA_Health_Master_Spatial.geojson is selected as the active primary source.
- Missing Geometry Fields in CSV Exports: The tabular CSV and Excel outputs drop spatial polygon geometry by design to optimize file sizes for analytical spreadsheets. To build polygon maps, always connect directly to the generated .geojson spatial file.
- Census API Rate Limits: If running bulk extractions repeatedly, populate your CENSUS_API_KEY in the .env file to prevent Census API request throttling.
- `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` pointing at a line such as `def sector_of(column: str) -> str | None:`: the app is being imported by Python 3.9 or older (PEP 604 unions like `X | None` need 3.10+, and macOS's stock `/usr/bin/python3` is 3.9.6), or you are running an older checkout of `main`. Fix: pull the latest `main`, then rebuild the environment with `rm -rf .venv && bash start_ui.sh`. The UI modules now use `from __future__ import annotations`, so Python 3.9 works, and `start_ui.sh` refuses to reuse a `.venv` built by an unsupported interpreter.
