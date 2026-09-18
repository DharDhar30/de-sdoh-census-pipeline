# Delaware SDOH & Census Health Data Pipeline

An automated Python ETL pipeline designed to extract, transform, and merge Delaware Social Determinants of Health (SDOH), Census ACS demographics, CDC BRFSS public-health indicators, and County Health Rankings (CHR) at the ZIP Code Tabulation Area (ZCTA) level.

The pipeline outputs ready-to-use tabular and spatial datasets specifically formatted for interactive mapping in Tableau, ArcGIS, and QGIS.

## Features

- Automated Spatial Extraction: Downloads official U.S. Census Bureau cartographic boundary files via pygris and clips boundaries specifically to Delaware ZCTAs.
- Census ACS Integration: Pulls 5-Year ACS Data Profile metrics (poverty, broadband, insurance, median income, age, language) directly via the Census API.
- CDC BRFSS (Public Health): Merges real CDC Behavioral Risk Factor Surveillance System 2024 state-level prevalence for Delaware - chronic disease (diabetes, asthma, COPD, heart disease, cancer, arthritis, kidney disease), risk behaviors (smoking, vaping, binge/heavy drinking, obesity, physical inactivity), health-care access (uninsured, cost barriers, routine checkups), screenings (mammogram, colorectal, flu/pneumonia vaccination), oral health, and disability. Each measure includes its sample size and 95% confidence interval.
- County Health Rankings (CHR): Merges medical / public-health indicators across Delaware's 3 counties (New Castle, Kent, Sussex) - health outcomes (poor/fair health, premature death, low birth weight, STIs, teen births), health behaviors (smoking, obesity, inactivity, excessive drinking, food environment, exercise access, alcohol-impaired driving deaths), and clinical care (uninsured, provider ratios, preventable hospital stays, screening & vaccination rates).
- Automated Transformations: Computes derived population counts and land density metrics directly in Python.
- Multi-Format Export: Generates wide-format outputs in CSV, Excel, and spatial GeoJSON formats simultaneously.
- Selectable Data Sources: Rather than one hardcoded merge, every source is registered with the geography level it belongs to, so the UI and CLI can assemble a master from any chosen subset and report exactly how each source joined.
- Tableau-Ready Outputs: A stable-filename bundle (flat CSV plus WGS84 MultiPolygon GeoJSON, geographic-role helper columns, centroid coordinates, and a field manifest) removes the manual source blending and field fixing that used to happen inside Tableau.

## Project Structure

- data_sources.py: Registry of every data source, the geography level(s) it can merge at, its join key, and its loader
- master_builder.py: Builds a master from a selected subset of sources and writes the Tableau export bundle
- extract_census.py: Command-line entry point (thin wrapper over data_sources.py + master_builder.py)
- app.py: Streamlit UI - build the master, then pick sectors and export
- exporter.py: Pandas-only export engine (sector tables, workbooks, separate files)
- sector_definitions.py: Sector groupings, key columns, and column-to-sector mapping
- gen_health_data.py: Downloads BRFSS (CDC API) and CHR (County Health Rankings website) CSV files from official sources
- fetch_places.py: Downloads CDC PLACES city-level estimates for Delaware
- generate_county_chr.py: Rolls the ZCTA master up to county level (Delaware_County_CHR.csv)
- BRFSS_Delaware.csv: CDC BRFSS 2024 Delaware state-level prevalence (public-health measures)
- CHR_Delaware.csv: County Health Rankings 2022 medical/public-health indicators
- data/brfss/: Cleaned CDC BRFSS ZCTA-level extracts (long format, 40 measures)
- data/census_tract/: CDC PLACES census tract estimates (257 tracts)
- .env: API key configuration
- requirements.txt: Python dependencies
- Delaware_ZCTA_Health_Master_Spatial.geojson: Master Spatial GeoJSON for Tableau

## Installation & Local Execution Instructions

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

# 5. Build the master and write the Tableau exports
python3 extract_census.py

# See every source and the level it merges at
python3 extract_census.py --list

# Build a different level, or hand-pick the sources
python3 extract_census.py --level tract
python3 extract_census.py --sources spatial_zcta,acs,brfss_zcta,metrics
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

Then open the URL printed by Streamlit (default http://localhost:8501).

## Choosing Data Sources (Master Builder)

The master is no longer hardcoded. Tab 1 of the UI, or the `extract_census.py` CLI, lets you choose
exactly which sources are merged, so source blending no longer has to happen in Tableau.

Sources are offered only at geography levels where their join key exists:

| Source | zcta | tract | city | county | Join key |
|---|---|---|---|---|---|
| ZCTA boundaries (Census cartographic, pygris) | base | - | - | - | ZCTA |
| Census ACS 5-Year Data Profile | yes | - | - | - | ZCTA |
| CDC BRFSS state prevalence (2024) | broadcast | broadcast | - | broadcast | every row |
| County Health Rankings (CHR) | yes | yes | - | base | County_FIPS |
| CDC BRFSS ZCTA-level estimates | yes | - | - | - | ZCTA |
| CDC PLACES census tract estimates | - | base | - | - | CensusTractFIPS |
| CDC PLACES city-level estimates | - | - | base | - | City_Name |
| County CHR rollup (derived) | - | - | - | optional | County_FIPS |
| Derived metrics (density, counts) | yes | - | - | - | computed |

Tract and city data cannot be keyed to ZCTAs, so each level builds its own master instead of
mixing geographies. Every build reports per-source join diagnostics: rows in, rows matched, rows
unmatched, duplicate keys, and columns added.

## Tableau Connection Guide

Tab 1 writes a bundle to `./tableau_exports/` using stable filenames, so a Tableau live connection
keeps working after a rebuild:

- `DE_Health_<LEVEL>_Master.csv` - one flat table, one row per geography, all selected attributes
- `DE_Health_<LEVEL>_Master.xlsx` - the same table for spreadsheet work
- `DE_Health_<LEVEL>_Master.geojson` - ZCTA level only, WGS84 geometry plus all attributes
- `DE_Health_<LEVEL>_Field_Manifest.csv` - which source produced each column

The exports are prepared for Tableau on purpose:

- One flat table per level, so no data blending is required
- GeoJSON reprojected to EPSG:4326 (Tableau reads GeoJSON as WGS84) and normalised to a single
  MultiPolygon geometry type with one feature per geography
- `ZIP`, `State` and `County_Name` columns so Tableau assigns geographic roles automatically
- `Latitude` / `Longitude` centroid columns for point maps and dual-axis geometry plus points
- Measures stay numeric and identifiers stay text, so ZIP codes keep their leading zeros
- ASCII-only, unique column names, with the geography keys first

To connect: Tableau -> Connect -> To a File -> Spatial file for the GeoJSON, or Text file for the
CSV. Because the filenames never change, use Data -> Refresh to pick up a new build instead of
repointing the connection. Timestamped copies of every build are archived in `./outputs/`.

## Sector Export UI Usage

1. Launch the UI with `streamlit run app.py` (or `bash start_ui.sh`).
2. In tab 1, choose the geography level and sources, build the master, then write the Tableau
   files. Or pick a dataset, or upload a file, in the sidebar to work with something else.
3. In tab 2, select the sectors you want (Demographics, Socioeconomic, Health Access, BRFSS
   (State Level), CHR - Health Outcomes, CHR - Health Behaviors, CHR - Clinical Care, Calculated
   Metrics, Geographic) and refine individual columns as needed.
4. Preview in tab 3, then export in tab 4 as an Excel workbook with one sheet per sector,
   separate per-sector CSV/Excel files, or a single combined file.

Exports are saved in `./exports/` and `./tableau_exports/` so your workspace stays clean.

## Derived Metrics & Formulas

- Population Density: Total Population / Land Area (Sq. Miles)
- Uninsured Population Volume: (Pct No Health Insurance / 100) * Total Population
- Poverty Population Volume: (Pct Below Poverty / 100) * Total Population
- Senior Population Volume: (Pct Age 65 Plus / 100) * Total Population

## Pipeline Output Schema

- Geographic: ZCTA, County_FIPS, County_Name (5-digit ZCTA and spatial county linkage)
- Demographics: Total_Population, Median_Age, Pct_Age_65_Plus (ACS population & age breakdown)
- Socioeconomic: Median_Household_Income, Pct_Below_Poverty (Economic prosperity indicators)
- Health Access: Pct_No_Health_Insurance, Pct_Broadband_Internet (Essential infrastructure access)
- BRFSS (State Level): CDC BRFSS 2024 Delaware prevalence - smoking, vaping, binge/heavy drinking, obesity, physical inactivity, arthritis, asthma, COPD, heart disease, stroke, diabetes, kidney disease, depression, cancer, fair/poor health, mental/physical distress, uninsured, cost barriers, checkups, colorectal & mammography screening, flu & pneumonia vaccination, HIV testing, oral health, and disability indicators (each with sample size + 95% CI)
- CHR - Health Outcomes: Pct_Poor_Fair_Health, Avg Poor Physical/Mental Health Days, CHR_YPLL_Rate, CHR_Pct_Low_Birthweight, CHR_STI_Chlamydia_Rate, CHR_Teen_Birth_Rate
- CHR - Health Behaviors: Pct_Adult_Smoking, Pct_Adult_Obesity, Pct_Physical_Inactivity, Excessive_Drinking_Pct, CHR_Food_Environment_Index, CHR_Access_Exercise_Opportunities_Pct, CHR_Alcohol_Impaired_Driving_Deaths_Pct
- CHR - Clinical Care: CHR_Uninsured_Pct, CHR_PCP_Ratio_Population, Dentist_Ratio_Population, Mental_Health_Provider_Ratio, CHR_Preventable_Hospital_Stays_Rate, CHR_Mammography_Screening_Pct, CHR_Flu_Vaccination_Pct
- Calculated Metrics: Population_Density_SqMi, Uninsured_Population_Count, No_Broadband_Households_Estimate (Derived volume & density counts)

## Data Sources

- U.S. Census Bureau Cartographic Boundary Files (ZCTA) - Current year via pygris
- U.S. Census Bureau American Community Survey (ACS) 5-Year Data Profile - 2023 (DP02, DP03, DP05 tables)
- CDC Behavioral Risk Factor Surveillance System (BRFSS) Prevalence Data - 2024, Delaware state-level
- CDC Behavioral Risk Factor Surveillance System (BRFSS) - ZCTA-level model-based estimates (40 measures)
- County Health Rankings & Roadmaps (CHR) - 2024 Data Document (underlying data year: 2022), Delaware counties (Kent, New Castle, Sussex)
- CDC PLACES: Local Data for Better Health - City/place-level and census tract-level model-based estimates for Delaware

## Tableau Visualization Guide

1. Open Tableau and select Connect -> Spatial File.
2. Select `tableau_exports/DE_Health_ZCTA_Master.geojson` (or the repo-root
   Delaware_ZCTA_Health_Master_Spatial.geojson).
3. Open a new Worksheet and double-click Geometry.
4. Drag ZIP (or ZCTA) onto Detail on the Marks Card to display individual ZIP code boundaries.
5. Drag any health metric onto Color.

Prefer the `tableau_exports/` bundle: those filenames never change, so a saved workbook keeps
working after a rebuild. The attribute table is also in the GeoJSON, so a single spatial connection
carries every measure and no blending is needed.

## Troubleshooting

- Tableau Field Mismatches Warning Icons: if red exclamation marks appear on fields, the connection
  is probably still pointing at a file that was renamed. Point Tableau at `tableau_exports/` instead:
  those filenames never change, so use Data -> Refresh rather than repointing. Geometry-related
  warnings are also avoided because the GeoJSON is written as a single MultiPolygon geometry type in
  EPSG:4326.
- Missing Geometry Fields in CSV Exports: the tabular CSV and Excel outputs drop spatial polygon
  geometry by design to keep file sizes workable in spreadsheets. To build polygon maps, connect to
  the generated .geojson spatial file; to build point maps, the CSV carries Latitude and Longitude.
- A Source Was Skipped in the Build: the join diagnostics table in tab 1 names the missing key. The
  usual cause is choosing a source whose key is not present at that geography level, for example
  County Health Rankings at ZCTA level without the boundary source that supplies County_FIPS.
- Unmatched Rows in a Build: unmatched counts mean the source genuinely has no record for that
  geography. ZIP 19901 to 19999 style ZCTAs outside a source's coverage are the common case, for
  example the 7 ZCTAs with no county CHR record.
- Census API Rate Limits: if running bulk extractions repeatedly, populate your CENSUS_API_KEY in the
  .env file to prevent Census API request throttling.
