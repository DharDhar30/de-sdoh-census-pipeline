"""Delaware ZCTA Health · Sector Export UI

Streamlit app that loads the master dataset, lets you pick and choose columns
grouped by sector (BRFSS State Level, CHR Health Outcomes / Behaviors /
Clinical Care, Demographics, Socioeconomic, Health Access, Calculated Metrics,
Geographic), previews the result, and exports as either one multi-sheet Excel
workbook or separate per-sector files.

Generated files are written to ./exports and ./outputs (both git-ignored) so
the working tree stays clean - no more spreadsheets piling up in the repo.

Run:  streamlit run app.py   (or double-click start_ui.command)
"""

# Keep the annotations lazy so "str | None" / "tuple[str | None, str]" work on
# Python 3.9 as well as 3.10+.
from __future__ import annotations

import sys

# Fail with an actionable message instead of a cryptic typing error on Python
# 3.8 and older (PEP 604 unions such as "str | None" are only evaluated by the
# interpreter when annotations are not lazy).
if sys.version_info < (3, 9):  # pragma: no cover - environment guard
    raise RuntimeError(
        "Python 3.9 or newer is required, but this environment is running "
        f"{sys.version_info.major}.{sys.version_info.minor}. "
        "Rebuild the environment with a newer python3:  rm -rf .venv && bash start_ui.sh"
    )

import io
import os
import shutil
import subprocess
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st

from exporter import (
    build_combined,
    build_sector_tables,
    export_combined,
    export_separate_files,
    load_master_data,
    normalize_master,
)
from sector_definitions import (
    SECTORS,
    all_sector_columns,
    CITY_KEY_COLUMNS,
    COUNTY_KEY_COLUMNS,
    geo_level_of,
    provenance_rows,
    source_id_of,
)
from raw_sources import (
    GEO_LEVELS,
    MASTER_LABEL,
    citation,
    list_sources,
    load_raw_frame,
    raw_path,
    source_option_labels,
    verify_source,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT, "outputs")
EXPORTS_DIR = os.path.join(ROOT, "exports")
ETL_SCRIPT = os.path.join(ROOT, "extract_census.py")
GEOJSON_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Spatial.geojson")
PLACES_CITY_PATH = os.path.join(ROOT, "PLACES_Delaware_City.csv")
PROVENANCE_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Column_Provenance.csv")
COUNTY_CHR_PATH = os.path.join(ROOT, "Delaware_County_CHR.csv")
GENERATED_FILES = [
    "Delaware_ZCTA_Health_Master_Wide.xlsx",
    "Delaware_ZCTA_Health_Master_Wide.csv",
    "Delaware_ZCTA_Health_Master_Column_Provenance.csv",
]

# Raw datasets archived by fetch_raw_data.py, plus the derived master output.
RAW_SOURCES = list_sources()
RAW_LABELS = source_option_labels()

st.set_page_config(page_title="DE Health Force", page_icon="\U0001f3e5", layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { padding: 8px 16px; font-weight: 500; }
[data-testid="stMetricValue"] { font-size: 1.4rem; }
h1 { margin-bottom: 0.2rem; }
.streamlit-expanderHeader { font-weight: 500; }
</style>""", unsafe_allow_html=True)


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


@st.cache_data(show_spinner="Loading raw snapshot…")
def load_raw_cached(source_id: str, mtime: float) -> pd.DataFrame:
    """Load an archived raw publisher snapshot exactly as stored."""
    source = next((s for s in RAW_SOURCES if s["id"] == source_id), None)
    if source is None:
        raise KeyError(f"Unknown raw source: {source_id}")
    return load_raw_frame(source)


def render_citation(source_id: str, key: str) -> None:
    """Show one dataset's citation on its own, separate from every other source."""
    source = next((s for s in RAW_SOURCES if s["id"] == source_id), None)
    if source is None:
        st.caption("Citation not available - run `python3 fetch_raw_data.py`.")
        return
    with st.expander(f"\U0001f4ce Source & citation — {source['label']}", expanded=False):
        st.markdown(citation(source))
        path = raw_path(source)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                st.download_button(
                    f"Download raw snapshot — {source['file']}",
                    data=fh.read(),
                    file_name=source["file"],
                    mime="text/csv",
                    key=f"dl_raw::{source_id}",
                )
        else:
            st.caption(
                f"`raw/{source['file']}` is not archived yet — restore it with "
                f"`python3 fetch_raw_data.py --only {source_id}`."
            )
        if st.button("Check this source is still live", key=key):
            ok, detail = verify_source(source)
            (st.success if ok else st.error)(f"{'Live' if ok else 'Unreachable'} · {detail}")


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
    st.title("\U0001f3e5 Delaware Health Force")
    st.caption("Explore & export ZCTA-level health data by sector.")

    # ---- 1. Data source ----------------------------------------------------
    with st.sidebar:
        st.markdown("### \U0001f4c2 Data Source")

        # Each raw dataset is its own entry: an unmodified publisher snapshot in
        # ./raw, cited separately. Derived datasets are processed ETL results.
        MASTER_OPTION = "Derived \u00b7 Master (Delaware ZCTA, ETL result)"
        PLACES_OPTION = "Derived \u00b7 CDC PLACES (City-Level, processed)"
        # The master now carries the PLACES *ZCTA* release, so chronic-disease
        # measures are ZCTA-level. The city-level file is still available as its
        # own dataset for city-level analysis.
        PLACES_ZCTA_OPTION = "Derived \u00b7 CDC PLACES (ZCTA-Level, processed)"
        CHR_OPTION = "Derived \u00b7 CHR (County-Level, processed)"
        options = (
            list(RAW_LABELS.keys())
            + [MASTER_OPTION, PLACES_OPTION, PLACES_ZCTA_OPTION, CHR_OPTION]
        )
        # Display label -> manifest id for the raw entries (they already carry
        # the "Raw \u00b7 " prefix from raw_sources.source_option_labels).
        label_to_source_id = {label: sid for label, sid in RAW_LABELS.items()}
        data_source = st.radio(
            "Choose dataset",
            options,
            help=(
                "Raw datasets are unmodified snapshots of public sources "
                "(see raw/SOURCES.md) - each carries its own citation. "
                "Derived datasets are cleaned/processed results of the ETL scripts."
            ),
        )

        uploaded = st.file_uploader("Upload Excel / CSV", type=["xlsx", "xls", "csv"])

        df: pd.DataFrame = pd.DataFrame()
        is_city_level = False
        is_county_level = False
        active_source_id: str | None = None
        is_master = False

        if uploaded is not None:
            try:
                df = load_upload_cached(uploaded.name, uploaded.getvalue())
                st.success(f"Using **{uploaded.name}**")
                is_city_level = "City_Name" in df.columns
                is_county_level = "County_Name" in df.columns and "ZCTA" not in df.columns
            except Exception as exc:
                st.error(f"Could not read upload: {exc}")
        elif data_source in label_to_source_id:
            active_source_id = label_to_source_id[data_source]
            source = next(s for s in RAW_SOURCES if s["id"] == active_source_id)
            path = raw_path(source)
            if os.path.exists(path):
                df = load_raw_cached(active_source_id, os.path.getmtime(path))
                is_city_level = source["geo_level"] == "City / place"
                is_county_level = source["geo_level"] == "County"
                st.success(f"Raw snapshot: {source['file']} ({source['rows']:,} rows)")
            else:
                st.warning(
                    f"`raw/{source['file']}` is missing. Restore it with "
                    f"`python3 fetch_raw_data.py --only {source['id']}`."
                )
        elif data_source == PLACES_OPTION:
            if os.path.exists(PLACES_CITY_PATH):
                df = load_path_cached(PLACES_CITY_PATH, os.path.getmtime(PLACES_CITY_PATH))
                is_city_level = True
                st.success("Loaded CDC PLACES (79 cities)")
            else:
                st.warning("PLACES_Delaware_City.csv not found. Run fetch_places.py")
        elif data_source == PLACES_ZCTA_OPTION:
            zcta_places_path = "Delaware_ZCTA_Health_Master_Wide.csv"
            if os.path.exists(zcta_places_path):
                df = load_path_cached(zcta_places_path, os.path.getmtime(zcta_places_path))
                df = df[[c for c in df.columns if c == "ZCTA" or c.startswith("PLACES_Pct_")]]
                st.success(
                    f"Loaded PLACES ZCTA-level estimates for {df['ZCTA'].nunique()} ZCTAs. "
                    "These are model-based estimates, not direct counts."
                )
            else:
                st.warning(
                    "Delaware_ZCTA_Health_Master_Wide.csv not found. Run extract_census.py"
                )
        elif data_source == CHR_OPTION:
            if os.path.exists(COUNTY_CHR_PATH):
                df = load_path_cached(COUNTY_CHR_PATH, os.path.getmtime(COUNTY_CHR_PATH))
                is_county_level = True
                st.success("Loaded CHR (3 counties)")
            else:
                st.warning("Delaware_County_CHR.csv not found. Run generate_county_chr.py")
        elif data_source == MASTER_OPTION:
            is_master = True
            source_path = find_latest_source()
            if source_path is None:
                st.warning("No master dataset found yet. Run the ETL pipeline.")
            else:
                df = load_path_cached(source_path, os.path.getmtime(source_path))
                st.success(f"Loaded `{os.path.relpath(source_path, ROOT)}`")

        st.divider()
        if not df.empty:
            if is_city_level:
                lbl = "Cities"
            elif is_county_level:
                lbl = "Counties"
            else:
                lbl = "ZCTAs" if is_master else "Rows"
            c1, c2 = st.columns(2)
            c1.metric(lbl, len(df))
            c2.metric("Columns", len(df.columns))

        # Citation for the active dataset, on its own, never mixed with others.
        if active_source_id:
            render_citation(active_source_id, key=f"cite::{active_source_id}")
        elif data_source == MASTER_OPTION:
            with st.expander("\U0001f4ce Source & citation — derived master", expanded=False):
                st.markdown(
                    "**Derived dataset** — built by `extract_census.py` from the raw sources "
                    "below (already checked into `./raw`), then transformed.\n\n"
                    "- ZCTA-level: Census ACS 2021 5-year profile + TIGER 2020 boundaries\n"
                    "- Broadcast onto ZCTA rows: CDC BRFSS 2024 (state) and County Health "
                    "Rankings 2024 (county)\n"
                    "- Added in Python: population counts and density\n\n"
                    "Per-column provenance ships with the master as "
                    "`Delaware_ZCTA_Health_Master_Column_Provenance.csv` and as the "
                    "`Column_Provenance` sheet of the master workbook."
                )
        elif data_source == PLACES_OPTION:
            with st.expander("\U0001f4ce Source & citation — processed PLACES", expanded=False):
                st.markdown(
                    "**Derived dataset** — cleaned from the raw snapshot "
                    "`raw/cdc_places_2024_de_city_raw.csv` by `fetch_places.py`. "
                    "Each measure is also directly inspectable in that raw file's own "
                    "dataset entry."
                )
        elif data_source == CHR_OPTION:
            with st.expander("\U0001f4ce Source & citation — processed CHR", expanded=False):
                st.markdown(
                    "**Derived dataset** — county table produced by "
                    "`generate_county_chr.py` from the raw CHR release "
                    "`raw/chr_2024_de_counties_raw.csv`. The unmodified workbook rows "
                    "are inspectable in that raw file's own dataset entry."
                )
            with st.expander("\U0001f4ce Source & citation — derived master", expanded=False):
                st.markdown(
                    "**Derived dataset** — built by `extract_census.py` from the raw sources "
                    "below (already checked into `./raw`), then transformed.\n\n"
                    "- ZCTA-level: Census ACS 2021 5-year profile + TIGER 2020 boundaries\n"
                    "- Broadcast onto ZCTA rows: CDC BRFSS 2024 (state) and County Health "
                    "Rankings 2024 (county)\n"
                    "- Added in Python: population counts and density\n\n"
                    "Per-column provenance ships with the master as "
                    "`Delaware_ZCTA_Health_Master_Column_Provenance.csv` and as the "
                    "`Column_Provenance` sheet of the master workbook."
                )

        with st.expander("\U0001f5c2\ufe0f All raw sources & citations", expanded=False):
            if not RAW_SOURCES:
                st.caption(
                    "No raw snapshots found. Run `python3 fetch_raw_data.py` to archive "
                    "them with citations and checksums."
                )
            else:
                archived = [s for s in RAW_SOURCES if os.path.exists(raw_path(s))]
                if archived:
                    st.caption(
                        f"{len(archived)} archived snapshot(s). Every file below is an "
                        "unmodified copy of what the publisher served — original column "
                        "names, original values, nothing edited."
                    )
                    st.download_button(
                        f"Download ALL {len(archived)} raw snapshots (ZIP)",
                        data=zip_paths([raw_path(s) for s in archived]).getvalue(),
                        file_name="DE_Raw_Sources.zip",
                        mime="application/zip",
                        key="dl_all_raw",
                    )
                for entry in RAW_SOURCES:
                    st.markdown(citation(entry))
                    path = raw_path(entry)
                    if os.path.exists(path):
                        with open(path, "rb") as fh:
                            st.download_button(
                                f"Download {entry['file']}",
                                data=fh.read(),
                                file_name=entry["file"],
                                mime="text/csv",
                                key=f"dl_list::{entry['id']}",
                            )
                    st.divider()
        st.divider()
        if st.button("\U0001f504 Run ETL & Refresh", use_container_width=True):
            with st.spinner("Running ETL..."):
                new_source, log = run_etl()
            if new_source:
                st.success("Done.")
                st.session_state["last_etl_log"] = log
                st.rerun()
            else:
                st.error(log or "ETL failed.")
        if st.session_state.get("last_etl_log"):
            with st.expander("Last ETL log"):
                st.code(st.session_state["last_etl_log"])

    if df.empty:
        st.info("👉 Pick a dataset or upload a file to get started.")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["  1 \u2502 Select Sectors  ", "  2 \u2502 Preview  ", "  3 \u2502 Export  "])
    with tab1:
        st.subheader("Choose sectors & columns")
        st.caption("Pick entire sectors or drill in to individual columns. Key columns always included.")
        all_sectors = list(SECTORS.keys())
        # The derived master hides geography keys and derived counts by default;
        # a raw snapshot is shown in full so nothing is silently filtered out.
        # Compare against MASTER_OPTION (the radio label), not MASTER_LABEL -
        # those are different strings and the mismatch silently forced every
        # dataset into the "raw" branch, breaking the master's default sectors
        # and its geography filter.
        is_master = uploaded is None and data_source == MASTER_OPTION
        default_sectors = (
            [s for s in all_sectors if s not in ("Geographic", "Calculated Metrics")]
            if is_master
            else all_sectors
        )
        selected_sectors = st.multiselect("Sectors to include", all_sectors, default=default_sectors)

        geo_filter = st.multiselect(
            "Filter measures by the geography they were actually collected at",
            GEO_LEVELS,
            default=[],
            help=(
                "Only Census ACS and the TIGER boundaries are genuinely ZCTA-level here. "
                "CDC BRFSS is a statewide survey and County Health Rankings reports by "
                "county, so those figures repeat across every ZCTA in the state or county. "
                "Leave empty to include everything."
            ),
        )
        picked_columns: list[str] = []
        if selected_sectors:
            st.write("")
            for sector in selected_sectors:
                available = [c for c in SECTORS[sector] if c in df.columns]
                if geo_filter:
                    available = [c for c in available if geo_level_of(c) in geo_filter]
                if not available:
                    continue
                with st.expander(f"{sector} ({len(available)} columns)", expanded=False):
                    chosen = st.multiselect(
                        "Columns", available, default=available,
                        key=f"cols::{sector}", label_visibility="collapsed",
                    )
                    picked_columns.extend(chosen)
        extra_columns = [c for c in df.columns if c not in all_sector_columns()]
        # Only the derived master has per-column provenance to filter on; a raw
        # publisher snapshot is one dataset, so its geography is shown in the
        # citation instead.
        if geo_filter and is_master:
            extra_columns = [c for c in extra_columns if geo_level_of(c) in geo_filter]
        if extra_columns:
            with st.expander(f"Other columns ({len(extra_columns)})", expanded=False):
                picked_columns.extend(st.multiselect("Ungrouped", extra_columns, key="cols::extra"))
        if not picked_columns:
            # A raw publisher snapshot (or an upload) uses the publisher's own
            # column names, so no sector ever matches and every column lands in
            # "Other columns" - which defaulted to *nothing* selected. That left
            # picked_columns empty and st.stop() killed the Preview and Export
            # tabs entirely, making the raw data impossible to preview or
            # download. Fall back to offering every column in the file.
            st.warning(
                "None of this dataset's columns match the master sector definitions "
                "(raw publisher snapshots keep the publisher's own column names). "
                "Showing every column instead."
            )
            picked_columns = list(df.columns)
        if is_city_level:
            include_keys = st.toggle("Include city keys", value=True)
        elif is_county_level:
            include_keys = st.toggle("Include county keys", value=True)
        else:
            include_keys = st.toggle("Include geographic keys (ZCTA \u00b7 County_FIPS \u00b7 County_Name)", value=True)

    with tab2:
        tables = build_sector_tables(
            df,
            picked_columns,
            include_keys=include_keys,
            fallback_label=None if is_master else f"All columns \u00b7 {data_source}",
        )
        if not tables:
            st.info("No columns matched.")
            st.stop()
        combined = build_combined(df, picked_columns, include_keys=include_keys)
        st.subheader("Data Preview")
        preview_choice = st.selectbox("View table", ["Combined"] + list(tables.keys()))
        preview_df = combined if preview_choice == "Combined" else tables[preview_choice]
        st.dataframe(preview_df, use_container_width=True, height=420)
        st.caption(f"{len(tables)} sector tables \u00b7 {len(picked_columns)} columns \u00b7 {len(df)} rows")

    with tab3:
        st.subheader("Export Options")
        st.caption("Export your selection as Excel, CSV, or a ZIP archive.")
        fmt = st.radio("Output format", ["One Excel workbook", "Separate CSVs", "Separate Excel files", "One combined CSV", "One combined Excel"], horizontal=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if st.button("\U0001f4e6 Export Data", type="primary", use_container_width=True):
            os.makedirs(EXPORTS_DIR, exist_ok=True)
            try:
                if fmt.startswith("One Excel workbook") or fmt.startswith("Separate Excel"):
                    # Raw publisher columns belong to no sector, so sector tables
                    # would silently drop them. This export mirrors the preview:
                    # the "Data" sheet is the whole working selection, plus one
                    # sheet per non-empty sector and a provenance dictionary.
                    prov = build_provenance_frame(list(combined.columns), is_master, active_source_id)
                    out_path = os.path.join(EXPORTS_DIR, f"DE_Health_Export_{stamp}.xlsx")
                    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
                        combined.to_excel(writer, sheet_name="Data", index=False)
                        for sheet, table in tables.items():
                            safe = "".join(
                                "_" if ch in "[]:*?/\\" else ch for ch in sheet
                            )[:31].strip() or "Sheet"
                            table.to_excel(writer, sheet_name=safe, index=False)
                        prov.to_excel(writer, sheet_name="Data_Dictionary", index=False)
                    downloads = [out_path]
                elif fmt.startswith("Separate CSV"):
                    out_dir = os.path.join(EXPORTS_DIR, f"DE_Health_CSV_{stamp}"); downloads = export_separate_files(tables, out_dir, fmt="csv")
                    # Always ship the data dictionary/file manifest alongside raw
                    # sector files so the provenance travels with the numbers.
                    downloads += _write_provenance_sidecar(out_dir, list(combined.columns), is_master, active_source_id)
                elif fmt.startswith("Separate Excel"):
                    out_dir = os.path.join(EXPORTS_DIR, f"DE_Health_Excel_{stamp}"); downloads = export_separate_files(tables, out_dir, fmt="xlsx")
                    downloads += _write_provenance_sidecar(out_dir, list(combined.columns), is_master, active_source_id)
                elif fmt == "One combined CSV":
                    out_path = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.csv"); export_combined(combined, out_path); downloads = [out_path]
                else:
                    out_path = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.xlsx"); export_combined(combined, out_path); downloads = [out_path]
            except Exception as exc:
                st.error(f"Export failed: {exc}"); st.stop()
            st.success("Export completed.")
            for path in downloads:
                rel = os.path.relpath(path, ROOT)
                with open(path, "rb") as fh:
                    st.download_button(f"Download: {rel}", data=fh.read(), file_name=os.path.basename(path), use_container_width=True)
            if len(downloads) > 1:
                st.download_button("Download all as ZIP", data=zip_paths(downloads).getvalue(), file_name=f"DE_Health_Exports_{stamp}.zip", mime="application/zip", use_container_width=True)

def build_provenance_frame(columns: list[str], is_master: bool, active_source_id: str | None) -> pd.DataFrame:
    """Per-column provenance for whatever is currently selected.

    For the derived master every column is resolved against SECTORS, so each
    measure carries its own source id and true collection geography. For a raw
    publisher snapshot (or an upload) there is nothing to resolve - the whole
    file has one source - so the source is recorded once per column.
    """
    if is_master:
        return pd.DataFrame(provenance_rows(list(columns)))
    prov_source = (
        next((s for s in RAW_SOURCES if s["id"] == active_source_id), None)
        if active_source_id
        else None
    )
    return pd.DataFrame(
        {
            "Column": list(columns),
            "Source": prov_source["label"] if prov_source else "uploaded file",
            "Source_ID": active_source_id or "",
            "Geography_Level": prov_source["geo_level"] if prov_source else "unknown",
            "Calculated": "no",
        }
    )


def _write_provenance_sidecar(
    out_dir: str, columns: list[str], is_master: bool, active_source_id: str | None
) -> list:
    """Write the data dictionary next to a set of exported sector files."""
    os.makedirs(out_dir, exist_ok=True)
    prov = build_provenance_frame(columns, is_master, active_source_id)
    path = os.path.join(out_dir, "00_Data_Dictionary.csv")
    prov.to_csv(path, index=False)
    return [path]


if __name__ == "__main__":
    main()
