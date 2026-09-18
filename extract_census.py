"""Delaware SDOH & Census health data pipeline entry point.

Builds the ZCTA-level master from every source, then writes both the canonical
output files and the Tableau export bundle.

The source definitions live in data_sources.py and the join logic lives in
master_builder.py, so this file stays a thin command-line wrapper with no
duplicated extraction code.

Usage
    python3 extract_census.py                                   # full ZCTA master
    python3 extract_census.py --sources spatial_zcta,acs,metrics
    python3 extract_census.py --level tract --no-geojson
    python3 extract_census.py --list                            # source/level matrix
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:  # dotenv is optional; data_sources reads the env directly
    pass

from data_sources import (  # noqa: E402
    ACS_VARS,
    BRFSS_STATE_MEASURES,
    NULL_CODES,
    default_sources_for_level,
    load_acs,
    load_brfss_state,
    load_chr_county,
    load_spatial_boundaries,
)
from master_builder import (  # noqa: E402
    _print_source_matrix,
    build_master,
    write_canonical_master,
    write_tableau_bundle,
)

TABLEAU_DIR = os.path.join(ROOT, "tableau_exports")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")

# ---------------------------------------------------------------------------
# Backwards-compatible names. Earlier revisions of this module exposed these
# loaders directly; they now delegate to data_sources so every download has a
# single implementation.
# ---------------------------------------------------------------------------
BRFSS_MEASURES = BRFSS_STATE_MEASURES


def fetch_spatial_boundaries():
    """ZCTA boundaries clipped to Delaware (see data_sources.load_spatial_boundaries)."""
    return load_spatial_boundaries()


def fetch_acs_data(api_key: str | None = None):
    """Census ACS 5-Year Data Profile metrics (see data_sources.load_acs)."""
    return load_acs(api_key if api_key else CENSUS_API_KEY)


def load_county_health_rankings(filepath: str | None = None):
    """County Health Rankings indicators (see data_sources.load_chr_county).

    `filepath` is accepted for backwards compatibility; the canonical
    CHR_Delaware.csv is always used.
    """
    return load_chr_county()


def fetch_brfss_state_data():
    """CDC BRFSS 2024 Delaware state prevalence (see data_sources.load_brfss_state)."""
    return load_brfss_state()


def _brfss_row_from_api() -> dict:
    """Single statewide BRFSS record taken from the resolved BRFSS source."""
    return load_brfss_state().iloc[0].to_dict()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the Delaware master dataset and write the Tableau exports."
    )
    parser.add_argument("--list", action="store_true", help="Show the source/level matrix and exit.")
    parser.add_argument("--level", default="zcta", choices=["zcta", "tract", "city", "county"])
    parser.add_argument(
        "--sources",
        default=None,
        help="Comma-separated source keys. Defaults to every source for the level.",
    )
    parser.add_argument("--no-geojson", action="store_true", help="Skip the spatial export.")
    parser.add_argument(
        "--no-canonical",
        action="store_true",
        help="Skip the legacy root-level Delaware_ZCTA_Health_Master_* files.",
    )
    args = parser.parse_args(argv)

    if args.list:
        _print_source_matrix()
        return 0

    keys = (
        [key.strip() for key in args.sources.split(",")]
        if args.sources
        else default_sources_for_level(args.level)
    )
    print(f"Building the {args.level} master from: {', '.join(keys)}")

    frame, report = build_master(args.level, keys, geometry=not args.no_geojson)
    print(f"\nMerged {report.rows} rows x {report.columns} columns.")
    print(report.to_frame().to_string(index=False))
    for warning in report.warnings:
        print(f"Warning: {warning}")

    print("\nWriting the Tableau export bundle...")
    formats = ("csv", "xlsx") if args.no_geojson else ("csv", "xlsx", "geojson")
    for kind, path in write_tableau_bundle(
        frame, args.level, TABLEAU_DIR, report=report, formats=formats
    ).items():
        print(f"  {kind:9s} {path}")

    if args.level == "zcta" and not args.no_canonical:
        print("Writing the canonical master files...")
        for kind, path in write_canonical_master(frame, ROOT).items():
            print(f"  {kind:9s} {path}")

    print("Successfully exported all files with County Health Rankings added!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
