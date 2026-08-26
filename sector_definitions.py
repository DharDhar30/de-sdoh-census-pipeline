"""Sector definitions for the Delaware ZCTA Health Master dataset.

Every column in the master dataset belongs to one themed sector so the UI can
offer "pick a sector -> export" workflows that mirror the README schema:

    Geographic / Demographics / Socioeconomic / Health Access /
    County Health Rankings (Physical, Dental, Behavioral) / Calculated Metrics

Columns not listed here are treated as "Other" and can still be picked
manually in the UI.
"""

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
    ],
    "CHR - Physical Health": [
        "Pct_Poor_Fair_Health",
        "Pct_Adult_Obesity",
        "Pct_Physical_Inactivity",
    ],
    "CHR - Dental Care": [
        "Dentist_Ratio_Population",
        "Pct_Dental_Visit_Past_Year",
    ],
    "CHR - Behavioral Health": [
        "Mental_Health_Provider_Ratio",
        "Avg_Poor_Mental_Health_Days",
        "Pct_Frequent_Mental_Distress",
        "Excessive_Drinking_Pct",
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
