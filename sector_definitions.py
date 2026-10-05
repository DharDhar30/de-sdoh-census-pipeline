"""Sector definitions for the Delaware ZCTA Health Master dataset.

Every column in the master dataset belongs to one themed sector so the UI can
offer "pick a sector -> export" workflows that mirror the README schema:

    Geographic / Demographics / Socioeconomic / Health Access /
    BRFSS (State Level) / CHR (Health Outcomes, Behaviors, Clinical Care) /
    Calculated Metrics

BRFSS columns carry a "_Sample_Size", "_CI_Low" and "_CI_High" companion for
every measure so confidence intervals stay exportable without polluting other
sectors. Columns not listed here are treated as "Other" and can still be picked
manually in the UI.
"""

# Keep the annotations below lazy so the PEP 604 unions ("str | None") and
# builtin generics ("list[str]") work on Python 3.9 as well as 3.10+.
from __future__ import annotations

# ---------------------------------------------------------------------------
# BRFSS state-level measure stems (CDC BRFSS Prevalence 2024, Delaware)
# ---------------------------------------------------------------------------
BRFSS_BASE_MEASURES = [
    "BRFSS_Pct_Cigarette_Smoking",
    "BRFSS_Pct_Smoke_Every_Day",
    "BRFSS_Pct_Ecigarette_Use",
    "BRFSS_Pct_Binge_Drinking",
    "BRFSS_Pct_Heavy_Drinking",
    "BRFSS_Pct_Adult_Obesity",
    "BRFSS_Pct_Adult_Overweight",
    "BRFSS_Pct_No_Physical_Activity",
    "BRFSS_Pct_Arthritis",
    "BRFSS_Pct_Current_Asthma",
    "BRFSS_Pct_Ever_Asthma",
    "BRFSS_Pct_COPD",
    "BRFSS_Pct_Coronary_Heart_Disease",
    "BRFSS_Pct_Had_Stroke",
    "BRFSS_Pct_Diabetes",
    "BRFSS_Pct_Kidney_Disease",
    "BRFSS_Pct_Depression",
    "BRFSS_Pct_Skin_Cancer",
    "BRFSS_Pct_Other_Cancer",
    "BRFSS_Pct_Fair_Poor_Health",
    "BRFSS_Pct_Frequent_Mental_Distress",
    "BRFSS_Pct_Frequent_Physical_Distress",
    "BRFSS_Pct_Uninsured",
    "BRFSS_Pct_Uninsured_18_64",
    "BRFSS_Pct_Cost_Barrier_Medical_Care",
    "BRFSS_Pct_No_Personal_Doctor",
    "BRFSS_Pct_Routine_Checkup_Past_Year",
    "BRFSS_Pct_Colorectal_Screening_45_75",
    "BRFSS_Pct_Mammography_40_74",
    "BRFSS_Pct_Flu_Vaccinated_65_Plus",
    "BRFSS_Pct_Pneumonia_Vaccinated_65_Plus",
    "BRFSS_Pct_HIV_Tested_Ever",
    "BRFSS_Pct_Permanent_Teeth_Removed",
    "BRFSS_Pct_All_Teeth_Removed_65_Plus",
    "BRFSS_Pct_Walking_Difficulty",
    "BRFSS_Pct_Seeing_Difficulty",
    "BRFSS_Pct_Cognitive_Difficulty",
]

# Every BRFSS measure ships with its sample size + 95% confidence interval.
BRFSS_COLUMNS = [
    f"{stem}{suffix}"
    for stem in BRFSS_BASE_MEASURES
    for suffix in ("_Sample_Size", "", "_CI_Low", "_CI_High")
]

# Sector name -> expected columns in the master dataset.
SECTORS: dict[str, list[str]] = {
    "Geographic": [
        "ZCTA",
        "County_FIPS",
        "County_Name",
        "Land_Area_SqMi",
        "Water_Area_SqMi",
    ],
    "Demographics (ACS)": [
        "Total_Population",
        "Median_Age",
        "Pct_Age_65_Plus",
        "Seniors_65_Plus_Count",
    ],
    "Socioeconomic (ACS)": [
        "Median_Household_Income",
        "Pct_Below_Poverty",
        "Poverty_Population_Count",
        "Pct_Commute_Public_Transit",
        "Pct_NonEnglish_Language_Home",
    ],
    "Health Access (ACS)": [
        "Pct_No_Health_Insurance",
        "Uninsured_Population_Count",
        "Pct_Broadband_Internet",
        "No_Broadband_Households_Estimate",
    ],
    "BRFSS (State Level)": BRFSS_COLUMNS,
    "CHR - Health Outcomes": [
        "Pct_Poor_Fair_Health",
        "Pct_Poor_Fair_Health_LowCI",
        "Pct_Poor_Fair_Health_HighCI",
        "Pct_Poor_Fair_Health_Quartile",
        "Avg_Poor_Physical_Health_Days",
        "Avg_Poor_Physical_Health_Days_LowCI",
        "Avg_Poor_Physical_Health_Days_HighCI",
        "Avg_Poor_Physical_Health_Days_Quartile",
        "Avg_Poor_Mental_Health_Days",
        "Avg_Poor_Mental_Health_Days_LowCI",
        "Avg_Poor_Mental_Health_Days_HighCI",
        "Avg_Poor_Mental_Health_Days_Quartile",
        "CHR_YPLL_Rate",
        "CHR_Premature_Deaths_Count",
        "CHR_Pct_Low_Birthweight",
        "CHR_Pct_Low_Birthweight_Quartile",
        "CHR_STI_Chlamydia_Rate",
        "CHR_Teen_Birth_Rate",
    ],
    "CHR - Health Behaviors": [
        "Pct_Adult_Smoking",
        "Pct_Adult_Smoking_LowCI",
        "Pct_Adult_Smoking_HighCI",
        "Pct_Adult_Smoking_Quartile",
        "Pct_Adult_Obesity",
        "Pct_Adult_Obesity_LowCI",
        "Pct_Adult_Obesity_HighCI",
        "Pct_Adult_Obesity_Quartile",
        "Pct_Physical_Inactivity",
        "Pct_Physical_Inactivity_LowCI",
        "Pct_Physical_Inactivity_HighCI",
        "Pct_Physical_Inactivity_Quartile",
        "Excessive_Drinking_Pct",
        "Excessive_Drinking_Pct_LowCI",
        "Excessive_Drinking_Pct_HighCI",
        "Excessive_Drinking_Pct_Quartile",
        "CHR_Food_Environment_Index",
        "CHR_Access_Exercise_Opportunities_Pct",
        "CHR_Alcohol_Impaired_Driving_Deaths_Pct",
    ],
    "CHR - Clinical Care": [
        "CHR_Uninsured_Pct",
        "CHR_Uninsured_Pct_LowCI",
        "CHR_Uninsured_Pct_HighCI",
        "CHR_Uninsured_Pct_Quartile",
        "CHR_PCP_Ratio_Population",
        "Dentist_Ratio_Population",
        "Mental_Health_Provider_Ratio",
        "CHR_Preventable_Hospital_Stays_Rate",
        "CHR_Mammography_Screening_Pct",
        "CHR_Mammography_Screening_Pct_Quartile",
        "CHR_Flu_Vaccination_Pct",
        "CHR_Flu_Vaccination_Pct_Quartile",
    ],
    "Calculated Metrics": [
        "Population_Density_SqMi",
    ],
    # CDC PLACES, ZCTA release. Genuinely ZCTA-level model-based estimates,
    # merged onto the same ZCTA rows as the ACS demographics.
    "CDC PLACES (ZCTA-Level)": [
        "PLACES_Pct_Teeth_Lost_65Plus",
        "PLACES_Pct_Arthritis",
        "PLACES_Pct_Cancer_NonSkin",
        "PLACES_Pct_COPD",
        "PLACES_Pct_Coronary_Heart_Disease",
        "PLACES_Pct_Current_Asthma",
        "PLACES_Pct_Depression",
        "PLACES_Pct_Diabetes",
        "PLACES_Pct_High_Blood_Pressure",
        "PLACES_Pct_High_Cholesterol",
        "PLACES_Pct_Obesity",
        "PLACES_Pct_Stroke",
        "PLACES_Pct_Binge_Drinking",
        "PLACES_Pct_Current_Smoking",
        "PLACES_Pct_Physical_Inactivity",
        "PLACES_Pct_Short_Sleep",
        "PLACES_Pct_Fair_Poor_Health",
        "PLACES_Pct_Frequent_Mental_Distress",
        "PLACES_Pct_Frequent_Physical_Distress",
        "PLACES_Pct_Cholesterol_Screening",
        "PLACES_Pct_Colorectal_Screening",
        "PLACES_Pct_Uninsured_18_64",
        "PLACES_Pct_Mammography",
        "PLACES_Pct_BP_Medication",
        "PLACES_Pct_Dental_Visit",
        "PLACES_Pct_Routine_Checkup",
        "PLACES_Pct_Any_Disability",
        "PLACES_Pct_Cognitive_Disability",
        "PLACES_Pct_Hearing_Disability",
        "PLACES_Pct_Independent_Living_Disability",
        "PLACES_Pct_Mobility_Disability",
        "PLACES_Pct_Self_Care_Disability",
        "PLACES_Pct_Vision_Disability",
        "PLACES_Pct_Food_Insecurity",
        "PLACES_Pct_Housing_Insecurity",
        "PLACES_Pct_Transportation_Barrier",
        "PLACES_Pct_Lack_Social_Support",
        "PLACES_Pct_Loneliness",
        "PLACES_Pct_Food_Stamps",
        "PLACES_Pct_Utility_Shutoff_Threat",
    ],
    "CHR - County Level": [
        "Pct_Poor_Fair_Health",
        "Pct_Poor_Fair_Health_LowCI",
        "Pct_Poor_Fair_Health_HighCI",
        "Pct_Poor_Fair_Health_Quartile",
        "Avg_Poor_Physical_Health_Days",
        "Avg_Poor_Physical_Health_Days_LowCI",
        "Avg_Poor_Physical_Health_Days_HighCI",
        "Avg_Poor_Physical_Health_Days_Quartile",
        "Avg_Poor_Mental_Health_Days",
        "Avg_Poor_Mental_Health_Days_LowCI",
        "Avg_Poor_Mental_Health_Days_HighCI",
        "Avg_Poor_Mental_Health_Days_Quartile",
        "CHR_YPLL_Rate",
        "CHR_Premature_Deaths_Count",
        "CHR_Pct_Low_Birthweight",
        "CHR_Pct_Low_Birthweight_Quartile",
        "CHR_STI_Chlamydia_Rate",
        "CHR_Teen_Birth_Rate",
        "Pct_Adult_Smoking",
        "Pct_Adult_Smoking_LowCI",
        "Pct_Adult_Smoking_HighCI",
        "Pct_Adult_Smoking_Quartile",
        "Pct_Adult_Obesity",
        "Pct_Adult_Obesity_LowCI",
        "Pct_Adult_Obesity_HighCI",
        "Pct_Adult_Obesity_Quartile",
        "Pct_Physical_Inactivity",
        "Pct_Physical_Inactivity_LowCI",
        "Pct_Physical_Inactivity_HighCI",
        "Pct_Physical_Inactivity_Quartile",
        "Excessive_Drinking_Pct",
        "Excessive_Drinking_Pct_LowCI",
        "Excessive_Drinking_Pct_HighCI",
        "Excessive_Drinking_Pct_Quartile",
        "CHR_Food_Environment_Index",
        "CHR_Access_Exercise_Opportunities_Pct",
        "CHR_Alcohol_Impaired_Driving_Deaths_Pct",
        "CHR_Uninsured_Pct",
        "CHR_Uninsured_Pct_LowCI",
        "CHR_Uninsured_Pct_HighCI",
        "CHR_Uninsured_Pct_Quartile",
        "CHR_PCP_Ratio_Population",
        "Dentist_Ratio_Population",
        "Mental_Health_Provider_Ratio",
        "CHR_Preventable_Hospital_Stays_Rate",
        "CHR_Mammography_Screening_Pct",
        "CHR_Mammography_Screening_Pct_Quartile",
        "CHR_Flu_Vaccination_Pct",
        "CHR_Flu_Vaccination_Pct_Quartile",
    ],
}

# ---------------------------------------------------------------------------
# Provenance: which archived raw source each sector comes from, and the true
# geography of that source. See ./raw/SOURCES.md for the citations and
# ./fetch_raw_data.py for the download/verification code.
#
# This matters because only ACS and the TIGER boundaries are genuinely
# ZCTA-level. CDC BRFSS is a statewide survey and County Health Rankings
# reports by county, so those figures are broadcast onto every ZCTA row in the
# state / county respectively.
# ---------------------------------------------------------------------------
SECTOR_SOURCES: dict[str, tuple[str | None, str]] = {
    "Geographic": ("census_tiger_2020_de_zctas", "ZCTA"),
    "Demographics (ACS)": ("census_acs_2024_zcta_de", "ZCTA"),
    "Socioeconomic (ACS)": ("census_acs_2024_zcta_de", "ZCTA"),
    "Health Access (ACS)": ("census_acs_2024_zcta_de", "ZCTA"),
    "BRFSS (State Level)": ("cdc_brfss_2024_de", "State"),
    "CHR - Health Outcomes": ("chr_2025_de_counties", "County"),
    "CHR - Health Behaviors": ("chr_2025_de_counties", "County"),
    "CHR - Clinical Care": ("chr_2025_de_counties", "County"),
    "CHR - County Level": ("chr_2025_de_counties", "County"),
    "CDC PLACES (ZCTA-Level)": ("cdc_places_2024_de_zcta", "ZCTA"),
    "Provider Supply (HRSA AHRF)": ("hrsa_ahrf_2025_de_counties", "County"),
    "PLACES Chronic Disease (ZCTA)": ("cdc_places_2024_de_zcta", "ZCTA"),
    "Calculated Metrics": (None, "Derived from ZCTA-level ACS"),
}

# Raw TIGER boundary attribute columns that reach the master unrenamed; they are
# genuinely ZCTA-level even though they sit outside the "Geographic" sector.
TIGER_ZCTA_COLUMNS = [
    "ZCTA5CE20",
    "AFFGEOID20",
    "GEOID20",
    "NAME20",
    "ALAND20",
    "AWATER20",
    "LSAD20",
    "MTFCC20",
]

# Year/audit stamps and API-native identifiers carry no geography of their own.
NON_GEOGRAPHIC_COLUMNS = {
    "zip code tabulation area": "ZCTA",  # ACS API's own ZCTA identifier
    "CHR_Data_Year": "Not geographic",   # release-year stamp for CHR columns
    "BRFSS_Year": "Not geographic",      # survey-year stamp for BRFSS columns
}

# Columns that are computed in extract_census.py rather than taken from a source.
CALCULATED_COLUMNS = [
    "Population_Density_SqMi",
    "Uninsured_Population_Count",
    "Poverty_Population_Count",
    "Seniors_65_Plus_Count",
    "No_Broadband_Households_Estimate",
]


def _build_provenance_maps() -> tuple[dict, dict, dict]:
    """Derive column -> source id / geography / sector from SECTORS once."""
    by_source, by_level, by_sector = {}, {}, {}
    for sector, columns in SECTORS.items():
        source_id, geo_level = SECTOR_SOURCES.get(sector, (None, "Unknown"))
        for column in columns:
            by_source[column] = source_id
            by_sector[column] = sector
            # The derived counts live inside ACS sectors next to their inputs -
            # they are still computed in extract_census.py, not measured.
            if column in CALCULATED_COLUMNS:
                by_source[column] = None
                by_level[column] = "Derived from ZCTA-level ACS"
                continue
            by_level[column] = geo_level
    for column in CALCULATED_COLUMNS:
        by_source.setdefault(column, None)
        by_level[column] = "Derived from ZCTA-level ACS"
    for column in TIGER_ZCTA_COLUMNS:
        by_source.setdefault(column, "census_tiger_2020_de_zctas")
        by_level[column] = "ZCTA"
        by_sector.setdefault(column, "Geographic")
    for column, level in NON_GEOGRAPHIC_COLUMNS.items():
        by_level[column] = level

    # Confidence-interval columns carry no sector of their own - they are the
    # uncertainty band around a measure, so they inherit the base measure's
    # source, geography and sector (e.g. PLACES_Pct_Diabetes_CI_Low follows
    # PLACES_Pct_Diabetes). The base measure is NOT listed in any sector, so the
    # CI columns have to be registered here rather than found by scanning
    # by_source, which only holds columns the sectors already declared.
    # Registers PLACES_Pct_<measure>_CI_Low / _CI_High in the PLACES sector at
    # ZCTA geography. The base measure is always listed in the sector, but its
    # interval columns are not, and by_source only holds sector-declared columns
    # - so the intervals are derived here from the base-measure names.
    places_sector = "CDC PLACES (ZCTA-Level)"
    places_source_id = SECTOR_SOURCES[places_sector][0]
    for base in [c for c in SECTORS[places_sector] if c.startswith("PLACES_Pct_")]:
        for suffix in ("_CI_Low", "_CI_High"):
            column = f"{base}{suffix}"
            by_source[column] = places_source_id
            by_level[column] = "ZCTA"
            by_sector[column] = places_sector
    return by_source, by_level, by_sector


COLUMN_SOURCES, COLUMN_GEO_LEVEL, COLUMN_SECTORS = _build_provenance_maps()


def source_id_of(column: str) -> str | None:
    """Manifest id of the raw source a column comes from (None if derived)."""
    return COLUMN_SOURCES.get(column)


def geo_level_of(column: str) -> str:
    """True geography of a measure: ZCTA, State, County, City / place or derived."""
    return COLUMN_GEO_LEVEL.get(column, "Unknown")


def provenance_rows(columns: list[str]) -> list[dict]:
    """Per-column provenance table (used for the data-dictionary exports)."""
    rows = []
    for column in columns:
        source_id = COLUMN_SOURCES.get(column)
        rows.append(
            {
                "Column": column,
                "Sector": COLUMN_SECTORS.get(column, "Other"),
                "Source_ID": source_id or "calculated",
                "Geography_Level": geo_level_of(column),
                "Calculated": "yes" if column in CALCULATED_COLUMNS else "no",
            }
        )
    return rows


KEY_COLUMNS = ["ZCTA", "County_FIPS", "County_Name"]

# City-level data uses City_Name as the key instead of ZCTA
CITY_KEY_COLUMNS = ["City_Name", "State"]

# County-level data uses County_Name as the key
COUNTY_KEY_COLUMNS = ["County_Name", "County_FIPS"]


def sector_of(column: str) -> str | None:
    """Return the sector a column belongs to, or None if it is ungrouped."""
    for sector, columns in SECTORS.items():
        if column in columns:
            return sector
    return None


def all_sector_columns() -> list[str]:
    """Every column that appears in any sector definition (deduped)."""
    return [col for columns in SECTORS.values() for col in columns]
