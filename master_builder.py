"""Assemble a master dataset from any user-selected subset of data sources.

build_master() is the single entry point used by the Streamlit UI and by the
extract_census.py CLI. It joins the selected sources at the requested geography
level, records a per-source join report, and applies a Tableau-readiness pass to
the result (column hygiene, geographic-role helper fields, WGS84 polygons).

Tableau contract
    Every deliverable is a single flat table, one row per geography, written to
    a stable filename so a Tableau live connection survives rebuilds:

        DE_Health_{LEVEL}_Master.csv             flat table, all attributes
        DE_Health_{LEVEL}_Master.geojson         ZCTA level, WGS84 MultiPolygon
        DE_Health_{LEVEL}_Field_Manifest.csv     column -> source documentation
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

import pandas as pd

from data_sources import (
    JUNK_COLUMNS,
    LEVELS,
    SOURCE_INDEX,
    Source,
    default_sources_for_level,
    sanitize_column_name,
    source_by_key,
)

# Columns whose string form must be preserved (leading zeros, identifiers).
PROTECTED_STRING_COLUMNS = {
    "ZIP",
    "ZCTA",
    "CensusTractFIPS",
    "City_Name",
    "County_Name",
    "CountyName",
    "County_FIPS",
    "CountyFIPS",
    "State",
}

# Keys and geographic-role helper fields are ordered first in every export.
GEO_ORDER = (
    "ZIP",
    "ZCTA",
    "CensusTractFIPS",
    "City_Name",
    "State",
    "County_Name",
    "CountyName",
    "County_FIPS",
    "CountyFIPS",
    "Latitude",
    "Longitude",
)


@dataclass
class SourceReport:
    """What happened when one source was merged into the master."""

    key: str
    label: str
    join_key: str | None
    status: str = "pending"
    rows_in: int = 0
    rows_matched: int = 0
    rows_unmatched: int = 0
    duplicate_keys: int = 0
    columns_added: int = 0
    message: str = ""


@dataclass
class BuildReport:
    """Full provenance and join diagnostics for one master build."""

    level: str
    base_source: str | None = None
    rows: int = 0
    columns: int = 0
    sources: list[SourceReport] = field(default_factory=list)
    source_of_column: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def report_for(self, key: str) -> SourceReport | None:
        return next((r for r in self.sources if r.key == key), None)

    def to_frame(self) -> pd.DataFrame:
        """Per-source join diagnostics as a displayable table."""
        return pd.DataFrame(
            [
                {
                    "Source": r.label,
                    "Key": r.key,
                    "Joined On": "broadcast" if r.join_key is None else r.join_key,
                    "Status": r.status,
                    "Rows In": r.rows_in,
                    "Rows Matched": r.rows_matched,
                    "Rows Unmatched": r.rows_unmatched,
                    "Duplicate Keys": r.duplicate_keys,
                    "Columns Added": r.columns_added,
                    "Note": r.message,
                }
                for r in self.sources
            ]
        )

    def manifest(self) -> pd.DataFrame:
        """Column-level documentation for the Tableau field manifest."""
        level_label = LEVELS[self.level]["label"]
        rows = []
        for column, source_key in self.source_of_column.items():
            source = SOURCE_INDEX.get(source_key)
            rows.append(
                {
                    "Column": column,
                    "Source": source.label if source else source_key,
                    "Source Key": source_key,
                    "Geography Level": level_label,
                }
            )
        return pd.DataFrame(rows)


def validate_selection(level: str, keys: Iterable[str], geometry: bool = True) -> tuple[list[str], list[str]]:
    """Return (blocking problems, warnings) for a proposed source selection."""
    if level not in LEVELS:
        return [f"Unknown geography level: {level}"], []

    selected = list(keys)
    problems: list[str] = []
    warnings: list[str] = []

    unknown = [k for k in selected if k not in SOURCE_INDEX]
    if unknown:
        problems.append(f"Unknown data source(s): {', '.join(unknown)}")
    if not selected:
        problems.append("Select at least one data source.")

    for key in selected:
        if key in SOURCE_INDEX and not SOURCE_INDEX[key].available(level):
            problems.append(
                f"'{SOURCE_INDEX[key].label}' cannot be merged at the "
                f"{LEVELS[level]['label']} level."
            )

    available = [k for k in selected if k in SOURCE_INDEX and SOURCE_INDEX[k].available(level)]
    has_geometry = any(SOURCE_INDEX[k].provides_geometry for k in available)

    if geometry and LEVELS[level]["supports_geometry"] and not has_geometry:
        problems.append(
            "Spatial output needs a boundary source. Add 'ZCTA boundaries' or turn off "
            "the GeoJSON export."
        )

    # Sources whose join key is supplied by another selected source.
    key_providers = {"chr_county": {"zcta": "spatial_zcta"}}
    for key, providers in key_providers.items():
        if key not in available:
            continue
        dependency = providers.get(level)
        if dependency and dependency not in available:
            problems.append(
                f"'{SOURCE_INDEX[key].label}' joins on {SOURCE_INDEX[key].join_key(level)}, "
                f"which only '{SOURCE_INDEX[dependency].label}' provides at this level."
            )

    if "metrics" in available and "acs" not in available:
        warnings.append(
            "Derived metrics need ACS inputs (Total_Population and the percentage "
            "measures). Metrics that cannot be computed are skipped."
        )

    if not has_geometry and LEVELS[level]["supports_geometry"]:
        warnings.append("No boundary source selected, so this master is tabular only.")

    if available and all(SOURCE_INDEX[k].derived for k in available):
        warnings.append("Every selected source is derived; the master may be mostly empty.")

    return problems, warnings


def missing_source_files(keys: Iterable[str]) -> list[tuple[str, str]]:
    """Local-file sources whose backing file is absent, as (key, path) pairs."""
    from data_sources import (
        BRFSS_CSV_PATH,
        BRFSS_ZCTA_CSV_PATH,
        CHR_CSV_PATH,
        COUNTY_CHR_PATH,
        PLACES_CITY_PATH,
        PLACES_TRACT_PATH,
    )

    local_paths = {
        "chr_county": CHR_CSV_PATH,
        "brfss_state": BRFSS_CSV_PATH,
        "brfss_zcta": BRFSS_ZCTA_CSV_PATH,
        "places_tract": PLACES_TRACT_PATH,
        "places_city": PLACES_CITY_PATH,
        "county_chr": COUNTY_CHR_PATH,
    }
    missing = []
    for key in keys:
        path = local_paths.get(key)
        if path and not os.path.exists(path):
            missing.append((key, path))
    return missing


# ---------------------------------------------------------------------------
# Master assembly
# ---------------------------------------------------------------------------
def _choose_base_source(level: str, frames: dict[str, pd.DataFrame]) -> str | None:
    """Pick the frame that supplies the master's base geography."""
    for key in LEVELS[level]["base_order"]:
        if key in frames:
            return key
    return next(iter(frames), None)


def _canonical_key(name: str) -> str:
    """Normalise a join-key name for fuzzy matching (CountyFIPS vs County_FIPS)."""
    return sanitize_column_name(str(name)).lower().replace("_", "")


def _resolve_join_column(
    master: pd.DataFrame, right: pd.DataFrame, join_col: str
) -> tuple[str | None, str | None]:
    """Find the join key on both sides, tolerating FIPS / name spelling variants.

    Returns (left column, right column), or (None, None) when no match exists.
    """
    if join_col in master.columns and join_col in right.columns:
        return join_col, join_col
    if join_col not in master.columns:
        return None, None

    target = _canonical_key(join_col)
    for candidate in right.columns:
        if _canonical_key(candidate) == target:
            return join_col, candidate
    return None, None


def _merge_source(
    master: pd.DataFrame,
    right: pd.DataFrame,
    source: Source,
    join_col: str | None,
    entry: SourceReport,
    report: BuildReport,
) -> pd.DataFrame:
    """Merge one source into the master, recording join diagnostics."""
    rows_before = len(master)
    entry.rows_in = len(right)

    if join_col is None:  # broadcast: a single statewide record
        row = right.iloc[0]
        additions = {
            column: row[column]
            for column in right.columns
            if column != "State" and column not in master.columns
        }
        if additions:
            master = pd.concat(
                [master, pd.DataFrame(additions, index=master.index)], axis=1
            )
            for column in additions:
                report.source_of_column[column] = source.key
        entry.status = "broadcast"
        entry.rows_matched = rows_before
        entry.columns_added = len(additions)
        entry.message = "Single statewide record copied onto every master row."
        return master

    left_col, right_col = _resolve_join_column(master, right, join_col)
    if left_col is None:
        entry.status = "skipped"
        entry.message = f"No {join_col} column at this level."
        report.add_warning(
            f"'{source.label}' was skipped: the master has no {join_col} column at this level."
        )
        return master
    if right_col is None:
        entry.status = "skipped"
        entry.message = f"Source has no {join_col} column."
        report.add_warning(f"'{source.label}' was skipped: the source has no {join_col} column.")
        return master
    if right_col != left_col:
        right = right.rename(columns={right_col: left_col})
    join_col = left_col


    entry.duplicate_keys = int(right[join_col].astype(str).duplicated().sum())
    if entry.duplicate_keys:
        right = right.drop_duplicates(subset=[join_col], keep="first")
        report.add_warning(
            f"'{source.label}' had {entry.duplicate_keys} duplicate {join_col} value(s); "
            "the first occurrence was kept to protect the row count."
        )

    overlap = [c for c in right.columns if c in master.columns and c != join_col]
    right = right.drop(columns=overlap)

    left = master.copy()
    left[join_col] = left[join_col].astype(str)
    right = right.copy()
    right[join_col] = right[join_col].astype(str)

    merged = left.merge(right, on=join_col, how="left", indicator=True)
    matched = int(merged["_merge"].eq("both").sum())
    merged = merged.drop(columns=["_merge"])

    entry.status = "joined"
    entry.rows_matched = matched
    entry.rows_unmatched = rows_before - matched
    entry.columns_added = max(len(right.columns) - 1, 0)
    if entry.rows_unmatched:
        entry.message = f"{entry.rows_unmatched} master row(s) had no matching {join_col}."

    if len(merged) != rows_before:
        report.add_warning(
            f"'{source.label}' changed the row count from {rows_before} to {len(merged)}."
        )

    for column in right.columns:
        if column != join_col:
            report.source_of_column.setdefault(column, source.key)
    return merged


def _add_derived_metrics(
    master: pd.DataFrame, entry: SourceReport, report: BuildReport
) -> pd.DataFrame:
    """Compute the derived density and population-count metrics."""
    pop = "Total_Population"
    specs = [
        (
            "Population_Density_SqMi",
            lambda df: (df[pop] / df["Land_Area_SqMi"]).round(2),
            (pop, "Land_Area_SqMi"),
        ),
        (
            "Uninsured_Population_Count",
            lambda df: ((df["Pct_No_Health_Insurance"] / 100) * df[pop]).round(0),
            ("Pct_No_Health_Insurance", pop),
        ),
        (
            "Poverty_Population_Count",
            lambda df: ((df["Pct_Below_Poverty"] / 100) * df[pop]).round(0),
            ("Pct_Below_Poverty", pop),
        ),
        (
            "Seniors_65_Plus_Count",
            lambda df: ((df["Pct_Age_65_Plus"] / 100) * df[pop]).round(0),
            ("Pct_Age_65_Plus", pop),
        ),
        (
            "No_Broadband_Households_Estimate",
            lambda df: (((100 - df["Pct_Broadband_Internet"]) / 100) * df[pop]).round(0),
            ("Pct_Broadband_Internet", pop),
        ),
    ]

    added, skipped = 0, []
    for name, compute, inputs in specs:
        if not all(col in master.columns for col in inputs):
            skipped.append(name)
            continue
        master[name] = compute(master)
        report.source_of_column[name] = "metrics"
        added += 1

    entry.status = "computed"
    entry.columns_added = added
    entry.message = f"Computed {added} derived metric(s)."
    if skipped:
        entry.message += f" Skipped for missing inputs: {', '.join(skipped)}."
        for name in skipped:
            report.add_warning(f"Derived metric '{name}' was skipped: missing input column(s).")
    return master


def build_master(
    level: str = "zcta",
    sources: Iterable[str] | None = None,
    *,
    geometry: bool = True,
    raw_columns: bool = False,
) -> tuple[pd.DataFrame, BuildReport]:
    """Join the selected sources at `level` into one master dataset.

    Returns (master, report). `master` is a GeoDataFrame when a geometry source
    is included, otherwise a plain DataFrame.
    """
    level = str(level).lower()
    if level not in LEVELS:
        raise ValueError(
            f"Unknown geography level: {level!r}. Expected one of: {', '.join(LEVELS)}."
        )

    keys = list(sources) if sources is not None else default_sources_for_level(level)
    problems, warnings = validate_selection(level, keys, geometry=geometry)
    if problems:
        raise ValueError(" ".join(problems))

    missing = missing_source_files(keys)
    if missing:
        raise FileNotFoundError(
            "; ".join(f"{SOURCE_INDEX[key].label}: {path} not found" for key, path in missing)
        )

    report = BuildReport(level=level)
    for message in warnings:
        report.add_warning(message)

    # ---- load --------------------------------------------------------------
    frames: dict[str, pd.DataFrame] = {}
    for key in keys:
        source = source_by_key(key)
        report.sources.append(
            SourceReport(key=key, label=source.label, join_key=source.join_key(level))
        )
        if source.loader is not None:
            frames[key] = source.loader()

    base_key = _choose_base_source(level, frames)
    if base_key is None:
        raise ValueError("None of the selected sources can provide the base geography.")

    report.base_source = base_key
    master = frames[base_key].copy()
    base_entry = report.report_for(base_key)
    base_entry.status = "base"
    base_entry.rows_in = len(master)
    base_entry.columns_added = len(master.columns)
    base_entry.message = "Base geography for this level."
    for column in master.columns:
        report.source_of_column.setdefault(column, base_key)

    # ---- join --------------------------------------------------------------
    for key in keys:
        if key == base_key or key not in frames:
            continue
        source = source_by_key(key)
        master = _merge_source(
            master,
            frames[key],
            source,
            source.join_key(level),
            report.report_for(key),
            report,
        )

    # ---- derived metrics ---------------------------------------------------
    metrics_entry = report.report_for("metrics")
    if metrics_entry is not None:
        master = _add_derived_metrics(master, metrics_entry, report)

    # ---- Tableau-readiness pass -------------------------------------------
    master = to_tableau_frame(master, level, raw_columns=raw_columns)
    for column in master.columns:
        report.source_of_column.setdefault(column, "derived")
    # Keep the manifest in step with the final frame: to_tableau_frame drops
    # raw-file cruft, so provenance for dropped columns must not be reported.
    final_columns = set(master.columns) - {"geometry"}
    report.source_of_column = {
        column: source for column, source in report.source_of_column.items() if column in final_columns
    }

    if "geometry" in master.columns:
        unmappable = non_polygonal_keys(master, level)
        if unmappable:
            report.add_warning(
                "Omitted from the GeoJSON because they have no polygon geometry after clipping: "
                f"{', '.join(unmappable)}. These rows remain in the CSV and XLSX tables."
            )

    report.rows = len(master)
    report.columns = len(master.columns)
    return master, report


# ---------------------------------------------------------------------------
# Tableau-readiness pass
# ---------------------------------------------------------------------------
def _unique_ascii_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Force ASCII-only, unique column names (non-ASCII names confuse Tableau)."""
    seen: dict[str, int] = {}
    mapping: dict[str, str] = {}
    for column in df.columns:
        base = sanitize_column_name(column)
        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 0
        mapping[column] = base
    return df.rename(columns=mapping)


def _centroids_wgs84(frame: pd.DataFrame) -> tuple[pd.Series | None, pd.Series | None]:
    """WGS84 centroid coordinates, so Tableau can plot points without geocoding.

    Centroids are computed in CONUS Albers (EPSG:5070) because a centroid taken
    directly in a geographic CRS is not meaningful, then converted to WGS84.
    """
    try:
        import geopandas as gpd

        gdf = gpd.GeoDataFrame(frame.copy(), geometry="geometry", crs=getattr(frame, "crs", None))
        centroids = gdf.to_crs(5070).geometry.centroid.to_crs(4326)
        return centroids.y.round(6), centroids.x.round(6)
    except Exception:
        return None, None


def to_tableau_frame(frame: pd.DataFrame, level: str, *, raw_columns: bool = False) -> pd.DataFrame:
    """Apply column hygiene and geographic-role helper fields for Tableau.

    - drops raw-file cruft columns (unless raw_columns)
    - adds ZIP, State, County_Name aliases so Tableau auto-assigns geo roles
    - adds Latitude / Longitude from the polygon centroids
    - keeps measures numeric and identifiers as strings
    - guarantees ASCII-only, unique column names, key columns first
    """
    df = frame.copy()

    latitude = longitude = None
    if "geometry" in df.columns:
        latitude, longitude = _centroids_wgs84(frame)

    if not raw_columns:
        df = df.drop(columns=[c for c in JUNK_COLUMNS if c in df.columns])

    if "ZCTA" in df.columns and "ZIP" not in df.columns:
        df.insert(0, "ZIP", df["ZCTA"].astype(str).str.zfill(5))
    if "CountyName" in df.columns and "County_Name" not in df.columns:
        df["County_Name"] = df["CountyName"].astype(str)
    if latitude is not None and "Latitude" not in df.columns:
        df["Latitude"] = latitude
        df["Longitude"] = longitude
    if "State" not in df.columns:
        df["State"] = "Delaware"

    for column in df.columns:
        if column in PROTECTED_STRING_COLUMNS or df[column].dtype != object:
            continue
        converted = pd.to_numeric(df[column], errors="coerce")
        if converted.notna().sum() == df[column].notna().sum():
            df[column] = converted

    df = df.replace([float("inf"), float("-inf")], pd.NA)
    df = _unique_ascii_columns(df)

    leader = [c for c in GEO_ORDER if c in df.columns]
    trailer = [c for c in df.columns if c not in GEO_ORDER]
    return df[leader + trailer]


def non_polygonal_keys(frame: pd.DataFrame, level: str, limit: int = 10) -> list[str]:
    """Geography keys that carry no polygon part and so cannot be mapped.

    Tableau spatial files must contain a single polygon geometry type, so these
    rows are omitted from the GeoJSON. They always remain in the CSV / XLSX
    table, and the build report names them so nothing disappears silently.
    """
    if "geometry" not in frame.columns:
        return []
    try:
        import geopandas as gpd

        key_column = LEVELS[level]["key_column"]
        if key_column not in frame.columns:
            return []
        gdf = gpd.GeoDataFrame(
            frame.copy(), geometry="geometry", crs=getattr(frame, "crs", None)
        )
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        gdf = gdf.explode(index_parts=False)
        polygonal = set(
            gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])][key_column].astype(str)
        )
        return [key for key in frame[key_column].astype(str) if key not in polygonal][:limit]
    except Exception:
        return []


def write_geojson(frame: pd.DataFrame, level: str, path: str) -> str:
    """Write a Tableau-readable GeoJSON: WGS84, MultiPolygon only, no empty geometry.

    Tableau reads GeoJSON as WGS84 and expects a single geometry type per file,
    so mixed Polygon / Point / GeometryCollection output is normalised first.
    """
    import geopandas as gpd
    from shapely.geometry import MultiPolygon

    key_column = LEVELS[level]["key_column"]
    gdf = gpd.GeoDataFrame(frame.copy(), geometry="geometry", crs=getattr(frame, "crs", None))
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf[~gdf.geometry.is_empty]
    gdf = gdf.explode(index_parts=False)
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf["geometry"] = gdf.geometry.apply(
        lambda geom: geom if isinstance(geom, MultiPolygon) else MultiPolygon([geom])
    )

    if key_column in gdf.columns:
        # One feature per geography, so a Tableau map never double-draws a unit.
        gdf = gdf.dissolve(by=key_column, aggfunc="first", as_index=False)
        gdf["geometry"] = gdf.geometry.apply(
            lambda geom: geom if isinstance(geom, MultiPolygon) else MultiPolygon([geom])
        )

    gdf = gdf.to_crs(4326)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    gdf.to_file(path, driver="GeoJSON")

    # RFC 7946 GeoJSON has no crs member: coordinates are always WGS84. Tableau
    # reads GeoJSON as WGS84, and some readers warn on an explicit member, so
    # strip it and keep the file compact.
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.pop("crs", None) is not None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
    return path


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def write_tableau_bundle(
    frame: pd.DataFrame,
    level: str,
    out_dir: str,
    *,
    report: BuildReport | None = None,
    raw_columns: bool = False,
    formats: Iterable[str] = ("csv", "xlsx", "geojson"),
    archive_dir: str | None = None,
    stamp: str | None = None,
) -> dict[str, str]:
    """Write the Tableau deliverables under stable filenames.

    CSV and XLSX hold the flat attribute table (no geometry); the GeoJSON holds
    the same attributes plus WGS84 MultiPolygon geometry. A field manifest
    documents which source produced each column. Optional archive_dir receives
    timestamped copies for history.
    """
    level = level.lower()
    os.makedirs(out_dir, exist_ok=True)
    stem = f"DE_Health_{level.upper()}_Master"
    frames = to_tableau_frame(frame, level, raw_columns=raw_columns)
    tabular = frames.drop(columns=["geometry"], errors="ignore")

    written: dict[str, str] = {}
    formats = tuple(formats)
    if "csv" in formats:
        path = os.path.join(out_dir, f"{stem}.csv")
        tabular.to_csv(path, index=False)
        written["csv"] = path
    if "xlsx" in formats:
        path = os.path.join(out_dir, f"{stem}.xlsx")
        tabular.to_excel(path, index=False)
        written["xlsx"] = path
    if "geojson" in formats and "geometry" in frames.columns:
        path = os.path.join(out_dir, f"{stem}.geojson")
        write_geojson(frames, level, path)
        written["geojson"] = path
    if report is not None:
        path = os.path.join(out_dir, f"{stem}_Field_Manifest.csv")
        report.manifest().to_csv(path, index=False)
        written["manifest"] = path

    if archive_dir:
        stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(archive_dir, exist_ok=True)
        for path in list(written.values()):
            name = os.path.basename(path)
            root, ext = os.path.splitext(name)
            shutil.copy2(path, os.path.join(archive_dir, f"{root}_{stamp}{ext}"))
    return written


# Legacy filenames kept so existing Tableau workbooks keep resolving.
CANONICAL_FILES = {
    "csv": "Delaware_ZCTA_Health_Master_Wide.csv",
    "xlsx": "Delaware_ZCTA_Health_Master_Wide.xlsx",
    "geojson": "Delaware_ZCTA_Health_Master_Spatial.geojson",
}


def write_canonical_master(frame: pd.DataFrame, out_dir: str) -> dict[str, str]:
    """Write the historical root-level master filenames at the ZCTA level."""
    written: dict[str, str] = {}
    tabular = frame.drop(columns=["geometry"], errors="ignore")

    csv_path = os.path.join(out_dir, CANONICAL_FILES["csv"])
    tabular.to_csv(csv_path, index=False)
    written["csv"] = csv_path

    xlsx_path = os.path.join(out_dir, CANONICAL_FILES["xlsx"])
    tabular.to_excel(xlsx_path, index=False)
    written["xlsx"] = xlsx_path

    if "geometry" in frame.columns:
        geojson_path = os.path.join(out_dir, CANONICAL_FILES["geojson"])
        write_geojson(frame, "zcta", geojson_path)
        written["geojson"] = geojson_path
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_source_matrix() -> None:
    from data_sources import sources_for_level

    print("Data sources by geography level")
    print("=" * 72)
    for level, meta in LEVELS.items():
        print(f"\n{level}  -  {meta['label']}")
        for source in sources_for_level(level):
            key = source.join_key(level)
            joined = "broadcast" if key is None else key
            tag = " [derived]" if source.derived else ""
            print(f"  {source.key:14s} join on {joined:16s} {source.label}{tag}")
    print("\nDefault ZCTA composition: " + ", ".join(default_sources_for_level("zcta")))


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a Tableau-ready master dataset from selected data sources."
    )
    parser.add_argument("--list", action="store_true", help="List data sources per level and exit.")
    parser.add_argument("--level", default="zcta", choices=sorted(LEVELS), help="Geography level.")
    parser.add_argument(
        "--sources",
        default=None,
        help="Comma-separated source keys. Defaults to the level's standard composition.",
    )
    parser.add_argument("--out", default=os.path.join(os.getcwd(), "tableau_exports"))
    parser.add_argument("--no-geojson", action="store_true", help="Skip the spatial export.")
    parser.add_argument("--raw-columns", action="store_true", help="Keep raw source columns.")
    args = parser.parse_args(argv)

    if args.list:
        _print_source_matrix()
        return 0

    keys = [k.strip() for k in args.sources.split(",")] if args.sources else None
    frame, report = build_master(
        args.level,
        keys,
        geometry=not args.no_geojson,
        raw_columns=args.raw_columns,
    )
    formats = ("csv", "xlsx") if args.no_geojson else ("csv", "xlsx", "geojson")
    written = write_tableau_bundle(
        frame, args.level, args.out, report=report, raw_columns=args.raw_columns, formats=formats
    )

    print(f"\nBuilt {report.rows} rows x {report.columns} columns at the {args.level} level.")
    print(f"Base geography: {report.base_source}")
    print(report.to_frame().to_string(index=False))
    for warning in report.warnings:
        print(f"Warning: {warning}")
    print("\nWritten:")
    for kind, path in written.items():
        print(f"  {kind:9s} {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())






