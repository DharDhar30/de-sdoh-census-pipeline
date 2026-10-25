"""CDC PLACES ZCTA-Level Health Data Fetcher for Trend Analysis.

Fetches CDC PLACES ZCTA-level health estimates across multiple releases to
build yearly trend series (2021-2023) for Delaware ZCTAs.

Uses the CDC PLACES Socrata API:
  - 2024 release (4r2x-hcfq): model years 2021-2022
  - 2025 release (qnzd-25i4): model years 2022-2023

Combined, this gives 3 years (2021-2023) of ZCTA-level data.
"""

from __future__ import annotations

import requests
import pandas as pd
from typing import Optional

# PLACES ZCTA Socrata dataset endpoints by release year
PLACES_ZCTA_ENDPOINTS = {
    2024: "https://data.cdc.gov/resource/4r2x-hcfq.json",
    2025: "https://data.cdc.gov/resource/qnzd-25i4.json",
}

# Delaware ZCTA prefixes
DE_ZCTA_PREFIXES = ("197", "198", "199")

# Measures to include in trend analysis
TREND_MEASURES = [
    "Diagnosed diabetes among adults",
    "Obesity among adults",
    "Coronary heart disease among adults",
    "Chronic obstructive pulmonary disease among adults",
    "Stroke among adults",
    "High blood pressure among adults",
    "Current asthma among adults",
    "Depression among adults",
    "Current cigarette smoking among adults",
    "No leisure-time physical activity among adults",
    "Binge drinking among adults",
    "Short sleep duration among adults",
    "Fair or poor self-rated health status among adults",
    "Frequent mental distress among adults",
    "Current lack of health insurance among adults aged 18-64 years",
    "Visits to doctor for routine checkup within the past year among adults",
    "Visited dentist or dental clinic in the past year among adults",
    "Cholesterol screening among adults",
    "Food insecurity in the past 12 months among adults",
    "Housing insecurity in the past 12 months among adults",
]


def fetch_places_zcta_release(
    endpoint: str, limit: int = 50000
) -> list[dict]:
    """Fetch PLACES ZCTA data from a single Socrata endpoint."""
    de_conditions = " OR ".join(
        f"locationname like '{p}%'" for p in DE_ZCTA_PREFIXES
    )
    where_clauses = [f"({de_conditions})", "datavaluetypeid = 'CrdPrv'"]
    measure_conditions = " OR ".join(
        f"measure = '{m}'" for m in TREND_MEASURES
    )
    where_clauses.append(f"({measure_conditions})")
    where = " AND ".join(where_clauses)

    params = {
        "$where": where,
        "$limit": limit,
        "$order": "locationname, year, measure",
    }

    resp = requests.get(endpoint, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_all_places_zcta_trends() -> pd.DataFrame:
    """Fetch PLACES ZCTA data across all releases for trend analysis."""
    all_records = []

    for release_year, endpoint in PLACES_ZCTA_ENDPOINTS.items():
        print(f"Fetching PLACES ZCTA {release_year} release from {endpoint}...")
        try:
            records = fetch_places_zcta_release(endpoint)
            print(f"  Fetched {len(records)} records")
            all_records.extend(records)
        except Exception as exc:
            print(f"  WARNING: Failed to fetch {release_year} release: {exc}")

    if not all_records:
        raise RuntimeError("No PLACES ZCTA data fetched from any endpoint")

    df = pd.DataFrame(all_records)

    # Normalize column names
    df = df.rename(
        columns={
            "locationname": "ZCTA",
            "year": "Year",
            "measure": "Measure",
            "data_value": "DataValue",
            "low_confidence_limit": "CI_Low",
            "high_confidence_limit": "CI_High",
            "totalpop18plus": "TotalPop18Plus",
            "totalpopulation": "TotalPopulation",
            "category": "Category",
            "data_value_type": "DataValueType",
        }
    )

    # Keep only columns we need
    keep_cols = [
        "ZCTA", "Year", "Measure", "DataValue", "CI_Low", "CI_High",
        "TotalPop18Plus", "TotalPopulation", "Category", "DataValueType",
    ]
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols].copy()

    # Ensure ZCTA is 5-char string
    df["ZCTA"] = df["ZCTA"].astype(str).str.zfill(5)

    # Convert Year to int
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")

    # Convert numeric columns
    for col in ["DataValue", "CI_Low", "CI_High", "TotalPop18Plus", "TotalPopulation"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows with missing values
    df = df.dropna(subset=["ZCTA", "Year", "Measure", "DataValue"])

    # Deduplicate: if same ZCTA x Year x Measure appears in both releases,
    # keep the later release (2025 over 2024)
    df = df.sort_values(["ZCTA", "Year", "Measure"])
    df = df.drop_duplicates(
        subset=["ZCTA", "Year", "Measure"], keep="last"
    )

    # Sort for readability
    df = df.sort_values(["Measure", "ZCTA", "Year"]).reset_index(drop=True)

    print(f"\nTotal records: {len(df)}")
    print(f"Years: {sorted(df['Year'].dropna().unique())}")
    print(f"ZCTAs: {df['ZCTA'].nunique()}")
    print(f"Measures: {df['Measure'].nunique()}")

    return df


if __name__ == "__main__":
    df = fetch_all_places_zcta_trends()
    print("\nSample data:")
    print(df.head(10).to_string())
    output_path = "DE_PLACES_ZCTA_Trends_Raw.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved to {output_path}")