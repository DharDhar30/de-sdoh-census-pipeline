"""Rebuild the Delaware county CHR table as a faithful copy of the raw release.

CHR is already published at county level, so this table uses
CHR_Delaware.csv / raw/chr_2025_de_counties_raw.csv directly - nothing is
re-aggregated from ZCTAs (Issue 4: copying a county value onto every ZCTA
and summing it back inflated Kent premature deaths 19x). County population
comes from the ACS county tables (DP05_0001E), never by summing ZCTAs.

Inputs
  raw/chr_2025_de_counties_raw.csv        CHR 2025 release, unmodified
Output
  Delaware_County_CHR.csv

Run:
    python3 generate_county_chr.py
"""

import os

import pandas as pd
import requests
from dotenv import load_dotenv

# The CHR column mappings (output name -> source column in the raw snapshot)
# are imported from gen_health_data.py so there is a single source of truth
# for them. gen_health_data.py only runs its downloads under __main__, so this
# import is side-effect free.
from gen_health_data import CHR_TARGETS, _parse_chr_value

ROOT = os.path.dirname(os.path.abspath(__file__))
CHR_PATH = os.path.join(ROOT, "raw", "chr_2025_de_counties_raw.csv")
OUTPUT_PATH = os.path.join(ROOT, "Delaware_County_CHR.csv")

load_dotenv(os.path.join(ROOT, ".env"))
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")

DE_COUNTY_FIPS = ["10001", "10003", "10005"]

# County population comes from the ACS county tables (Issue 4) - never by
# summing ZCTAs, and no longer from AHRF postcensal estimates.
POPULATION_SOURCE = "Census ACS 2024 5-Year (DP05_0001E, county)"


def _fips(series: pd.Series) -> pd.Series:
    """Normalise FIPS to a 5-digit string ('10001', not '10001.0')."""
    return (
        series.astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(5)
    )


def load_county_population() -> pd.DataFrame:
    """County population denominators from the ACS county tables (Issue 4)."""
    url = (
        "https://api.census.gov/data/2024/acs/acs5/profile"
        "?get=DP05_0001E&for=county:*&in=state:10"
        f"&key={CENSUS_API_KEY}"
    )
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    frame = pd.DataFrame(data[1:], columns=data[0])
    frame["County_FIPS"] = frame["state"] + frame["county"]
    frame["Total_Population"] = pd.to_numeric(frame["DP05_0001E"], errors="coerce")
    return frame.set_index("County_FIPS")[["Total_Population"]]


def build_county_chr() -> pd.DataFrame:
    """Project the CHR release onto its Delaware county rows, unaltered."""
    chr_raw = pd.read_csv(CHR_PATH, dtype=str, low_memory=False)

    live_targets = {v for v in CHR_TARGETS.values() if not v.startswith("__")}
    missing = sorted(v for v in live_targets if v not in chr_raw.columns)
    if missing:
        raise SystemExit(f"CHR snapshot is missing expected columns: {missing}")

    de = chr_raw[_fips(chr_raw["FIPS"]).isin(DE_COUNTY_FIPS)].copy()
    de["County_FIPS"] = _fips(de["FIPS"])

    out = pd.DataFrame(
        {"County_FIPS": de["County_FIPS"], "County_Name": de["County"].str.strip()}
    )
    for out_col, src in CHR_TARGETS.items():
        if src.startswith("__"):
            # Dropped from the 2024 release; kept as NaN so the schema that
            # downstream consumers expect is unchanged.
            out[out_col] = float("nan")
        else:
            out[out_col] = de[src].map(_parse_chr_value)

    out = out.merge(load_county_population(), on="County_FIPS", how="left")

    # Column order: identifiers, then population, then the CHR measures.
    measures = [c for c in CHR_TARGETS if c in out.columns]
    out = out[["County_FIPS", "County_Name", "Total_Population"] + measures]
    out["Population_Source"] = POPULATION_SOURCE
    # Release-year stamp: CHR 2025 clinical-care source year is 2022
    # (see the workbook's Sources & Years sheets).
    out["CHR_Data_Year"] = 2022
    return out


def verify_against_raw(out: pd.DataFrame) -> None:
    """Fail loudly if any emitted value differs from the publisher's snapshot.

    This is the guard against the aggregation bug this script used to have:
    one row per county, and every measure equal to the raw published value.
    """
    raw = pd.read_csv(CHR_PATH, dtype=str, low_memory=False)
    raw_by_fips = raw.assign(_fips=_fips(raw["FIPS"])).set_index("_fips", drop=False)
    problems = []

    if len(out) != len(DE_COUNTY_FIPS):
        problems.append(f"expected {len(DE_COUNTY_FIPS)} county rows, got {len(out)}")

    for _, row in out.iterrows():
        fips = row["County_FIPS"]
        if fips not in raw_by_fips.index:
            problems.append(f"{fips}: not present in the raw CHR snapshot")
            continue
        raw_row = raw_by_fips.loc[fips]
        for out_col, src in CHR_TARGETS.items():
            if src.startswith("__") or out_col not in out.columns:
                continue
            published = _parse_chr_value(raw_row[src])
            emitted = row[out_col]
            if pd.isna(published) and pd.isna(emitted):
                continue
            if pd.isna(published) or pd.isna(emitted) or float(emitted) != float(published):
                problems.append(
                    f"{fips} {out_col}: emitted {emitted!r} != published {published!r}"
                )

    if problems:
        for p in problems:
            print(f"  MISMATCH  {p}")
        raise SystemExit(f"\n{len(problems)} value(s) differ from the raw CHR release")


def main() -> None:
    if not os.path.exists(CHR_PATH):
        raise SystemExit(
            f"{os.path.relpath(CHR_PATH, ROOT)} is missing - run "
            "`python3 fetch_raw_data.py --only chr_2025_de_counties` first."
        )

    out = build_county_chr()
    verify_against_raw(out)
    out.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {os.path.relpath(OUTPUT_PATH, ROOT)}  shape={out.shape}")
    print(f"{len(out)} counties x {len(out.columns)} columns")
    print("Every value verified identical to raw/chr_2025_de_counties_raw.csv\n")
    print(
        out[
            [
                "County_Name",
                "Total_Population",
                "Pct_Poor_Fair_Health",
                "CHR_PCP_Ratio_Population",
                "Dentist_Ratio_Population",
                "Mental_Health_Provider_Ratio",
            ]
        ].to_string(index=False)
    )
    print(f"\nTotal_Population source: {POPULATION_SOURCE}")
    print(
        "\nProvider ratios and Fair/Poor Health are CHR's own published figures, "
        "unaltered.\nNo aggregation, averaging or summing was applied."
    )


if __name__ == "__main__":
    main()