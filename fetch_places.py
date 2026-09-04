"""CDC PLACES City-Level Health Data Fetcher

Fetches city/place-level health estimates from CDC PLACES (Local Data for Better Health).
PLACES provides model-based estimates for chronic disease risk factors, health outcomes,
and prevention services at the city/place level for the entire United States.
"""

import os
import requests
import pandas as pd

# CDC PLACES API endpoint for city/place data
PLACES_API_BASE = "https://data.cdc.gov/api/v3/views/eav7-hnsx/query.json"

# Delaware state name for filtering
DELAWARE_STATE = "Delaware"

# Output column mapping: measure -> clean column name
MEASURE_COLUMNS = {
    # Health Outcomes
    "All teeth lost among adults aged >=65 years": "PLACES_Pct_Teeth_Lost_65Plus",
    "Arthritis among adults": "PLACES_Pct_Arthritis",
    "Cancer (non-skin) or melanoma among adults": "PLACES_Pct_Cancer_NonSkin",
    "Chronic obstructive pulmonary disease among adults": "PLACES_Pct_COPD",
    "Coronary heart disease among adults": "PLACES_Pct_Coronary_Heart_Disease",
    "Current asthma among adults": "PLACES_Pct_Current_Asthma",
    "Depression among adults": "PLACES_Pct_Depression",
    "Diagnosed diabetes among adults": "PLACES_Pct_Diabetes",
    "High blood pressure among adults": "PLACES_Pct_High_Blood_Pressure",
    "High cholesterol among adults who have ever been screened": "PLACES_Pct_High_Cholesterol",
    "Obesity among adults": "PLACES_Pct_Obesity",
    "Stroke among adults": "PLACES_Pct_Stroke",
    # Health Risk Behaviors
    "Binge drinking among adults": "PLACES_Pct_Binge_Drinking",
    "Current cigarette smoking among adults": "PLACES_Pct_Current_Smoking",
    "No leisure-time physical activity among adults": "PLACES_Pct_Physical_Inactivity",
    "Short sleep duration among adults": "PLACES_Pct_Short_Sleep",
    # Health Status
    "Fair or poor self-rated health status among adults": "PLACES_Pct_Fair_Poor_Health",
    "Frequent mental distress among adults": "PLACES_Pct_Frequent_Mental_Distress",
    "Frequent physical distress among adults": "PLACES_Pct_Frequent_Physical_Distress",
    # Prevention
    "Cholesterol screening among adults": "PLACES_Pct_Cholesterol_Screening",
    "Colorectal cancer screening among adults aged 45\u201375 years": "PLACES_Pct_Colorectal_Screening",
    "Current lack of health insurance among adults aged 18-64 years": "PLACES_Pct_Uninsured_18_64",
    "Mammography use among women aged 50-74 years": "PLACES_Pct_Mammography",
    "Taking medicine to control high blood pressure among adults with high blood pressure": "PLACES_Pct_BP_Medication",
    "Visited dentist or dental clinic in the past year among adults": "PLACES_Pct_Dental_Visit",
    "Visits to doctor for routine checkup within the past year among adults": "PLACES_Pct_Routine_Checkup",
    # Disability
    "Any disability among adults": "PLACES_Pct_Any_Disability",
    "Cognitive disability among adults": "PLACES_Pct_Cognitive_Disability",
    "Hearing disability among adults": "PLACES_Pct_Hearing_Disability",
    "Independent living disability among adults": "PLACES_Pct_Independent_Living_Disability",
    "Mobility disability among adults": "PLACES_Pct_Mobility_Disability",
    "Self-care disability among adults": "PLACES_Pct_Self_Care_Disability",
    "Vision disability among adults": "PLACES_Pct_Vision_Disability",
    # Health-Related Social Needs
    "Food insecurity in the past 12 months among adults": "PLACES_Pct_Food_Insecurity",
    "Housing insecurity in the past 12 months among adults": "PLACES_Pct_Housing_Insecurity",
    "Lack of reliable transportation in the past 12 months among adults": "PLACES_Pct_Transportation_Barrier",
    "Lack of social and emotional support among adults": "PLACES_Pct_Lack_Social_Support",
    "Loneliness among adults": "PLACES_Pct_Loneliness",
    "Received food stamps in the past 12 months among adults": "PLACES_Pct_Food_Stamps",
    "Utility services shut-off threat in the past 12 months among adults": "PLACES_Pct_Utility_Shutoff_Threat",
}


def fetch_places_delaware(limit: int = 50000) -> list[dict]:
    """Fetch CDC PLACES city-level health data for Delaware.
    
    Args:
        limit: Maximum number of rows to fetch
        
    Returns:
        List of dictionaries with PLACES health data
    """
    print("Fetching CDC PLACES city-level health data for Delaware...")
    
    params = {
        "$where": f"statedesc='{DELAWARE_STATE}'",
        "$limit": limit,
    }
    
    response = requests.get(PLACES_API_BASE, params=params, timeout=180)
    response.raise_for_status()
    
    data = response.json()
    print(f"  Fetched {len(data)} PLACES records")
    return data


def process_places_data(raw_data: list[dict]) -> pd.DataFrame:
    """Process raw PLACES data into a clean city-level DataFrame.
    
    Pivots measure names into separate columns with clean names.
    Converts data values to numeric percentages.
    
    Args:
        raw_data: Raw list of dictionaries from CDC PLACES API
        
    Returns:
        Clean DataFrame with one row per city and columns for each measure
    """
    df = pd.DataFrame(raw_data)
    
    # Filter to measures we want
    df = df[df["measure"].isin(MEASURE_COLUMNS.keys())].copy()
    
    # Convert data_value to numeric (percentages)
    df["data_value"] = pd.to_numeric(df["data_value"], errors="coerce")
    df["low_confidence_limit"] = pd.to_numeric(df["low_confidence_limit"], errors="coerce")
    df["high_confidence_limit"] = pd.to_numeric(df["high_confidence_limit"], errors="coerce")
    
    # Pivot: one row per city, columns for each measure
    pivot = df.pivot_table(
        index="locationname",
        columns="measure",
        values="data_value",
        aggfunc="first"
    ).reset_index()
    
    # Rename columns to clean names
    pivot = pivot.rename(columns=MEASURE_COLUMNS)
    
    # Add confidence intervals
    for measure, col_name in MEASURE_COLUMNS.items():
        if measure in df["measure"].values:
            low = df[df["measure"] == measure].set_index("locationname")["low_confidence_limit"]
            high = df[df["measure"] == measure].set_index("locationname")["high_confidence_limit"]
            pivot[f"{col_name}_CI_Low"] = pivot["locationname"].map(low).values
            pivot[f"{col_name}_CI_High"] = pivot["locationname"].map(high).values
    
    # Rename location column
    pivot = pivot.rename(columns={"locationname": "City_Name"})
    
    # Add state info
    pivot["State"] = "Delaware"
    
    # Reorder columns
    first_cols = ["City_Name", "State"]
    measure_cols = [col for col in MEASURE_COLUMNS.values() if col in pivot.columns]
    ci_cols = [c for c in pivot.columns if c.endswith(("_CI_Low", "_CI_High"))]
    pivot = pivot[first_cols + sorted(measure_cols) + sorted(ci_cols)]
    
    print(f"  Processed {len(pivot)} cities with {len(measure_cols)} health measures")
    return pivot


def get_places_delaware() -> pd.DataFrame:
    """Main function to fetch and process CDC PLACES city-level data for Delaware.
    
    Returns:
        DataFrame with city-level health estimates for Delaware
    """
    raw_data = fetch_places_delaware()
    return process_places_data(raw_data)


if __name__ == "__main__":
    df = get_places_delaware()
    print(f"\nCDC PLACES City-Level Data for Delaware:")
    print(f"  Cities: {len(df)}")
    print(f"  Columns: {len(df.columns)}")
    print(f"\nColumn names:")
    for col in df.columns:
        print(f"  - {col}")
    print(f"\nSample data:")
    print(df.head())
    
    # Save to CSV
    output_path = "PLACES_Delaware_City.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved to {output_path}")
