# Data Provenance & Licensing — Healthcare Workforce Inequities

Reference for **"Healthcare Workforce Inequities: An Analytical Evaluation of Social
Determinants of Health, Provider Ratios, and Chronic Disease Burdens in Delaware."**

It answers the two questions reviewers most often raise:

1. **Are the provider ratios and chronic-disease measures paid / closed sources?**
   **No.** Every measure in this project comes from a **free, public-domain federal
   download**. Nothing requires a licence fee, a vendor contract, an account, or a
   signed data-use agreement.
2. **Where did each number come from, and can it be re-downloaded?**
   Every figure is reproduced in `raw/` as an unmodified publisher snapshot with a
   SHA-256 checksum, and can be re-fetched or downloaded from the app at any time.

---

## 1. Provider ratios — where they actually come from

Provider ratios (population per primary care physician, per dentist, per mental health
provider) are often mistaken for licensed data. They are not. County Health Rankings
computes its ratios from the **HRSA Area Health Resources Files (AHRF)**, a free
public-domain federal file.

| | |
|---|---|
| **Dataset** | Area Health Resources Files (AHRF), 2024–2025 CSV release |
| **Publisher** | Health Resources & Services Administration (HRSA), U.S. Dept. of Health & Human Services |
| **Cost** | **Free.** Direct `.zip` download — no login, no account, no data-use agreement |
| **Download** | `https://data.hrsa.gov/DataDownload/AHRF/AHRF_2024-2025_CSV.zip` (~23 MB) |
| **Landing page** | <https://data.hrsa.gov/topics/health-workforce/ahrf> |
| **Licence** | Public domain (U.S. Government work) |
| **Local snapshot** | `raw/hrsa_ahrf_2025_de_counties_raw.csv` |
| **Geography** | **County** (Kent 10001, New Castle 10003, Sussex 10005) |
| **Content** | Provider counts by profession/sex/race/vintage **and** population denominators (`pop_popn_est_23`) |

### Reproducing the ratios from first-party counts

Because AHRF ships both the numerator and the denominator, the ratios can be recomputed
independently rather than accepted as published:

```bash
python3 generate_provider_ratios.py     # -> Delaware_Provider_Ratios_From_AHRF.csv
```

Recomputed ratio vs. the ratio County Health Rankings published:

| County | Provider | AHRF count | AHRF ratio | CHR ratio | Difference |
|---|---|---:|---:|---:|---:|
| Kent | Primary Care Physicians | 83 | 2,287 | 1,980:1 | +15.5% |
| Kent | Dentists | 78 | 2,433 | 2,460:1 | −1.1% |
| New Castle | Primary Care Physicians | 473 | 1,223 | 1,155:1 | +5.9% |
| New Castle | Dentists | 342 | 1,692 | 1,723:1 | −1.8% |
| Sussex | Primary Care Physicians | 136 | 1,938 | 1,628:1 | +19.0% |
| Sussex | Dentists | 58 | 4,543 | 4,490:1 | +1.2% |

The small differences are expected: CHR applies its own provider definition and data
vintage. **The county ranking is identical in both** (New Castle best supplied, Sussex
worst for primary care), which is what the paper's analysis relies on.

> **Citable claim.** "Provider ratios were derived from the HRSA Area Health Resources
> Files (AHRF), a free public-domain federal dataset, and independently recomputed from
> AHRF provider counts and population denominators."

---

## 2. Chronic disease measures — where they actually come from

Chronic disease burdens (diabetes, hypertension, asthma, COPD, coronary heart disease,
stroke, depression, arthritis, cancer, high cholesterol) come from **CDC PLACES**, also
free and public domain.

> **Important geographic note.** PLACES publishes **separate datasets per geography** —
> county, census tract, place/city, and ZCTA are four *different* files. The pipeline
> originally used the **place/city** release, which meant chronic-disease values were
> borrowed from a city geography. It now uses the **ZCTA release**, so these measures are
> reported directly on the same ZCTAs as the rest of the master.

> **Also note what these values are.** PLACES figures are **model-based estimates**, not
> direct counts. CDC derives them from the statewide BRFSS survey using small-area
> modelling, so a ZCTA-level estimate carries real uncertainty. Every measure ships with
> the publisher's confidence limits, and those are archived too.

| | ZCTA release (used) | City/place release (legacy) |
|---|---|---|
| **Dataset** | PLACES: Local Data for Better Health — ZCTA | PLACES — Place |
| **Socrata id** | `4r2x-hcfq` (2024 release) | `eav7-hnsx` |
| **Cost / licence** | **Free**, public domain | **Free**, public domain |
| **Geography** | **ZCTA** (65 Delaware ZCTAs) | City / place |
| **Local snapshot** | `raw/cdc_places_2024_de_zcta_raw.csv` | `raw/cdc_places_2024_de_city_raw.csv` |
| **Rows** | 2,597 (65 ZCTAs × 41 measures) | 6,320 |

Delaware ZCTA coverage was verified directly against the API: 65 ZCTAs, spanning all
six categories (Health Outcomes, Health Risk Behaviors, Health Status, Prevention,
Disability, Health-Related Social Needs).

PLACES does not publish an estimate for every Delaware ZCTA. **4 of the master's 68 ZCTAs
(`19902`, `19716`, `19735`, `19736`) have no PLACES value** and their PLACES columns are
left NULL — they are never imputed or filled from another geography.

---

## 2b. Delaware ZCTA selection — a correction worth knowing about

The master holds **68 ZCTAs**. Reaching that number correctly took two filters, and the
original pipeline only applied one.

Clipping the TIGER ZCTA file to the Delaware state boundary keeps every ZCTA that *touches*
Delaware, and border ZCTAs keep their full multi-state polygon. Delaware's north-east
corner touches Maryland and Pennsylvania, so the original centroid test alone let **25
Maryland, Pennsylvania and New Jersey ZCTAs** into the master — including ZCTA `21921`
(Annapolis, MD) with 245 km² of land area. Their ACS populations were then merged in:

| | Rows | Total population |
|---|---:|---:|
| Master **before** the fix | 98 | 1,190,837 |
| Master **after** the fix | 68 | **982,285** |

That was a **21.2% overstatement** of Delaware's population, and the New Jersey and
Philadelphia-area rows were assigned to Kent, New Castle and Sussex counties via
`County_FIPS`.

Both `fetch_raw_data.py` and `extract_census.py` now require **both** conditions:

1. the ZCTA's centroid falls inside the Delaware state polygon, **and**
2. the ZCTA's ZIP is a Delaware ZIP (`197`, `198`, `199`).

Either test alone is insufficient. If you have already written state-level totals, means
or percentages into the paper, they need recomputing — they were inflated by about 21%.

---

## 3. Full source inventory

Every source is free. Regenerate or re-verify everything with:

```bash
python3 fetch_raw_data.py            # re-download all snapshots
python3 fetch_raw_data.py --verify   # re-check live URLs + checksums
```

| # | Dataset | Publisher | Geography | Cost | Licence |
|---|---|---|---|---|---|
| 1 | TIGER/Line 2020 ZCTA boundaries | Census Bureau | ZCTA | Free | Public domain |
| 2 | TIGER/Line 2020 county boundaries | Census Bureau | County | Free | Public domain |
| 3 | ACS 2021 5-Year Data Profile | Census Bureau | ZCTA | Free | Public domain |
| 4 | BRFSS 2024 Prevalence | CDC | **State** | Free | Public domain |
| 5 | County Health Rankings 2024 | CHR&R / UW PHI | **County** | Free | Free with attribution |
| 6 | PLACES 2024 Place | CDC | City / place | Free | Public domain |
| 7 | **AHRF 2024–2025** | **HRSA** | **County** | **Free** | **Public domain** |
| 8 | **PLACES 2024 ZCTA** | **CDC** | **ZCTA** | **Free** | **Public domain** |

### Honest statement about geographic level

Only ACS, the TIGER boundaries, and the PLACES **ZCTA** release are genuinely
ZCTA-level. BRFSS is a **statewide survey**, and CHR/AHRF report at **county** level, so
those figures repeat across every ZCTA in the state or county. This is not hidden:
`Delaware_ZCTA_Health_Master_Column_Provenance.csv` labels every column with the
geography it was really collected at, and the app exposes the same field as a filter
(*"Filter measures by the geography they were actually collected at"*).

### What this means for the paper's claims

- Provider-supply analysis is **county-level** (3 counties). Do not describe provider
  ratios as a ZCTA-level measure.
- Chronic-disease measures from PLACES **are** ZCTA-level.
- SDOH / demographics from ACS **are** ZCTA-level.

---

## 4. Downloading all the data

Three ways, all giving you the real files:

1. **In the app** — each raw source's citation panel has a *Download raw snapshot*
   button, and *All raw sources & citations* has a single **Download ALL snapshots (ZIP)**
   button.
2. **From the command line** — the snapshots are plain files in `raw/`.
3. **Straight from the publishers** — every URL in `raw/SOURCES.md` is a direct, free
   download with no authentication.

Run the app:

```bash
streamlit run app.py
```

---

## 5. Suggested reviewer response

> The provider-ratio and chronic-disease data are not licensed or proprietary. They come
> from two free public-domain federal datasets published by HRSA and CDC respectively.
> Provider ratios were recomputed directly from the HRSA Area Health Resources Files
> (AHRF) provider counts and population denominators — both included in the archived
> snapshot — and these reproduce the County Health Rankings ratios to within a few
> percent, yielding an identical county ranking. Chronic-disease measures come from CDC
> PLACES, and we use the ZCTA release so the measures align with the ZCTA geography of
> the rest of the study; these are CDC's model-based small-area estimates, and we report
> them with their published confidence limits rather than as direct counts. Every dataset
> is archived unmodified with a SHA-256 checksum and a direct publisher URL, so all
> results can be independently re-downloaded and reproduced. Per-column provenance for
> every measure, including the true geography of each, is shipped with the master
> dataset.

---

## 6. Things to be careful about when writing this up

These are the places a reviewer is most likely to catch an overstatement:

1. **Recompute every state-level figure.** Before the ZCTA-selection fix the master's
   population was 21.2% too high (1,190,837 vs 982,285). Any total, mean, or percentage
   you computed from the old master is affected.

2. **Provider ratios are county-level, not ZCTA-level.** They come from AHRF and CHR,
   which report for Kent, New Castle and Sussex. Calling them a ZCTA measure would be
   wrong — 3 observations cannot support ZCTA-level inference.

3. **PLACES values are modelled, not observed.** They are small-area estimates derived
   from a statewide survey. Always report them with confidence limits, and avoid
   describing small differences between neighbouring ZCTAs as meaningful without
   testing whether the confidence intervals even separate.

4. **BRFSS figures are statewide.** Every Delaware ZCTA row shows the same value. They
   cannot explain any within-state variation.

5. **4 ZCTAs have no PLACES data** (`19902`, `19716`, `19735`, `19736`). Exclude them
   from any PLACES-based analysis and say so, rather than letting them drop out silently.