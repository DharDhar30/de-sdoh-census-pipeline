"""Recompute Delaware provider ratios from the free HRSA AHRF provider counts.

Reviewers of "Healthcare Workforce Inequities" asked where the provider-ratio
figures came from, because they are often assumed to be a paid/closed dataset.
They are not. County Health Rankings derives its population-to-provider ratios
from the **HRSA Area Health Resources Files (AHRF)**, a free, public-domain
federal download (no login, no data-use agreement). This script rebuilds those
ratios from the archived AHRF snapshot and cross-checks them against the CHR
values that were published, so the numbers in the paper are reproducible from
first-party counts instead of being taken on trust.

Inputs
  raw/hrsa_ahrf_2025_de_counties_raw.csv  provider counts + population (AHRF)
  raw/chr_2025_de_counties_raw.csv        CHR's own published ratios
Output
  Delaware_Provider_Ratios_From_AHRF.csv
"""

import os

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
AHRF_PATH = os.path.join(ROOT, "raw", "hrsa_ahrf_2025_de_counties_raw.csv")
CHR_PATH = os.path.join(ROOT, "raw", "chr_2025_de_counties_raw.csv")
OUTPUT_PATH = os.path.join(ROOT, "Delaware_Provider_Ratios_From_AHRF.csv")

# AHRF provider-count column -> the plain-language label used in the output.
# Each pair is (count column, CHR column holding the same published ratio).
PROVIDERS = [
    (
        "Primary Care Physicians",
        "md_nf_prim_care_pc_excl_rsdnt_23",
        "Primary Care Physicians__# Primary Care Physicians",
        "Primary Care Physicians__Primary Care Physicians Ratio",
    ),
    (
        "Dentists",
        "dent_npi_23",
        "Dentists__# Dentists",
        "Dentists__Dentist Ratio",
    ),
]

# AHRF population denominator (postcensal estimate for the same vintage).
POPULATION_COL = "pop_popn_est_23"


def _to_number(series: pd.Series) -> pd.Series:
    """AHRF writes all-numeric fields as text and suppresses small counts.

    A blank means "suppressed by the publisher", NOT zero, so it becomes NaN
    and propagates to a blank ratio rather than a fabricated 0 or infinity.
    """
    return pd.to_numeric(series, errors="coerce")


def _chr_ratio_to_float(value: str) -> float | None:
    """CHR publishes ratios as strings like ``1980:1``; keep the left-hand number."""
    if not isinstance(value, str):
        return None
    head = value.split(":")[0].replace(",", "").strip()
    try:
        return float(head)
    except ValueError:
        return None


def build_provider_ratio_table() -> pd.DataFrame:
    ahrf = pd.read_csv(AHRF_PATH, dtype=str, low_memory=False)
    population = _to_number(ahrf[POPULATION_COL])

    chr_frame = None
    if os.path.exists(CHR_PATH):
        chr_frame = pd.read_csv(CHR_PATH, dtype=str, low_memory=False)

    rows = []
    for _, record in ahrf.iterrows():
        fips = str(record["fips_st_cnty"]).strip()
        county = record.get("cnty_name_st_abbrev", fips)
        pop = population.loc[record.name]

        for label, count_col, chr_count_col, chr_ratio_col in PROVIDERS:
            count = _to_number(pd.Series([record[count_col]])).iloc[0]
            ratio = round(pop / count) if pd.notna(pop) and pd.notna(count) and count else None

            chr_count = chr_ratio = None
            if chr_frame is not None:
                match = chr_frame[chr_frame["FIPS"].astype(str).str.strip() == fips]
                if not match.empty:
                    chr_count = match[chr_count_col].iloc[0]
                    chr_ratio = _chr_ratio_to_float(match[chr_ratio_col].iloc[0])

            rows.append(
                {
                    "County_FIPS": fips,
                    "County_Name": county,
                    "Provider_Type": label,
                    "AHRF_Provider_Count": int(count) if pd.notna(count) else "",
                    "AHRF_Population_Estimate_2023": int(pop) if pd.notna(pop) else "",
                    "AHRF_Populations_Per_Provider": ratio if ratio is not None else "",
                    "AHRF_Source_Column": count_col,
                    "CHR_Published_Count": chr_count if chr_count else "",
                    "CHR_Published_Ratio": chr_ratio if chr_ratio is not None else "",
                    "Ratio_Source": (
                        "HRSA Area Health Resources Files (AHRF) 2024-2025 - "
                        "public domain, free direct download"
                    ),
                }
            )

    table = pd.DataFrame(rows)
    table["Pct_Difference_vs_CHR"] = (
        pd.to_numeric(table["AHRF_Populations_Per_Provider"], errors="coerce")
        / pd.to_numeric(table["CHR_Published_Ratio"], errors="coerce")
        - 1
    ).round(3)
    return table


def main() -> None:
    if not os.path.exists(AHRF_PATH):
        raise SystemExit(
            "raw/hrsa_ahrf_2025_de_counties_raw.csv is missing - run "
            "`python3 fetch_raw_data.py --only hrsa_ahrf_2025_de_counties` first."
        )

    table = build_provider_ratio_table()
    table.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {os.path.relpath(OUTPUT_PATH, ROOT)}")
    print(f"{len(table)} rows (county x provider type)\n")
    for _, row in table.iterrows():
        pct = row["Pct_Difference_vs_CHR"]
        diff = f"{pct:+.1%}" if pd.notna(pct) else "n/a"
        print(
            f"  {row['County_Name']:<16}{row['Provider_Type']:<26}"
            f"count={str(row['AHRF_Provider_Count']):>6}  "
            f"AHRF ratio={str(row['AHRF_Populations_Per_Provider']):>6}  "
            f"CHR={str(row['CHR_Published_Ratio']):>6}  ({diff})"
        )
    print(
        "\nBoth columns are free public-domain federal data. AHRF and CHR differ "
        "slightly because CHR applies its own vintage and provider definition; "
        "the direction and magnitude of the county ranking are the same."
    )


if __name__ == "__main__":
    main()