# Raw Data Sources

Proof-of-provenance index for every dataset this pipeline consumes. Each file in this
directory is an **unmodified copy** of what a public publisher served - original column
names, original values, no cleaning, no renaming and no cross-source joins.

Manifest generated: **2026-10-05T16:37:27Z** by `fetch_raw_data.py`.

Re-verify everything at any time:

```bash
python3 fetch_raw_data.py --verify
```

## Archived datasets

| # | Dataset | Publisher | Geography | Rows x Cols | Snapshot |
|---|---|---|---|---|---|
| 1 | Census TIGER 2020 ZCTA Boundaries (DE) | U.S. Census Bureau | ZCTA | 68 x 7 | `raw/census_tiger_2020_de_zctas_raw.csv` |
| 2 | Census TIGER 2020 County Boundaries (DE) | U.S. Census Bureau | County | 3 x 12 | `raw/census_tiger_2020_de_counties_raw.csv` |
| 3 | Census ACS 2024 5-Year Profile (ZCTA) | U.S. Census Bureau | ZCTA | 68 x 10 | `raw/census_acs_2024_zcta_de_raw.csv` |
| 4 | CDC BRFSS 2024 Prevalence (DE, state level) | U.S. Centers for Disease Control and Prevention | State | 165 x 27 | `raw/cdc_brfss_2024_de_raw.csv` |
| 5 | County Health Rankings 2025 (DE counties) | County Health Rankings & Roadmaps (Univ. of Wisconsin Population Health Institute) | County | 3 x 618 | `raw/chr_2025_de_counties_raw.csv` |
| 6 | CDC PLACES 2025 Place-Level (DE cities) | U.S. Centers for Disease Control and Prevention | City / place | 6,320 x 20 | `raw/cdc_places_2025_de_city_raw.csv` |
| 7 | HRSA AHRF 2024-2025 (DE counties, provider supply) | Health Resources & Services Administration (HRSA), U.S. Dept. of Health & Human Services | County | 3 x 3395 | `raw/hrsa_ahrf_2025_de_counties_raw.csv` |
| 8 | CDC PLACES 2025 ZCTA-Level (DE chronic disease & prevention) | U.S. Centers for Disease Control and Prevention | ZCTA | 2,597 x 18 | `raw/cdc_places_2025_de_zcta_raw.csv` |

## Per-source detail

### 1. Census TIGER 2020 ZCTA Boundaries (DE)

- **Publisher:** U.S. Census Bureau
- **Dataset:** TIGER/Line Cartographic Boundary File - 2020 ZCTA (cb_2020_us_zcta520_500k), clipped to Delaware
- **Vintage:** 2020
- **Geography:** ZCTA (Delaware)
- **Retrieved (UTC):** 2026-10-03T16:04:46Z
- **File:** `raw/census_tiger_2020_de_zctas_raw.csv` (68 rows x 7 columns)
- **Source URL:** `https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip`
- **Landing page:** https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html
- **License / terms:** Public domain (U.S. Government work)
- **SHA-256:** `a76ccda7421b031746a1b2f5d3d02dcfe87559cc734ee175b95a36d2afa7b26f`
- **Note:** Every attribute column the TIGER ZCTA shapefile ships with, geometry dropped so it can be archived as CSV. Clipped to the Delaware state boundary and restricted to ZCTAs whose centroid is inside Delaware AND whose ZIP is a Delaware ZIP (197/198/199). Both filters are required: the centroid test alone keeps border ZCTAs belonging to MD/PA/NJ.

### 2. Census TIGER 2020 County Boundaries (DE)

- **Publisher:** U.S. Census Bureau
- **Dataset:** TIGER/Line Cartographic Boundary File - 2020 counties (cb_2020_us_county_500k), Delaware
- **Vintage:** 2020
- **Geography:** County (Delaware)
- **Retrieved (UTC):** 2026-10-02T16:47:47Z
- **File:** `raw/census_tiger_2020_de_counties_raw.csv` (3 rows x 12 columns)
- **Source URL:** `https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_500k.zip`
- **Landing page:** https://www.census.gov/geographies/mapping-files/time-series/geo/carto-boundary-file.html
- **License / terms:** Public domain (U.S. Government work)
- **SHA-256:** `50dcd867a2bdb426028d8fcd01fb65702ed42573a15d3f109968b4ff3229f467`
- **Note:** All 3 Delaware counties; source of County_FIPS / County_Name in the master.

### 3. Census ACS 2024 5-Year Profile (ZCTA)

- **Publisher:** U.S. Census Bureau
- **Dataset:** American Community Survey 5-Year Data Profile (DP02 / DP03 / DP05)
- **Vintage:** 2024 5-year estimates (2020-2024)
- **Geography:** ZCTA (Delaware rows of a national response)
- **Retrieved (UTC):** 2026-10-05T16:01:39Z
- **File:** `raw/census_acs_2024_zcta_de_raw.csv` (68 rows x 10 columns)
- **Source URL:** `https://api.census.gov/data/2024/acs/acs5/profile?get=DP05_0001E,DP05_0018E,DP05_0024PE,DP03_0062E,DP03_0128PE,DP03_0099PE,DP03_0021PE,DP02_0154PE,DP02_0114PE&for=zip%20code%20tabulation%20area:*&key=***REDACTED***`
- **Landing page:** https://data.census.gov/
- **License / terms:** Public domain (U.S. Government work)
- **Rows downloaded before regional filter:** 33,772
- **SHA-256:** `139db60df3d5c84352676ce0bc1386cf6cd31bc9876aaa5465eed1b9ec4636d1`
- **Note:** API variable codes retained (no renaming). 33,772 ZCTAs were returned nationwide; the snapshot keeps the Delaware rows used by the pipeline.

### 4. CDC BRFSS 2024 Prevalence (DE, state level)

- **Publisher:** U.S. Centers for Disease Control and Prevention
- **Dataset:** Behavioral Risk Factor Surveillance System - Prevalence Data (Socrata resource dttw-5yxu)
- **Vintage:** 2024
- **Geography:** State (Delaware) - broadcast onto ZCTA rows downstream
- **Retrieved (UTC):** 2026-10-02T16:47:58Z
- **File:** `raw/cdc_brfss_2024_de_raw.csv` (165 rows x 27 columns)
- **Source URL:** `https://chronicdata.cdc.gov/resource/dttw-5yxu.csv?$where=locationabbr='DE' and break_out_category='Overall' and year=2024&$limit=10000`
- **Landing page:** https://chronicdata.cdc.gov/
- **License / terms:** Public domain (U.S. Government work)
- **SHA-256:** `6bd3f26703524f876fc3cbac5b602a63d4cdb3829b0dc80bd476f8c524dac69c`
- **Note:** Byte-for-byte copy of the CDC Socrata CSV response (no re-encoding, no column renaming). This is a STATE-level survey, so every row here describes Delaware as a whole - not an individual ZCTA.

### 5. County Health Rankings 2025 (DE counties)

- **Publisher:** County Health Rankings & Roadmaps (Univ. of Wisconsin Population Health Institute)
- **Dataset:** 2025 County Health Rankings Data v4 (`Select Measure Data` + `Additional Measure Data` sheets, merged on FIPS)
- **Vintage:** 2025 release (clinical-care source year 2022; see Sources & Years sheets)
- **Geography:** County (Kent, New Castle, Sussex) - broadcast onto ZCTA rows downstream
- **Retrieved (UTC):** 2026-10-05T16:02:15Z
- **File:** `raw/chr_2025_de_counties_raw.csv` (3 rows x 618 columns)
- **Source URL:** `https://www.countyhealthrankings.org/sites/default/files/media/document/2025%20County%20Health%20Rankings%20Data%20-%20v4.xlsx`
- **Landing page:** https://www.countyhealthrankings.org/health-data/methodology-and-sources/data-documentation
- **License / terms:** Free for public use with attribution (CHR&R / UW PHI)
- **SHA-256:** `5f795de7de4e48b41dfc668c6d2a9a6606cb98a7fb6b9f307cd498dd15750844`
- **Note:** Workbook sheets 'Select Measure Data' + 'Additional Measure Data' merged on FIPS, every measure column kept, Delaware counties only (FIPS 10001/10003/10005). The two header rows the publisher ships are joined with '__'; no values are altered or rounded.

### 6. CDC PLACES 2025 Place-Level (DE cities)

- **Publisher:** U.S. Centers for Disease Control and Prevention
- **Dataset:** PLACES: Local Data for Better Health - place/city release, 2025 (Socrata eav7-hnsx)
- **Vintage:** 2025 release (model years 2022-2023)
- **Geography:** City / place (Delaware)
- **Retrieved (UTC):** 2026-10-05T16:37:27Z
- **File:** `raw/cdc_places_2025_de_city_raw.csv` (6,320 rows x 20 columns)
- **Source URL:** `https://data.cdc.gov/resource/eav7-hnsx.json?%24where=statedesc%3D%27Delaware%27&%24limit=50000`
- **Landing page:** https://www.cdc.gov/places/index.html
- **License / terms:** Public domain (U.S. Government work)
- **SHA-256:** `128fb2ee94408da3443c5e9cb2cc78747b5d6ad8f003bf11391dd089dc2030b7`
- **Note:** Untouched API rows - one row per place x measure with the publisher's own field names. PLACES publishes place/city, county, census-tract and ZCTA files as SEPARATE datasets; this endpoint is the place/city release.

### 7. HRSA AHRF 2024-2025 (DE counties, provider supply)

- **Publisher:** Health Resources & Services Administration (HRSA), U.S. Dept. of Health & Human Services
- **Dataset:** Area Health Resources Files (AHRF) 2024-2025 CSV release - health professional (AHRF2025hp) + population (AHRF2025pop)
- **Vintage:** 2024-2025 release (counts carry per-column vintage suffixes, e.g. _23)
- **Geography:** County (Kent, New Castle, Sussex)
- **Retrieved (UTC):** 2026-10-03T15:17:01Z
- **File:** `raw/hrsa_ahrf_2025_de_counties_raw.csv` (3 rows x 3395 columns)
- **Source URL:** `https://data.hrsa.gov/DataDownload/AHRF/AHRF_2024-2025_CSV.zip`
- **Landing page:** https://data.hrsa.gov/topics/health-workforce/ahrf
- **License / terms:** Public domain (U.S. Government work)
- **Rows downloaded before regional filter:** 3,235
- **SHA-256:** `7b0984fbbb6a6c94eb3f908ce99b9785da0ab893934e578e6bfcf3333428c6c7`
- **Note:** Delaware county rows (FIPS 10001, 10003, 10005) from the 'AHRF2025hp.csv' health-professional file joined to 'AHRF2025pop.csv' on fips_st_cnty. Health-professional columns carry the publisher's own names and vintage suffix (e.g. md_nf_prim_care_pc_excl_rsdnt_23); population columns are prefixed 'pop_' so the two files' overlapping short names stay distinct. Values are exactly as published - AHRF suppresses small counts, so blanks mean 'suppressed', not zero.

### 8. CDC PLACES 2025 ZCTA-Level (DE chronic disease & prevention)

- **Publisher:** U.S. Centers for Disease Control and Prevention
- **Dataset:** PLACES: Local Data for Better Health - ZCTA release, 2025 (Socrata qnzd-25i4)
- **Vintage:** 2025 release (model years 2022-2023)
- **Geography:** ZCTA (Delaware) - directly reported, NOT broadcast from a city file
- **Retrieved (UTC):** 2026-10-05T16:35:29Z
- **File:** `raw/cdc_places_2025_de_zcta_raw.csv` (2,597 rows x 18 columns)
- **Source URL:** `https://data.cdc.gov/resource/qnzd-25i4.json?%24where=locationname+like+%27197%25%27+OR+locationname+like+%27198%25%27+OR+locationname+like+%27199%25%27&%24limit=50000`
- **Landing page:** https://www.cdc.gov/places/index.html
- **License / terms:** Public domain (U.S. Government work)
- **Rows downloaded before regional filter:** 2,597
- **SHA-256:** `9c91912436d8ac03cbb4125af11c9cb7bb9584a65f42fdf8d4a6384cc4ed64ec`
- **Note:** Untouched API rows - one row per ZCTA x measure with the publisher's own field names. 65 Delaware ZCTAs x 40 measures. This is the ZCTA release of PLACES, so the chronic-disease measures (diabetes, hypertension, asthma, COPD, depression, ...) are reported ON the ZCTAs rather than being borrowed from a city-level file and broadcast.

## Notes on geography

- ACS 2024, the TIGER boundaries and the PLACES ZCTA release are genuinely
  ZCTA-level.
- PLACES values are **model-based estimates** produced from BRFSS survey data by
  small-area modelling - they are not direct counts of conditions. The publisher's
  confidence limits are archived alongside every measure. PLACES does not publish an
  estimate for every ZCTA; those rows are NULL rather than filled in.
- BRFSS is a **state** survey, so its Delaware figures describe the whole state and
  are broadcast onto every ZCTA row downstream (identical across ZCTAs).
- CHR and the HRSA AHRF provider ratios report at **county** level, so their figures
  are broadcast onto the ZCTAs in that county via `County_FIPS`.
- The `Geography_Level` field in `Delaware_ZCTA_Health_Master_Column_Provenance.csv`
  (also the `Column_Provenance` sheet of the master workbook) labels each measure,
  and the UI's 'geography they were actually collected at' filter uses the same field,
  so non-ZCTA measures can be filtered out in the UI or in Tableau.

## Delaware ZCTA selection

The master contains **68** ZCTAs. Getting that number right needed two filters, not
one. Clipping the TIGER ZCTAs to the Delaware state boundary keeps every ZCTA that
*touches* Delaware, and border ZCTAs keep their full multi-state polygon - Delaware's
north-east corner touches Maryland and Pennsylvania. A centroid test alone therefore
let 25 Maryland, Pennsylvania and New Jersey ZCTAs through, including ZCTA 21921
(Annapolis, MD). Their ACS populations were merged in, inflating the master's total
population from 982,285 to 1,190,837 - an overstatement of about 21%, with the NJ and
Philadelphia-area rows assigned to Kent, New Castle and Sussex counties.

So `fetch_raw_data.py` and `extract_census.py` both require **both** conditions:

1. the ZCTA's centroid falls inside the Delaware state polygon, and
2. the ZCTA's ZIP is a Delaware ZIP (`197`, `198` or `199`).

Either test on its own is insufficient.
