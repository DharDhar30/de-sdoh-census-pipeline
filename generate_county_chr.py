"""Generate county-level CHR data by aggregating ZCTA-level data."""

import pandas as pd
import numpy as np
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Wide.xlsx")
OUTPUT_PATH = os.path.join(ROOT, "Delaware_County_CHR.csv")


def load_master_data() -> pd.DataFrame:
    """Load the master ZCTA dataset."""
    df = pd.read_excel(MASTER_PATH)
    print(f"Loaded master data: {df.shape[0]} ZCTAs, {df.shape[1]} columns")
    return df


def get_chr_columns() -> dict[str, list[str]]:
    """Get CHR-related columns grouped by category."""
    return {
        "Health Outcomes": [
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
        "Health Behaviors": [
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
        "Clinical Care": [
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


def aggregate_to_county(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ZCTA-level data to county level."""
    # Filter out ZCTAs with no county assignment
    df = df.dropna(subset=["County_Name"]).copy()
    print(f"ZCTAs with county assignment: {df.shape[0]}")
    
    # Define column types for aggregation
    count_cols = ["CHR_Premature_Deaths_Count"]
    ratio_cols = ["CHR_PCP_Ratio_Population", "Dentist_Ratio_Population", "Mental_Health_Provider_Ratio"]
    
    # Get all CHR columns
    chr_columns = []
    for cols in get_chr_columns().values():
        chr_columns.extend(cols)
    chr_columns = [c for c in chr_columns if c in df.columns]
    
    # Group by county
    counties = []
    for county_name, group in df.groupby("County_Name"):
        county_data = {
            "County_Name": county_name,
            "County_FIPS": group["County_FIPS"].iloc[0],
            "Total_Population": group["Total_Population"].sum(),
            "ZCTA_Count": len(group),
        }
        
        for col in chr_columns:
            if col not in group.columns:
                continue
            values = group[col].dropna()
            if len(values) == 0:
                county_data[col] = np.nan
            elif col in count_cols:
                county_data[col] = group[col].sum()
            elif col in ratio_cols:
                county_data[col] = group[col].mean()
            elif "Quartile" in col:
                county_data[col] = group[col].mode().iloc[0] if len(group[col].mode()) > 0 else np.nan
            elif "CI" in col:
                county_data[col] = group[col].mean()
            else:
                # Population-weighted average for percentages
                pop = group["Total_Population"]
                vals = group[col]
                mask = vals.notna() & pop.notna()
                if mask.sum() > 0:
                    county_data[col] = (vals[mask] * pop[mask]).sum() / pop[mask].sum()
                else:
                    county_data[col] = np.nan
        counties.append(county_data)
    
    return pd.DataFrame(counties)


def filter_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Remove rows where all CHR data columns are NaN."""
    key_cols = ["County_Name", "County_FIPS", "Total_Population", "ZCTA_Count"]
    data_cols = [c for c in df.columns if c not in key_cols]
    non_nan_counts = df[data_cols].notna().sum(axis=1)
    print(f"\nRows before filtering: {len(df)}")
    for idx, row in df.iterrows():
        print(f"  {row['County_Name']}: {non_nan_counts[idx]} of {len(data_cols)} data columns")
    mask = non_nan_counts > 0
    result = df[mask].copy()
    print(f"Rows after filtering: {len(result)}")
    return result


def main():
    """Generate county-level CHR dataset."""
    print("Generating County-Level CHR Data")
    print("=" * 50)
    df = load_master_data()
    county_df = aggregate_to_county(df)
    county_df = filter_empty_rows(county_df)
    county_df = county_df.sort_values("County_Name").reset_index(drop=True)
    county_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved county-level CHR data to: {OUTPUT_PATH}")
    print(f"Shape: {county_df.shape}")
    print(f"\nCounties: {list(county_df['County_Name'])}")
    print(f"\nColumns ({len(county_df.columns)}):")
    for col in county_df.columns:
        print(f"  - {col}")
    return county_df


if __name__ == "__main__":
    main()
