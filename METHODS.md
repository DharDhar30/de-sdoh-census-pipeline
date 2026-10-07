# METHODS — Measures, Naming, and Access Framework

## 1. Access framework (mentor item #7)

Every measure is grouped under Penchansky & Thomas's five access dimensions
plus need, so dashboards and write-ups follow one structure:

| Dimension | Question | Example measures in this pipeline |
|---|---|---|
| Need | How much care does the population need? | PLACES chronic disease, teeth lost, depression; ACS age 65+; PLACES disability |
| Availability | Is there enough supply? | HPSA status (future). Provider supply: refer to existing DE Health Force data, not new counts (§3 out of scope) |
| Accessibility | Can people physically reach care? | ACS households with no vehicle (future); public-transit commute; PLACES transportation barrier |
| Affordability | Can people pay for care? | ACS uninsured (published `DP03_0099E` count); BRFSS cost barrier (state ref); poverty (`S1701_C02_001E` count) |
| Acceptability | Does care fit the population? | Limited English proficiency; language spoken at home (`DP02_0114E` count) |
| Accommodation | Do services fit people's lives? | Broadband access / telehealth readiness (`DP02_0154E`-based household count) |

## 2. Naming convention (mentor item #6)

- **Case:** lower `snake_case` everywhere for NEW columns
  (`acs_poverty_pct`, not `Pct_Below_Poverty`).
- **Pattern:** `<source>_<measure>[_<qualifier>]_<unit>`, e.g.
  `places_dental_visit_crude_pct`, `acs_no_vehicle_hh_count`.
- **Unit suffixes:** `_pct` (0–100), `_count`, `_per100k`, `_rate100k`,
  `_ratio`, `_index`, `_usd`, `_sqmi`, `_min` (travel minutes).
- **Uncertainty:** `_moe`, `_ci_low`, `_ci_high`, `_cv`, `_flag` suffixed
  onto the parent column.
- **Derived metrics:** `calc_` prefix (e.g. `calc_access_index`) with the
  formula recorded in §3 below.
- **Keys:** `geoid`, `geo_level`, `geo_name`, `county_fips`, `county_name` —
  identical across county, ZCTA and tract tables.
- **Same measure, same name** at county, ZCTA and tract level, so one
  Tableau sheet can switch levels with a parameter.
- **Files:** `<level>_master_<release>.csv` / `.geojson`; no spaces; release
  year in the name.

> **Migration status (Oct 2026):** the shipped master still carries legacy
> names (`Pct_Below_Poverty`, `CHR_*`, `PLACES_Pct_*`) so the Streamlit app
> and existing Tableau workbooks keep working. New columns MUST follow this
> convention; the full rename ships as a versioned breaking change with a
> compat view.

## 3. Derived-metric formulae (`calc_`)

| Column | Formula | Inputs (published counts) |
|---|---|---|
| `Population_Density_SqMi` | `Total_Population / Land_Area_SqMi` | ACS `DP05_0001E`; TIGER `ALAND20` |
| `Uninsured_Population_Count` | direct | ACS `DP03_0099E` (universe: civilian non-institutionalized, `DP03_0095E`) |
| `Poverty_Population_Count` | direct | ACS `S1701_C02_001E` (poverty universe `S1701_C01_001E`; `DP03_0128E` only duplicates the percent) |
| `Seniors_65_Plus_Count` | direct | ACS `DP05_0024E` |
| `No_Broadband_Households_Estimate` | `DP02_0152E − DP02_0154E` | ACS household universe minus broadband subscriptions — households, NOT people |

No other back-calculation from percentages is permitted (mentor issue #7).

## 4. Quality gates (mentor item #9)

Before sharing ANY result:
1. 68 Delaware ZCTAs (relationship file); pop total within 1% of state ACS.
2. County labels from relationship file (19952→Kent, 19734→New Castle).
3. No published/derived measure negative.
4. County table == CHR source exactly (Kent deaths = raw value for the
   release vintage).
5. BRFSS/CHR never on ZCTA maps; PLACES crude-only with CIs.
