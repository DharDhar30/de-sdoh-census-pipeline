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
}

# Key columns always kept in every export so rows stay joinable.
KEY_COLUMNS = ["ZCTA", "County_FIPS", "County_Name"]


def sector_of(column: str) -> str | None:
    """Return the sector a column belongs to, or None if it is ungrouped."""
    for sector, columns in SECTORS.items():
        if column in columns:
            return sector
    return None


def all_sector_columns() -> list[str]:
    """Every column that appears in any sector definition (deduped)."""
    return [col for columns in SECTORS.values() for col in columns]
