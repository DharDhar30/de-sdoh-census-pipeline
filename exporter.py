"""Export engine for the Delaware ZCTA health sector exports.

Pandas-only (no Streamlit dependency) so it can also be reused from scripts.
"""

import os
from typing import Iterable

import pandas as pd

from sector_definitions import KEY_COLUMNS, SECTORS


# ---------------------------------------------------------------------------
# Compatibility fix for pandas >= 2.2 where io.excel.zip.reader config option
# was removed but the ExcelFile init code still tries to look it up.
# ---------------------------------------------------------------------------
def _fix_pandas_excel_config() -> None:
    """Register the missing io.excel.zip.reader config option if needed."""
    from pandas._config import config as _config

    try:
        _config.get_option("io.excel.zip.reader", silent=True)
    except Exception:
        try:
            _config.register_option("io.excel.zip.reader", "openpyxl", validator=str)
        except Exception:
            pass  # already registered by a previous call


_fix_pandas_excel_config()


def normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    """Drop geometry (spatial-only) and normalise ZCTA keys to 5-digit strings."""
    if "geometry" in df.columns:
        df = df.drop(columns=["geometry"])
    for col in ("ZCTA", "ZCTA5CE20", "GEOID20"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.zfill(5)
    return df


def load_master_data(source_path: str) -> pd.DataFrame:
    """Load the master dataset from xlsx / xls / csv / geojson."""
    ext = os.path.splitext(source_path)[1].lower()
    if ext == ".geojson":
        import geopandas as gpd

        gdf = gpd.read_file(source_path)
        return normalize_master(pd.DataFrame(gdf))
    if ext in (".xlsx", ".xls"):
        return normalize_master(pd.read_excel(source_path))
    if ext == ".csv":
        return normalize_master(pd.read_csv(source_path))
    raise ValueError(f"Unsupported file type: {source_path}")


def _key_columns(df: pd.DataFrame, include_keys: bool) -> list[str]:
    if not include_keys:
        return []
    return [c for c in KEY_COLUMNS if c in df.columns]


def build_sector_tables(
    df: pd.DataFrame, picked_columns: Iterable[str], include_keys: bool = True
) -> dict[str, pd.DataFrame]:
    """Split the master frame into one table per sector.

    Returns {sector_name: DataFrame} where each table keeps the key columns
    first (ZCTA / County_FIPS / County_Name when present) followed by that
    sector's picked columns. Empty sectors are skipped.
    """
    picked = [c for c in picked_columns if c in df.columns]
    keys = _key_columns(df, include_keys)
    tables: dict[str, pd.DataFrame] = {}
    for sector, columns in SECTORS.items():
        chosen = [c for c in columns if c in picked]
        if not chosen:
            continue
        ordered = list(dict.fromkeys(keys + chosen))
        tables[sector] = df[ordered].copy()
    return tables


def build_combined(
    df: pd.DataFrame, picked_columns: Iterable[str], include_keys: bool = True
) -> pd.DataFrame:
    """One wide table with every picked column (deduped, keys first)."""
    picked = [c for c in picked_columns if c in df.columns]
    keys = _key_columns(df, include_keys)
    return df[list(dict.fromkeys(keys + picked))].copy()


def _safe_name(name: str) -> str:
    """Excel-safe sheet/filename: strip forbidden chars, cap at 31 chars."""
    forbidden = "[]:*?/\\"
    cleaned = "".join("_" if ch in forbidden else ch for ch in name)
    return (cleaned[:31] or "Sheet").strip()


def export_multi_sheet_excel(tables: dict[str, pd.DataFrame], out_path: str) -> str:
    """Write every sector table as its own sheet in a single .xlsx workbook."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet, table in tables.items():
            table.to_excel(writer, sheet_name=_safe_name(sheet), index=False)
    return out_path


def export_separate_files(
    tables: dict[str, pd.DataFrame],
    out_dir: str,
    fmt: str = "csv",
    prefix: str = "DE_Health",
) -> list[str]:
    """Write one file per sector into out_dir. Returns the written file paths."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for sector, table in tables.items():
        filename = f"{prefix}_{_safe_name(sector).replace(' ', '_')}.{fmt}"
        path = os.path.join(out_dir, filename)
        if fmt == "csv":
            table.to_csv(path, index=False)
        else:
            table.to_excel(path, index=False)
        paths.append(path)
    return paths


def export_combined(df: pd.DataFrame, out_path: str) -> str:
    """Write the combined wide table to csv or xlsx based on the extension."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if out_path.lower().endswith(".csv"):
        df.to_csv(out_path, index=False)
    else:
        df.to_excel(out_path, index=False)
    return out_path
