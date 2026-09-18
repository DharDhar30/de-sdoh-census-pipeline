"""Delaware Health Force - data source selection and sector export UI.

Two jobs in one Streamlit app:

1. Build Master: merge any subset of the project's data sources at a chosen
   geography level into a single flat table, then export it in the layout that
   is easiest to bring into Tableau (stable filenames, WGS84 MultiPolygon
   GeoJSON, and a field manifest that documents every column).
2. Sector Export: pick columns grouped by sector (BRFSS State Level, CHR Health
   Outcomes / Behaviors / Clinical Care, Demographics, Socioeconomic, Health
   Access, Calculated Metrics, Geographic), preview the result, and export as
   one multi-sheet Excel workbook or as separate per-sector files.

Generated files are written to ./exports, ./outputs and ./tableau_exports (all
git-ignored) so the working tree stays clean.

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
from data_sources import (
    LEVELS,
    default_sources_for_level,
    sources_for_level,
    sources_requiring_network,
)
from master_builder import (
    build_master,
    missing_source_files,
    validate_selection,
    write_tableau_bundle,
)
from sector_definitions import SECTORS, all_sector_columns, TRACT_KEY_COLUMNS

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT, "outputs")
EXPORTS_DIR = os.path.join(ROOT, "exports")
TABLEAU_DIR = os.path.join(ROOT, "tableau_exports")
ETL_SCRIPT = os.path.join(ROOT, "extract_census.py")
GEOJSON_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Spatial.geojson")
PLACES_CITY_PATH = os.path.join(ROOT, "PLACES_Delaware_City.csv")
PLACES_TRACT_PATH = os.path.join(ROOT, "data/census_tract/Delaware_CensusTract_PLACES.csv")
COUNTY_CHR_PATH = os.path.join(ROOT, "Delaware_County_CHR.csv")
GENERATED_FILES = [
    "Delaware_ZCTA_Health_Master_Wide.xlsx",
    "Delaware_ZCTA_Health_Master_Wide.csv",
]

st.set_page_config(
    page_title="DE Health Force",
    layout="wide",
    initial_sidebar_state="expanded",
)

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


@st.cache_data(show_spinner="Loading dataset...")
def load_path_cached(path: str, mtime: float) -> pd.DataFrame:
    return load_master_data(path)


@st.cache_data(show_spinner="Reading uploaded file...")
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

# ---------------------------------------------------------------------------
# Master builder UI
# ---------------------------------------------------------------------------
def detect_level(df: pd.DataFrame) -> str:
    """Which geography a frame is keyed on. Drives the key-column handling."""
    if "CensusTractFIPS" in df.columns:
        return "tract"
    if "City_Name" in df.columns:
        return "city"
    if "County_Name" in df.columns and "ZCTA" not in df.columns:
        return "county"
    if "ZCTA" in df.columns:
        return "zcta"
    return "other"


KEY_TOGGLE_LABELS = {
    "tract": "Include tract keys (CensusTractFIPS, County)",
    "city": "Include city keys (City_Name, State)",
    "county": "Include county keys (County_Name, County_FIPS)",
    "zcta": "Include geographic keys (ZIP, ZCTA, County_FIPS, County_Name)",
    "other": "Include key columns",
}


def render_source_picker(level: str) -> list[str]:
    """One checkbox per source available at `level`; returns the selected keys."""
    available = sources_for_level(level)
    defaults = set(default_sources_for_level(level))
    selected: list[str] = []

    for source in available:
        join_key = source.join_key(level)
        join_text = (
            "copied onto every row (statewide)" if join_key is None else f"joined on {join_key}"
        )
        tag = " (derived)" if source.derived else ""
        checked = st.checkbox(
            f"{source.label}{tag}",
            value=source.key in defaults,
            key=f"mb::source::{level}::{source.key}",
            help=source.note,
        )
        st.caption(f"Key: {source.key} | {join_text}")
        if checked:
            selected.append(source.key)
    return selected


def render_master_builder() -> None:
    """Tab 1: pick a level and sources, then build and export the master."""
    st.subheader("Build a master dataset")
    st.caption(
        "Choose a geography level, then choose which sources take part. The build produces a "
        "single flat table written to a stable filename, so a Tableau live connection keeps "
        "working after every rebuild."
    )

    level = st.radio(
        "Geography level",
        list(LEVELS),
        format_func=lambda key: LEVELS[key]["label"],
        horizontal=True,
        key="mb::level",
    )
    st.caption(
        "Sources are offered only at levels where their join key exists. Tract and city data "
        "cannot be keyed to ZCTAs, so each level builds its own master."
    )

    selected = render_source_picker(level)

    supports_geometry = LEVELS[level]["supports_geometry"]
    controls = st.columns(2)
    geometry = controls[0].toggle(
        "Write spatial GeoJSON (Tableau spatial file)",
        value=supports_geometry,
        disabled=not supports_geometry,
        key="mb::geometry",
    )
    raw_columns = controls[1].toggle(
        "Keep raw source columns (GEOID, LSAD, ...)",
        value=False,
        key="mb::raw-columns",
    )

    problems, warnings = validate_selection(level, selected, geometry=geometry)
    for problem in problems:
        st.error(problem)
    for warning in warnings:
        st.warning(warning)
    for key, path in missing_source_files(selected):
        st.error(f"Missing file for {key}: {path}")

    network_sources = sources_requiring_network(selected)
    if network_sources:
        st.info(
            "Downloads from the internet during the build: "
            + ", ".join(source.label for source in network_sources)
        )

    if st.button(
        "Build master",
        type="primary",
        use_container_width=True,
        disabled=bool(problems),
    ):
        try:
            with st.spinner("Merging selected sources..."):
                frame, report = build_master(
                    level, selected, geometry=geometry, raw_columns=raw_columns
                )
        except Exception as exc:
            st.error(f"Build failed: {exc}")
        else:
            st.session_state["working_master"] = frame
            st.session_state["working_report"] = report
            st.session_state["working_level"] = level
            st.session_state["working_raw_columns"] = raw_columns
            st.session_state["working_source_label"] = (
                f"Master builder - {LEVELS[level]['label']} from {', '.join(selected)}"
            )
            st.session_state.pop("bundle_files", None)
            st.rerun()

    render_master_result()


def render_master_result() -> None:
    """Diagnostics and Tableau export for the master built in this session."""
    report = st.session_state.get("working_report")
    frame = st.session_state.get("working_master")
    if report is None or frame is None:
        st.info(
            "No master built in this session yet. Until you build one, the Select Sectors, "
            "Preview and Export tabs use whichever dataset the sidebar is showing."
        )
        return

    level = st.session_state.get("working_level", report.level)
    st.divider()
    st.subheader("Build result")

    metrics = st.columns(4)
    metrics[0].metric("Rows", report.rows)
    metrics[1].metric("Columns", report.columns)
    metrics[2].metric("Level", LEVELS[level]["label"])
    metrics[3].metric("Base source", report.base_source or "none")

    st.markdown("**Join diagnostics**")
    st.dataframe(report.to_frame(), use_container_width=True, hide_index=True)

    for warning in report.warnings:
        st.warning(warning)

    with st.expander(f"Column provenance ({len(report.source_of_column)} columns)", expanded=False):
        st.dataframe(report.manifest(), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Export for Tableau")
    st.caption(
        "Writes DE_Health_<LEVEL>_Master.csv, .xlsx, .geojson (when a boundary source is "
        "selected) and _Field_Manifest.csv to ./tableau_exports. Filenames are stable, so point "
        "Tableau at the file once and the connection survives a rebuild. Timestamped copies are "
        "archived to ./outputs."
    )
    if st.button("Write Tableau files", use_container_width=True):
        try:
            written = write_tableau_bundle(
                frame,
                level,
                TABLEAU_DIR,
                report=report,
                raw_columns=st.session_state.get("working_raw_columns", False),
                archive_dir=OUTPUTS_DIR,
            )
        except Exception as exc:
            st.error(f"Export failed: {exc}")
        else:
            st.session_state["bundle_files"] = written
            st.success("Files written.")

    for kind, path in (st.session_state.get("bundle_files") or {}).items():
        rel = os.path.relpath(path, ROOT)
        with open(path, "rb") as handle:
            st.download_button(
                f"Download {kind.upper()}: {rel}",
                data=handle.read(),
                file_name=os.path.basename(path),
                key=f"dl::bundle::{kind}",
                use_container_width=True,
            )


def render_sidebar() -> tuple[pd.DataFrame, str]:
    """Sidebar dataset browser. Returns (frame, label) for the working dataset."""
    with st.sidebar:
        st.markdown("### Browse a dataset")
        st.caption("Used as the working dataset when no master has been built in tab 1.")

        data_source = st.radio(
            "Choose dataset",
            [
                "ZCTA Master (ETL)",
                "CDC PLACES (Census Tract)",
                "CDC PLACES (City-Level)",
                "CHR (County-Level)",
            ],
            help=(
                "ZCTA Master: ZCTA-level ACS/BRFSS/CHR data\n"
                "CDC PLACES Census Tract: Tract-level health data (257 tracts)\n"
                "CDC PLACES City-Level: City-level health data (79 cities)\n"
                "CHR: County-level health rankings (3 counties)"
            ),
        )

        uploaded = st.file_uploader("Upload Excel / CSV", type=["xlsx", "xls", "csv"])

        df: pd.DataFrame = pd.DataFrame()
        label = ""

        if uploaded is not None:
            try:
                df = load_upload_cached(uploaded.name, uploaded.getvalue())
                st.success(f"Using **{uploaded.name}**")
                label = f"Uploaded file: {uploaded.name}"
            except Exception as exc:
                st.error(f"Could not read upload: {exc}")
        elif data_source == "CDC PLACES (Census Tract)":
            if os.path.exists(PLACES_TRACT_PATH):
                df = load_path_cached(PLACES_TRACT_PATH, os.path.getmtime(PLACES_TRACT_PATH))
                label = "CDC PLACES (Census Tract)"
                st.success("Loaded CDC PLACES Census Tract (257 tracts)")
            else:
                st.warning("Census tract data not found.")
        elif data_source == "CDC PLACES (City-Level)":
            if os.path.exists(PLACES_CITY_PATH):
                df = load_path_cached(PLACES_CITY_PATH, os.path.getmtime(PLACES_CITY_PATH))
                label = "CDC PLACES (City-Level)"
                st.success("Loaded CDC PLACES (79 cities)")
            else:
                st.warning("PLACES_Delaware_City.csv not found. Run fetch_places.py")
        elif data_source == "CHR (County-Level)":
            if os.path.exists(COUNTY_CHR_PATH):
                df = load_path_cached(COUNTY_CHR_PATH, os.path.getmtime(COUNTY_CHR_PATH))
                label = "CHR (County-Level)"
                st.success("Loaded CHR (3 counties)")
            else:
                st.warning("Delaware_County_CHR.csv not found. Run generate_county_chr.py")
        else:
            source_path = find_latest_source()
            if source_path is None:
                st.warning("No master dataset found yet. Run the ETL pipeline.")
            else:
                df = load_path_cached(source_path, os.path.getmtime(source_path))
                label = f"Latest master file: {os.path.relpath(source_path, ROOT)}"
                st.success(f"Loaded `{os.path.relpath(source_path, ROOT)}`")

        st.divider()
        if not df.empty:
            row_noun = {
                "tract": "Tracts",
                "city": "Cities",
                "county": "Counties",
                "zcta": "ZCTAs",
            }.get(detect_level(df), "Rows")
            c1, c2 = st.columns(2)
            c1.metric(row_noun, len(df))
            c2.metric("Columns", len(df.columns))
        st.divider()
        st.markdown("### Rebuild everything")
        st.caption(
            "Runs extract_census.py, which rebuilds the full ZCTA master from every source and "
            "rewrites the canonical files in the repo root."
        )
        if st.button("Rebuild full master (all sources)", use_container_width=True):
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

    return df, label


def active_dataset(browsed: pd.DataFrame, browsed_label: str) -> tuple[pd.DataFrame, str]:
    """Prefer the master built in tab 1; otherwise fall back to the sidebar dataset."""
    built = st.session_state.get("working_master")
    if built is not None and not built.empty:
        return built, st.session_state.get("working_source_label", "Master builder result")
    return browsed, browsed_label


def main() -> None:
    st.title("Delaware Health Force")
    st.caption("Choose which data sources go into the master, then export it for Tableau.")

    browsed, browsed_label = render_sidebar()
    df, source_label = active_dataset(browsed, browsed_label)

    tabs = st.tabs(
        [
            "  1 - Build Master  ",
            "  2 - Select Sectors  ",
            "  3 - Preview  ",
            "  4 - Export  ",
        ]
    )
    with tabs[0]:
        render_master_builder()

    if df.empty:
        st.info("Build a master in tab 1, or pick a dataset or upload a file in the sidebar.")
        st.stop()

    level = detect_level(df)
    st.caption(
        f"Working dataset: {source_label} | {len(df)} rows | {len(df.columns)} columns"
    )

    with tabs[1]:
        render_sector_selection(df, level)
    with tabs[2]:
        render_preview(df)
    with tabs[3]:
        render_export(df)


def render_sector_selection(df: pd.DataFrame, level: str) -> None:
    """Tab 2: pick sectors and columns, then store the selection for tabs 3 and 4."""
    st.subheader("Choose sectors and columns")
    st.caption("Pick whole sectors or drill in to individual columns. Key columns stay included.")

    all_sectors = list(SECTORS.keys())
    selected_sectors = st.multiselect(
        "Sectors to include",
        all_sectors,
        default=[s for s in all_sectors if s not in ("Geographic", "Calculated Metrics")],
    )

    picked_columns: list[str] = []
    if selected_sectors:
        st.write("")
        for sector in selected_sectors:
            available = [c for c in SECTORS[sector] if c in df.columns]
            if not available:
                continue
            with st.expander(f"{sector} ({len(available)} columns)", expanded=False):
                chosen = st.multiselect(
                    "Columns",
                    available,
                    default=available,
                    key=f"cols::{sector}",
                    label_visibility="collapsed",
                )
                picked_columns.extend(chosen)

    extra_columns = [c for c in df.columns if c not in all_sector_columns()]
    if extra_columns:
        with st.expander(f"Other columns ({len(extra_columns)})", expanded=False):
            picked_columns.extend(st.multiselect("Ungrouped", extra_columns, key="cols::extra"))

    if not picked_columns:
        st.info("Select at least one sector.")

    include_keys = st.toggle(
        KEY_TOGGLE_LABELS.get(level, "Include key columns"),
        value=True,
        key="sel::include_keys",
    )

    st.session_state["picked_columns"] = picked_columns
    st.session_state["include_keys"] = include_keys

def render_preview(df: pd.DataFrame) -> None:
    """Tab 3: preview the selected sectors."""
    picked_columns = st.session_state.get("picked_columns", [])
    include_keys = st.session_state.get("include_keys", True)
    if not picked_columns:
        st.info("Select at least one sector in the Select Sectors tab.")
        return

    tables = build_sector_tables(df, picked_columns, include_keys=include_keys)
    if not tables:
        st.info("No columns matched.")
        return

    combined = build_combined(df, picked_columns, include_keys=include_keys)
    st.subheader("Data Preview")
    preview_choice = st.selectbox("View table", ["Combined"] + list(tables.keys()))
    preview_df = combined if preview_choice == "Combined" else tables[preview_choice]
    st.dataframe(preview_df, use_container_width=True, height=420)
    st.caption(f"{len(tables)} sector tables | {len(picked_columns)} columns | {len(df)} rows")

def render_export(df: pd.DataFrame) -> None:
    """Tab 4: export the selected sectors using the existing export engine."""
    picked_columns = st.session_state.get("picked_columns", [])
    include_keys = st.session_state.get("include_keys", True)
    if not picked_columns:
        st.info("Select at least one sector in the Select Sectors tab.")
        return

    tables = build_sector_tables(df, picked_columns, include_keys=include_keys)
    if not tables:
        st.info("No columns matched.")
        return
    combined = build_combined(df, picked_columns, include_keys=include_keys)

    st.subheader("Export Options")
    st.caption("For Tableau, tab 1 writes the flat master. These exports are for people or splits.")
    fmt = st.radio(
        "Output format",
        [
            "One Excel workbook",
            "Separate CSVs",
            "Separate Excel files",
            "One combined CSV",
            "One combined Excel",
        ],
        horizontal=True,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if st.button("Export Data", type="primary", use_container_width=True):
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
        except Exception as exc:
            st.error(f"Export failed: {exc}")
            return

        st.success("Export completed.")
        for path in downloads:
            rel = os.path.relpath(path, ROOT)
            with open(path, "rb") as fh:
                st.download_button(
                    f"Download: {rel}",
                    data=fh.read(),
                    file_name=os.path.basename(path),
                    use_container_width=True,
                )
        if len(downloads) > 1:
            st.download_button(
                "Download all as ZIP",
                data=zip_paths(downloads).getvalue(),
                file_name=f"DE_Health_Exports_{stamp}.zip",
                mime="application/zip",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
