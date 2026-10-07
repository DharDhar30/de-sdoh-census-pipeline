# Dataset Catalogue

Curated inventory of every dataset this pipeline consumes (mentor item #5).
Rule: **before adding any new dataset, add a row here first** with its
release year, geography vintage, known caveats, and pull command.

| Dataset | Steward | County | ZCTA | Tract | Release | Geography vintage | What it adds | How to pull | Known caveats |
|---|---|---|---|---|---|---|---|---|---|
| ACS 5-Year Data Profile (DP02/DP03/DP05) | U.S. Census Bureau | Yes (DP05_0001E county) | Yes | Yes (not pulled) | 2024 5-yr (2020–2024) | 2020 ZCTA boundaries | Demographics, poverty, insurance, disability proxies, broadband, vehicles, language; published `E` counts + denominators | Census API with key; `extract_census.fetch_acs_data()` / `fetch_raw_data --only census_acs_2024_zcta_de` | Missing-value sentinels (-666666666, -888888888, …) arrive as numbers — masked via `≤ -111111111 → NaN` after `pd.to_numeric`. Percent universes differ (insurance = civilian non-institutionalized; poverty = poverty universe), so counts use published `E` vars, never percent×population. |
| ZCTA-to-County Relationship File | U.S. Census Bureau | Yes (defines it) | Yes (defines it) | — | 2020 | 2020 ZCTA/county | Authoritative DE ZCTA list (68) + primary county (largest land-area share) + multi-county flags | Direct `.txt` download; `fetch_raw_data --only census_zcta_county_rel_2020` | 5 ZCTAs span >1 county (19938, 19950, 19952, 19963, 19977) — flagged, assigned by largest share. Never assign counties from ZIP prefixes or spatial intersects. |
| CDC PLACES, ZCTA release (Socrata `qnzd-25i4`) | CDC | — | Yes | — | 2025 (model yrs 2022–2023) | 2020 ZCTA | Chronic disease, prevention, dental, depression/mental distress, disability, social needs — genuinely ZCTA-level | Socrata API; match on `measureid`; crude only (`datavaluetypeid='CrdPrv'`) | Model-based small-area estimates, not observed counts — report with CI limits. No estimate for some ZCTAs (NULL, not zero). City release (`eav7-hnsx`) ships crude+age-adjusted duplicates — filter before pivot. |
| County Health Rankings (v4 workbook) | UW Population Health Inst. | Yes | — | — | 2025 (clinical-care source yr 2022) | County | Health outcomes, behaviours, clinical care; county reference table only | Annual `.xlsx` download; `Select`+`Additional` sheets merged on FIPS | County grain only — never broadcast onto ZCTA rows or re-aggregate ZCTA→county (that inflated Kent deaths ~19×). Quartile columns retired from release (kept as NaN for schema). Clinical-care source year (2022) lags release year. |
| BRFSS Prevalence (Socrata `dttw-5yxu`) | CDC | — | — | — | 2024 | State | State benchmark incl. oral/mental health; state reference table only | `data.cdc.gov` API; Overall breakout | State grain only — identical value in every ZCTA if joined; keep in `BRFSS_Delaware.csv`, never map at ZCTA level. |
| TIGER/Line Cartographic Boundaries (ZCTA + county) | U.S. Census Bureau | Yes | Yes | — | 2020 | 2020 | Geometries + land/water area; `County_FIPS`/`County_Name` keys | `pygris` (`zctas(year=2020, cb=True)`, `counties(state='DE')`) | `gpd.clip` to DE keeps every touching ZCTA (30 out-of-state) — always filter through the relationship file first. |
| ~~HRSA AHRF 2024–2025 (provider supply)~~ | ~~HRSA~~ | ~~Yes~~ | — | — | ~~2024–2025~~ | County | ~~Provider counts~~ — **OUT OF SCOPE** (mentor §3): county-level counts duplicate/conflict with the DE Health Force dashboard's granular supply data | Archived raw retained; no longer consumed by the pipeline | AHRF county counts ≠ dashboard counts; supplement need/access data instead of duplicating supply. |

## Adding a new dataset — checklist

1. Add a catalogue row above (release, vintage, caveats, pull command).
2. Add a `fetch_raw_data.py` source with URL, landing page, licence, SHA-256.
3. Add a sector + provenance entry in `sector_definitions.py`.
4. Document the true geography; if it isn't ZCTA-level, it gets its own
   table — never broadcast onto ZCTA rows.
