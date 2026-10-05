"""Build the Delaware city/municipality chronic-disease table from CDC PLACES.

A straight projection of the archived publisher snapshot: one row per Delaware
city/place, every value exactly as CDC published it. Nothing is cleaned,
imputed or re-derived.

Two selection decisions are made explicit here rather than left to fall out of
row order, because PLACES publishes more than one series per place:

- Measure type. CDC publishes each measure twice - as an *age-adjusted*
  prevalence and as a *crude* prevalence. Age-adjusted is the headline series
  and the one to compare across places, because crude rates confound health
  with a place's age structure. The primary columns are therefore age-adjusted;
  the crude series is carried alongside in ``*_Crude_Pct`` columns so the
  choice is auditable rather than hidden. (The older PLACES_Delaware_City.csv
  resolved this with ``aggfunc="first"``, i.e. whatever row the API returned
  first - which happened to be age-adjusted but was never stated.)
- Vintage. All three measures below are 2023 for all 79 places. The vintage is
  asserted rather than assumed, so a future release with mixed years fails
  loudly instead of silently mixing them.

PLACES values are model-based small-area estimates, not observed counts, so
every measure keeps its published confidence limits.

Input
  raw/cdc_places_2025_de_city_raw.csv   PLACES place-level release, unmodified
Output
  Delaware_City_Chronic_Disease.csv

Run:
    python3 build_city_chronic_disease_table.py
"""

import os

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
PLACES_PATH = os.path.join(ROOT, "raw", "cdc_places_2025_de_city_raw.csv")
OUTPUT_PATH = os.path.join(ROOT, "Delaware_City_Chronic_Disease.csv")

DELAWARE_STATE = "Delaware"
EXPECTED_VINTAGE = "2023"
PRIMARY_TYPE = "Age-adjusted prevalence"
CRUDE_TYPE = "Crude prevalence"

# The three chronic-disease measures requested, in report order, using the
# publisher's own measure strings.
MEASURES = [
    ("Obesity among adults", "Adult_Obesity_Pct"),
    ("Diagnosed diabetes among adults", "Diabetes_Pct"),
    ("Coronary heart disease among adults", "Coronary_Heart_Disease_Pct"),
]

# (measure, output column) -> which published series and column to read.
VALUE_SOURCES = [
    (PRIMARY_TYPE, "", "data_value"),
    (PRIMARY_TYPE, "_CI_Low", "low_confidence_limit"),
    (PRIMARY_TYPE, "_CI_High", "high_confidence_limit"),
    (CRUDE_TYPE, "_Crude_Pct", "data_value"),
]


def load_delaware_places() -> pd.DataFrame:
    """The snapshot's Delaware rows, with the location name normalised."""
    raw = pd.read_csv(PLACES_PATH, dtype=str, low_memory=False)
    de = raw[raw["statedesc"].fillna("").str.strip().eq(DELAWARE_STATE)].copy()
    de["place"] = de["locationname"].str.strip()
    return de


def check_snapshot(de: pd.DataFrame) -> None:
    """Fail loudly if the snapshot does not match what this script assumes."""
    missing = [m for m, _ in MEASURES if m not in set(de["measure"])]
    if missing:
        raise SystemExit(f"PLACES snapshot is missing expected measures: {missing}")

    for measure, _ in MEASURES:
        rows = de[de["measure"].eq(measure)]
        vintages = sorted(set(rows["year"]))
        if vintages != [EXPECTED_VINTAGE]:
            raise SystemExit(
                f"{measure!r} has vintage(s) {vintages}, expected only "
                f"{EXPECTED_VINTAGE!r}. Refusing to mix vintages in one table."
            )
        for value_type in (PRIMARY_TYPE, CRUDE_TYPE):
            if value_type not in set(rows["data_value_type"]):
                raise SystemExit(f"{measure!r} has no {value_type!r} series in the snapshot.")


def _series(de: pd.DataFrame, measure: str, value_type: str, column: str) -> pd.Series:
    """One published column, keyed by place name."""
    rows = de[de["measure"].eq(measure) & de["data_value_type"].eq(value_type)]
    if rows["place"].duplicated().any():
        dupes = sorted(rows["place"][rows["place"].duplicated()].unique())
        raise SystemExit(f"{measure!r} / {value_type!r} has duplicate places: {dupes[:5]}")
    return pd.to_numeric(rows.set_index("place")[column], errors="coerce")
def build_city_table(de: pd.DataFrame) -> pd.DataFrame:
    """Project the PLACES snapshot onto its Delaware places."""
    out = pd.DataFrame({"City_Municipality": sorted(set(de["place"]))})

    for measure, col_name in MEASURES:
        for value_type, suffix, column in VALUE_SOURCES:
            out[f"{col_name}{suffix}"] = out["City_Municipality"].map(
                _series(de, measure, value_type, column)
            )

    out["State"] = DELAWARE_STATE
    out["PLACES_Vintage"] = EXPECTED_VINTAGE
    out["PLACES_Measure_Type"] = PRIMARY_TYPE
    out["Geography_Level"] = "City / place"
    return out.sort_values("City_Municipality").reset_index(drop=True)


def verify_against_raw(out: pd.DataFrame, de: pd.DataFrame) -> None:
    """Fail loudly if any emitted value differs from the publisher's snapshot."""
    problems = []
    published_places = set(de["place"])
    emitted_places = set(out["City_Municipality"])
    for extra in sorted(emitted_places - published_places):
        problems.append(f"{extra}: emitted but not in the raw snapshot")
    for missing in sorted(published_places - emitted_places):
        problems.append(f"{missing}: in the raw snapshot but not emitted")

    actual = out.set_index("City_Municipality")
    for measure, col_name in MEASURES:
        for value_type, suffix, column in VALUE_SOURCES:
            expected = _series(de, measure, value_type, column)
            for place in sorted(expected.index):
                published = expected[place]
                emitted = (
                    actual.loc[place, f"{col_name}{suffix}"]
                    if place in actual.index
                    else float("nan")
                )
                if pd.isna(published) and pd.isna(emitted):
                    continue
                if (
                    pd.isna(published)
                    or pd.isna(emitted)
                    or float(emitted) != float(published)
                ):
                    problems.append(
                        f"{place} {col_name}{suffix} [{value_type}]: "
                        f"emitted {emitted!r} != published {published!r}"
                    )

    if problems:
        for p in problems[:40]:
            print(f"  MISMATCH  {p}")
        raise SystemExit(f"\n{len(problems)} value(s) differ from the raw PLACES release")


def main() -> None:
    if not os.path.exists(PLACES_PATH):
        raise SystemExit(
            f"{os.path.relpath(PLACES_PATH, ROOT)} is missing - run "
            "`python3 fetch_raw_data.py --only cdc_places_2025_de_city` first."
        )

    de = load_delaware_places()
    check_snapshot(de)
    out = build_city_table(de)
    verify_against_raw(out, de)
    out.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {os.path.relpath(OUTPUT_PATH, ROOT)}  shape={out.shape}")
    print(f"{len(out)} cities x {len(out.columns)} columns, vintage {EXPECTED_VINTAGE}")
    print(
        f"Primary series: {PRIMARY_TYPE} (crude carried in *_Crude_Pct columns).\n"
        "Every value verified identical to raw/cdc_places_2025_de_city_raw.csv\n"
    )
    print(
        out[
            [
                "City_Municipality",
                "Adult_Obesity_Pct",
                "Diabetes_Pct",
                "Coronary_Heart_Disease_Pct",
            ]
        ].head(10).to_string(index=False)
    )
    print(
        "\nConfidence limits sit in the _CI_Low / _CI_High columns beside each measure.\n"
        "These are model-based small-area estimates - report them with those limits."
    )


if __name__ == "__main__":
    main()