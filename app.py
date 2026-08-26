"""Delaware ZCTA Health · Sector Export UI

Streamlit app that loads the master dataset, lets you pick and choose columns
grouped by sector (County Health Ratings, Dental Care, Behavioral Health,
Demographics, Socioeconomic, Health Access, Calculated Metrics, Geographic),
previews the result, and exports as either one multi-sheet Excel workbook or
separate per-sector files.

Generated files are written to ./exports and ./outputs (both git-ignored) so
the working tree stays clean - no more spreadsheets piling up in the repo.

Run:  streamlit run app.py   (or double-click start_ui.command)
"""

import io
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st

from exporter import (
    build_combined,
    build_sector_tables,
    export_combined,
    export_multi_sheet_excel,
    export_separate_files,
    load_master_data,
    normalize_master,
)
from sector_definitions import SECTORS, all_sector_columns

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT, "outputs")
EXPORTS_DIR = os.path.join(ROOT, "exports")
ETL_SCRIPT = os.path.join(ROOT, "extract_census.py")
GEOJSON_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Spatial.geojson")
GENERATED_FILES = [
    "Delaware_ZCTA_Health_Master_Wide.xlsx",
    "Delaware_ZCTA_Health_Master_Wide.csv",
]

st.set_page_config(page_title="DE Health Sector Exporter", page_icon="🏥", layout="wide")


# ---------------------------------------------------------------------------
# Data source helpers
# ---------------------------------------------------------------------------
def find_latest_source() -> str | None:
    """Prefer the newest master file in outputs/, then root, then the geojson."""
    candidates = []
    for folder in (OUTPUTS_DIR, ROOT):
        if not os.path.isdir(folder):
            continue
        for name in GENERATED_FILES:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                candidates.append(path)
    if os.path.exists(GEOJSON_PATH):
        candidates.append(GEOJSON_PATH)
    return max(candidates, key=os.path.getmtime) if candidates else None


def organize_outputs() -> list[str]:
    """Move freshly generated master files from the repo root into outputs/."""
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    moved = []
    for name in GENERATED_FILES:
        src = os.path.join(ROOT, name)
        if os.path.exists(src):
            stem, ext = os.path.splitext(name)
            dst = os.path.join(OUTPUTS_DIR, f"{stem}_{stamp}{ext}")
            shutil.move(src, dst)
            moved.append(dst)
    return moved


def run_etl() -> tuple[str | None, str]:
    """Run the unchanged ETL script, then tidy its outputs into outputs/."""
    if not os.path.exists(ETL_SCRIPT):
        return None, "extract_census.py not found."
    proc = subprocess.run(
        [sys.executable, ETL_SCRIPT],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=3600,
    )
    log = f"{proc.stdout}\n{proc.stderr}".strip()[-4000:]
    if proc.returncode != 0:
        return None, log or "ETL failed."
    moved = organize_outputs()
    source = moved[0] if moved else find_latest_source()
    return source, log or "Done."


@st.cache_data(show_spinner="Loading dataset…")
def load_path_cached(path: str, mtime: float) -> pd.DataFrame:
    return load_master_data(path)


@st.cache_data(show_spinner="Reading uploaded file…")
def load_upload_cached(name: str, data: bytes) -> pd.DataFrame:
    if name.lower().endswith(".csv"):
        return normalize_master(pd.read_csv(io.BytesIO(data)))
    return normalize_master(pd.read_excel(io.BytesIO(data)))


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def zip_paths(paths: list[str]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            zf.write(path, arcname=os.path.basename(path))
    buf.seek(0)
    return buf

# __APP_MAIN_CHUNK1__
def main() -> None:
    st.title("Delaware ZCTA Health · Sector Exporter")
    st.caption(
        "Pick a dataset, choose sectors & columns, then export clean per-sector "
        "files (or one multi-sheet workbook) without cluttering your workspace."
    )

    # ---- 1. Data source ----------------------------------------------------
    with st.sidebar:
        st.header("1 · Data source")
        uploaded = st.file_uploader("Upload Excel / CSV", type=["xlsx", "xls", "csv"])

        df: pd.DataFrame = pd.DataFrame()
        if uploaded is not None:
            try:
                df = load_upload_cached(uploaded.name, uploaded.getvalue())
                st.caption(f"Using **{uploaded.name}**")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not read upload: {exc}")
        else:
            source_path = find_latest_source()
            if source_path is None:
                st.warning("No master dataset found yet. Run the ETL pipeline.")
            else:
                df = load_path_cached(source_path, os.path.getmtime(source_path))
                st.caption(f"Loaded `{os.path.relpath(source_path, ROOT)}`")

        st.divider()
        if st.button("⚡ Run ETL & refresh", width="stretch"):
            with st.spinner("Running extract_census.py …"):
                new_source, log = run_etl()
            if new_source:
                st.success("Pipeline finished — outputs moved to outputs/.")
                st.session_state["last_etl_log"] = log
                st.rerun()
            else:
                st.error(log or "ETL failed.")
        if st.session_state.get("last_etl_log"):
            with st.expander("Last ETL log"):
                st.code(st.session_state["last_etl_log"])

        st.divider()
        if not df.empty:
            st.metric("Rows (ZCTAs)", len(df))
            st.metric("Columns", len(df.columns))

    if df.empty:
        st.info("No data to show. Run the ETL pipeline or upload an Excel/CSV file.")
        st.stop()

    # ---- 2. Sector & column selection --------------------------------------
    st.header("2 · Pick sectors & columns")
    all_sectors = list(SECTORS.keys())
    selected_sectors = st.multiselect(
        "Sectors to include",
        all_sectors,
        default=[s for s in all_sectors if s not in ("Geographic", "Calculated Metrics")],
    )

    picked_columns: list[str] = []
    if selected_sectors:
        st.markdown("#### Refine columns per sector")
        for sector in selected_sectors:
            available = [c for c in SECTORS[sector] if c in df.columns]
            if not available:
                continue
            chosen = st.multiselect(
                f"{sector} — {len(available)} columns",
                available,
                default=available,
                key=f"cols::{sector}",
            )
            picked_columns.extend(chosen)

    extra_columns = [c for c in df.columns if c not in all_sector_columns()]
    if extra_columns:
        st.markdown("#### Other columns in this dataset")
        picked_columns.extend(
            st.multiselect("Ungrouped columns", extra_columns, key="cols::extra")
        )

    if not picked_columns:
        st.info("Select at least one sector (or column) to continue.")
        st.stop()

    include_keys = st.toggle(
        "Include geographic keys (ZCTA · County_FIPS · County_Name)", value=True
    )

    # ---- 3. Preview --------------------------------------------------------
    st.header("3 · Preview")
    tables = build_sector_tables(df, picked_columns, include_keys=include_keys)
    if not tables:
        st.info("No columns matched in the current dataset.")
        st.stop()

    combined = build_combined(df, picked_columns, include_keys=include_keys)
    preview_choice = st.selectbox("Preview table", ["Combined"] + list(tables.keys()))
    preview_df = combined if preview_choice == "Combined" else tables[preview_choice]
    st.dataframe(preview_df, width="stretch", height=360)
    st.caption(
        f"{len(tables)} sector tables · {len(picked_columns)} selected columns · "
        f"{len(df)} ZCTA rows"
    )

# ---- 4. Export ---------------------------------------------------------
    st.header("4 · Export")
    fmt = st.radio(
        "Output format",
        [
            "One Excel workbook (one sheet per sector)",
            "Separate CSV files (one per sector)",
            "Separate Excel files (one per sector)",
            "One combined CSV",
            "One combined Excel",
        ],
        horizontal=True,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if st.button("💾 Export", type="primary", width="stretch"):
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        try:
            if fmt.startswith("One Excel workbook"):
                out_path = os.path.join(EXPORTS_DIR, f"DE_Health_SectorExport_{stamp}.xlsx")
                export_multi_sheet_excel(tables, out_path)
                downloads = [out_path]
            elif fmt.startswith("Separate CSV"):
                out_dir = os.path.join(EXPORTS_DIR, f"DE_Health_CSV_{stamp}")
                downloads = export_separate_files(tables, out_dir, fmt="csv")
            elif fmt.startswith("Separate Excel"):
                out_dir = os.path.join(EXPORTS_DIR, f"DE_Health_Excel_{stamp}")
                downloads = export_separate_files(tables, out_dir, fmt="xlsx")
            elif fmt == "One combined CSV":
                out_path = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.csv")
                export_combined(combined, out_path)
                downloads = [out_path]
            else:
                out_path = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.xlsx")
                export_combined(combined, out_path)
                downloads = [out_path]
        except Exception as exc:  # noqa: BLE001
            st.error(f"Export failed: {exc}")
            st.stop()

        st.success("Exported ✓")
        for path in downloads:
            rel = os.path.relpath(path, ROOT)
            with open(path, "rb") as fh:
                st.download_button(
                    f"⬇️ {rel}",
                    data=fh.read(),
                    file_name=os.path.basename(path),
                    mime=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        if path.endswith(".xlsx")
                        else "text/csv"
                    ),
                    width="stretch",
                )

        if len(downloads) > 1:
            st.download_button(
                "⬇️ Download all as ZIP",
                data=zip_paths(downloads).getvalue(),
                file_name=f"DE_Health_Exports_{stamp}.zip",
                mime="application/zip",
                width="stretch",
            )


if __name__ == "__main__":
    main()