"""Rebuild the Delaware county CHR table as a faithful copy of the raw release.

This script used to aggregate the ZCTA-level master back up to county level,
averaging percentages, averaging ratios and summing counts. That was unsound
and is why it was rewritten:

- County Health Rankings publishes county measures directly. The master
  broadcasts each county value onto every ZCTA in that county, so re-aggregating
  ZCTA -> county averaged an identical value against itself.
- Summing a county count across its ZCTAs multiplied it by the ZCTA count:
  Kent's 2,920 premature deaths became 56,892 (19.5x too high).

So nothing is aggregated any more. Every value here is lifted straight out of
the archived publisher snapshot, unchanged. The only value from another source
is Total_Population, because CHR publishes no county population total (its
"High School Completion__Population" / "Some College__Population" columns are
education cohorts, not a population total). That one comes from the HRSA AHRF
postcensal estimate, the only published county total in ./raw.

Inputs
  raw/chr_2025_de_counties_raw.csv        CHR 2025 release, unmodified
  raw/hrsa_ahrf_2025_de_counties_raw.csv  county population denominators
Output
  Delaware_County_CHR.csv

Run:
    python3 generate_county_chr.py
"""

import os

import pandas as pd

# The CHR column mappings (output name -> source column in the raw snapshot)
# are imported from gen_health_data.py so there is a single source of truth
# for them. gen_health_data.py only runs its downloads under __main__, so this
# import is side-effect free.
from gen_health_data import CHR_TARGETS, _parse_chr_value

ROOT = os.path.dirname(os.path.abspath(__file__))
CHR_PATH = os.path.join(ROOT, "raw", "chr_2025_de_counties_raw.csv")
AHRF_PATH = os.path.join(ROOT, "raw", "hrsa_ahrf_2025_de_counties_raw.csv")
OUTPUT_PATH = os.path.join(ROOT, "Delaware_County_CHR.csv")

DE_COUNTY_FIPS = ["10001", "10003", "10005"]

# AHRF postcensal population estimate used as the county population total.
POPULATION_SOURCE_COL = "pop_popn_est_23"
POPULATION_SOURCE = "HRSA AHRF 2024-2025 (postcensal estimate, 2023 vintage)"


def _fips(series: pd.Series) -> pd.Series:
    """Normalise FIPS to a 5-digit string ('10001', not '10001.0')."""
    return (
        series.astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(5)
    )


def load_county_population() -> pd.DataFrame:
    """County population denominators straight from the AHRF snapshot."""
    ahrf = pd.read_csv(AHRF_PATH, dtype=str, low_memory=False)
    frame = pd.DataFrame(
        {
            "County_FIPS": _fips(ahrf["fips_st_cnty"]),
            "Total_Population": pd.to_numeric(ahrf[POPULATION_SOURCE_COL], errors="coerce"),
        }
    )
    return frame.set_index("County_FIPS")


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
    for path, hint in (
        (CHR_PATH, "chr_2025_de_counties"),
        (AHRF_PATH, "hrsa_ahrf_2025_de_counties"),
    ):
        if not os.path.exists(path):
            raise SystemExit(
                f"{os.path.relpath(path, ROOT)} is missing - run "
                f"`python3 fetch_raw_data.py --only {hint}` first."
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
    print(f"        column: {POPULATION_SOURCE_COL}")
    print(
        "\nProvider ratios and Fair/Poor Health are CHR's own published figures, "
        "unaltered.\nNo aggregation, averaging or summing was applied."
    )


if __name__ == "__main__":
    main()