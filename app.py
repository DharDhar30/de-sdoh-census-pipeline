"""Delaware ZCTA Health Sector Export UI."""

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

st.set_page_config(page_title="DE Health Force", page_icon="🏥", layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { padding: 8px 16px; font-weight: 500; }
[data-testid="stMetricValue"] { font-size: 1.4rem; }
h1 { margin-bottom: 0.2rem; }
.streamlit-expanderHeader { font-weight: 500; }
</style>""", unsafe_allow_html=True)

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT, "outputs")
EXPORTS_DIR = os.path.join(ROOT, "exports")
ETL_SCRIPT = os.path.join(ROOT, "extract_census.py")
GEOJSON_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Spatial.geojson")
PLACES_CITY_PATH = os.path.join(ROOT, "PLACES_Delaware_City.csv")
COUNTY_CHR_PATH = os.path.join(ROOT, "Delaware_County_CHR.csv")
GENERATED_FILES = ["Delaware_ZCTA_Health_Master_Wide.xlsx", "Delaware_ZCTA_Health_Master_Wide.csv"]


def find_latest_source():
    candidates = []
    for folder in (OUTPUTS_DIR, ROOT):
        if not os.path.isdir(folder): continue
        for name in GENERATED_FILES:
            path = os.path.join(folder, name)
            if os.path.exists(path): candidates.append(path)
    if os.path.exists(GEOJSON_PATH): candidates.append(GEOJSON_PATH)
    return max(candidates, key=os.path.getmtime) if candidates else None


def organize_outputs():
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


def run_etl():
    if not os.path.exists(ETL_SCRIPT): return None, "extract_census.py not found."
    proc = subprocess.run([sys.executable, ETL_SCRIPT], capture_output=True, text=True, cwd=ROOT, timeout=3600)
    log = f"{proc.stdout}\n{proc.stderr}".strip()[-4000:]
    if proc.returncode != 0: return None, log or "ETL failed."
    moved = organize_outputs()
    source = moved[0] if moved else find_latest_source()
    return source, log or "Done."


@st.cache_data(show_spinner="Loading dataset")
def load_path_cached(path, mtime):
    return load_master_data(path)


@st.cache_data(show_spinner="Reading uploaded file")
def load_upload_cached(name, data):
    if name.lower().endswith(".csv"): return normalize_master(pd.read_csv(io.BytesIO(data)))
    return normalize_master(pd.read_excel(io.BytesIO(data)))


def zip_paths(paths):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths: zf.write(path, arcname=os.path.basename(path))
    buf.seek(0)
    return buf


def main():
    st.title("🏥 Delaware Health Force")
    st.caption("Explore & export ZCTA-level health data by sector.")

    with st.sidebar:
        st.markdown("### 📂 Data Source")
        data_source = st.radio("Choose dataset", ["ZCTA Master (ETL)", "CDC PLACES (City-Level)", "CHR (County-Level)"])
        uploaded = st.file_uploader("Or upload Excel / CSV", type=["xlsx", "xls", "csv"])
        df = pd.DataFrame()
        is_city_level = False
        is_county_level = False

        if uploaded is not None:
            try:
                df = load_upload_cached(uploaded.name, uploaded.getvalue())
                st.success(f"Using **{uploaded.name}**")
                is_city_level = "City_Name" in df.columns
                is_county_level = "County_Name" in df.columns and "ZCTA" not in df.columns
            except Exception as exc: st.error(f"Could not read upload: {exc}")
        elif data_source == "CDC PLACES (City-Level)":
            if os.path.exists(PLACES_CITY_PATH):
                df = load_path_cached(PLACES_CITY_PATH, os.path.getmtime(PLACES_CITY_PATH))
                is_city_level = True
                st.success("Loaded CDC PLACES (79 cities)")
            else: st.warning("Run fetch_places.py")
        elif data_source == "CHR (County-Level)":
            if os.path.exists(COUNTY_CHR_PATH):
                df = load_path_cached(COUNTY_CHR_PATH, os.path.getmtime(COUNTY_CHR_PATH))
                is_county_level = True
                st.success("Loaded CHR (3 counties)")
            else: st.warning("Run generate_county_chr.py")
        else:
            source_path = find_latest_source()
            if source_path is None: st.warning("No master dataset found. Run ETL below.")
            else:
                df = load_path_cached(source_path, os.path.getmtime(source_path))
                st.success(f"Loaded `{os.path.relpath(source_path, ROOT)}`")

        st.divider()
        if not df.empty:
            lbl = "Cities" if is_city_level else "Counties" if is_county_level else "ZCTAs"
            c1, c2 = st.columns(2)
            c1.metric(lbl, len(df))
            c2.metric("Columns", len(df.columns))
        st.divider()
        if st.button("🔄 Run ETL & Refresh", use_container_width=True):
            with st.spinner("Running ETL..."): new_source, log = run_etl()
            if new_source: st.success("Done."); st.session_state["last_etl_log"] = log; st.rerun()
            else: st.error(log or "ETL failed.")
        if st.session_state.get("last_etl_log"):
            with st.expander("Last ETL log"): st.code(st.session_state["last_etl_log"])

    if df.empty:
        st.info("Pick a dataset or upload a file to get started.")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["  1 │ Select Sectors  ", "  2 │ Preview  ", "  3 │ Export  "])

    return load_master_data(path)


@st.cache_data(show_spinner="Reading uploaded file")
def load_upload_cached(name, data):
    if name.lower().endswith(".csv"): return normalize_master(pd.read_csv(io.BytesIO(data)))
    return normalize_master(pd.read_excel(io.BytesIO(data)))

    with tab1:
        st.subheader("Choose sectors & columns")
        st.caption("Pick entire sectors or drill in to individual columns. Key columns always included.")
        all_sectors = list(SECTORS.keys())
        selected_sectors = st.multiselect("Sectors to include", all_sectors, default=[s for s in all_sectors if s not in ("Geographic", "Calculated Metrics")])
        picked_columns = []
        if selected_sectors:
            st.write("")
            for sector in selected_sectors:
                available = [c for c in SECTORS[sector] if c in df.columns]
                if not available: continue
                with st.expander(f"{sector} ({len(available)} columns)", expanded=False):
                    chosen = st.multiselect("Columns", available, default=available, key=f"cols::{sector}", label_visibility="collapsed")
                    picked_columns.extend(chosen)
        extra_columns = [c for c in df.columns if c not in all_sector_columns()]
        if extra_columns:
            with st.expander(f"Other columns ({len(extra_columns)})", expanded=False):
                picked_columns.extend(st.multiselect("Ungrouped", extra_columns, key="cols::extra"))
        if not picked_columns: st.info("Select at least one sector."); st.stop()
        if is_city_level: include_keys = st.toggle("Include city keys", value=True)
        elif is_county_level: include_keys = st.toggle("Include county keys", value=True)
        else: include_keys = st.toggle("Include geographic keys (ZCTA · County_FIPS · County_Name)", value=True)

    with tab2:
        tables = build_sector_tables(df, picked_columns, include_keys=include_keys)
        if not tables: st.info("No columns matched."); st.stop()
        combined = build_combined(df, picked_columns, include_keys=include_keys)
        st.subheader("Data Preview")
        preview_choice = st.selectbox("View table", ["Combined"] + list(tables.keys()))
        preview_df = combined if preview_choice == "Combined" else tables[preview_choice]
        st.dataframe(preview_df, use_container_width=True, height=420)
        st.caption(f"{len(tables)} sector tables · {len(picked_columns)} columns · {len(df)} rows")

    with tab3:
        st.subheader("Export Options")
        fmt = st.radio("Output format", ["One Excel workbook", "Separate CSVs", "Separate Excel files", "One combined CSV", "One combined Excel"], horizontal=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if st.button("📦 Export Data", type="primary", use_container_width=True):
            os.makedirs(EXPORTS_DIR, exist_ok=True)
            try:
                if fmt.startswith("One Excel workbook"):
                    out = os.path.join(EXPORTS_DIR, f"DE_Health_SectorExport_{stamp}.xlsx"); export_multi_sheet_excel(tables, out); downloads = [out]
                elif fmt.startswith("Separate CSV"):
                    d = os.path.join(EXPORTS_DIR, f"DE_Health_CSV_{stamp}"); downloads = export_separate_files(tables, d, fmt="csv")
                elif fmt.startswith("Separate Excel"):
                    d = os.path.join(EXPORTS_DIR, f"DE_Health_Excel_{stamp}"); downloads = export_separate_files(tables, d, fmt="xlsx")
                elif fmt == "One combined CSV":
                    out = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.csv"); export_combined(combined, out); downloads = [out]
                else:
                    out = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.xlsx"); export_combined(combined, out); downloads = [out]
            except Exception as exc: st.error(f"Export failed: {exc}"); st.stop()
            st.success("Export completed.")
            for path in downloads:
                with open(path, "rb") as fh: st.download_button(f"Download: {os.path.basename(path)}", data=fh.read(), file_name=os.path.basename(path), use_container_width=True)
            if len(downloads) > 1: st.download_button("Download all as ZIP", data=zip_paths(downloads).getvalue(), file_name=f"DE_Health_Exports_{stamp}.zip", mime="application/zip", use_container_width=True)


if __name__ == "__main__":
    main()
