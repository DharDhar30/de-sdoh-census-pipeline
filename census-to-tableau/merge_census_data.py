"""
merge_census_data.py

Merges ACS Data Profile CSV exports (downloaded from data.census.gov) into a
single, clean, Tableau-ready CSV keyed by an 11-digit Census Tract GEOID.

WHY THIS EXISTS
----------------
data.census.gov lets you download individual tables (DP02, DP03, DP05, etc.)
as CSV, but each download:
  1. Has a GEO_ID like "1400000US10001040100" instead of the plain 11-digit
     FIPS code Tableau's "Census Tract" geographic role expects.
  2. Has a duplicate second header row with raw variable codes.
  3. Uses text placeholders ("-", "**", "(X)", "N") for suppressed/NA cells
     instead of blanks, which breaks numeric typing.
  4. Only has your file's own topic — you have to join across files by hand.

This script does all four steps for you.

HOW TO GET NEW INPUT FILES
----------------------------
1. Go to https://data.census.gov
2. Search a table code, e.g. "DP03" (Economic), "DP02" (Social),
   "DP05" (Demographic), or any other ACS Data Profile / Subject / Detail table.
3. Click "Geography" (left sidebar) -> choose your geography level
   (Census Tract / County / Block Group) -> choose your state -> "All [geography]
   within [state]" -> Apply.
4. Click "Download" (top right) -> CSV -> Download. You'll get a .zip.
5. Unzip it. You'll see three files; you only need the one ending in "-Data.csv".

USAGE
-----
    python merge_census_data.py \
        --inputs DP03=path/to/ACSDP5Y2024.DP03-Data.csv \
                 DP02=path/to/ACSDP5Y2024.DP02-Data.csv \
                 DP05=path/to/ACSDP5Y2024.DP05-Data.csv \
        --output Delaware_Tract_Health_Data.csv

Edit the VARIABLES dict below to change which columns get pulled out of each
table and what they get renamed to. Use the *-Column-Metadata.csv file that
comes in each zip to find new variable codes (search it for keywords like
"poverty", "insurance", "internet", "language").
"""

import argparse
import pandas as pd

VARIABLES = {
    "DP05": {
        "DP05_0001E": "Total_Population",
        "DP05_0018E": "Median_Age",
        "DP05_0024PE": "Pct_Age_65_Plus",
    },
    "DP03": {
        "DP03_0062E": "Median_Household_Income",
        "DP03_0128PE": "Pct_Below_Poverty",
        "DP03_0099PE": "Pct_No_Health_Insurance",
        "DP03_0021PE": "Pct_Commute_Public_Transit",
    },
    "DP02": {
        "DP02_0154PE": "Pct_Broadband_Internet",
        "DP02_0114PE": "Pct_NonEnglish_Language_Home",
    },
}

# Table used as the "base" for geography columns (GEOID / tract / county / state).
# Must be one of the keys in VARIABLES / --inputs.
BASE_TABLE = "DP03"

# Values the Census Bureau uses in place of real numbers for suppressed cells.
NULL_CODES = ["-", "**", "***", "(X)", "N", "null"]


def geoid_from_geo_id(geo_id: str) -> str:
    """'1400000US10001040100' -> '10001040100' (state+county+tract FIPS)."""
    return str(geo_id).split("US")[-1]


def load_table(path: str) -> pd.DataFrame:
    """Load a Data Profile CSV, skipping the duplicate description header row."""
    return pd.read_csv(path, skiprows=[1], low_memory=False)


def build_merged_dataframe(inputs: dict) -> pd.DataFrame:
    tables = {table_id: load_table(path) for table_id, path in inputs.items()}
    base = tables[BASE_TABLE]

    out = pd.DataFrame()
    out["GEOID"] = base["GEO_ID"].apply(geoid_from_geo_id)
    name_parts = base["NAME"].str.split(";", expand=True)
    out["Geography_Name"] = name_parts[0].str.strip()
    if name_parts.shape[1] > 1:
        out["County"] = name_parts[1].str.strip()
    if name_parts.shape[1] > 2:
        out["State"] = name_parts[2].str.strip()

    for table_id, colmap in VARIABLES.items():
        if table_id not in tables:
            print(f"Skipping {table_id}: no input file provided for it.")
            continue
        table = tables[table_id]
        cols_present = [c for c in colmap if c in table.columns]
        missing = set(colmap) - set(cols_present)
        if missing:
            print(f"Warning: {table_id} is missing expected columns: {missing}")

        sub = table[["GEO_ID"] + cols_present].rename(columns=colmap)
        out = out.merge(
            sub, left_on=base["GEO_ID"], right_on="GEO_ID", how="left"
        ).drop(columns="GEO_ID")

    non_numeric = {"GEOID", "Geography_Name", "County", "State"}
    for col in out.columns:
        if col not in non_numeric:
            out[col] = out[col].replace(NULL_CODES, pd.NA)
            out[col] = pd.to_numeric(out[col], errors="coerce")

    sort_cols = [c for c in ["County", "Geography_Name"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols).reset_index(drop=True)

    return out


def parse_inputs(pairs):
    """Turn ['DP03=path.csv', 'DP02=path.csv'] into {'DP03': 'path.csv', ...}."""
    inputs = {}
    for pair in pairs:
        table_id, path = pair.split("=", 1)
        inputs[table_id.strip().upper()] = path.strip()
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="TABLE_ID=path.csv pairs, e.g. DP03=dp03.csv DP02=dp02.csv DP05=dp05.csv",
    )
    parser.add_argument(
        "--output",
        default="census_tract_data_tableau.csv",
        help="Output CSV path (default: census_tract_data_tableau.csv)",
    )
    args = parser.parse_args()

    inputs = parse_inputs(args.inputs)
    if BASE_TABLE not in inputs:
        raise SystemExit(
            f"BASE_TABLE is set to '{BASE_TABLE}' but no --inputs entry for it was given."
        )

    df = build_merged_dataframe(inputs)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} rows x {len(df.columns)} columns to {args.output}")


if __name__ == "__main__":
    main()
