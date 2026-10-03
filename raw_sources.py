"""Registry of the live, verifiable raw data sources behind this pipeline.

Every snapshot under ./raw is an unmodified copy of what a public publisher
served, archived together with the exact request URL, the retrieval timestamp
and a SHA-256 digest of the stored bytes.  ``raw/sources.json`` is the
machine-readable manifest written by ``fetch_raw_data.py``; this module is the
read-only accessor used by the UI and by scripts.

Nothing in ./raw is modelled, imputed, smoothed or hand-edited by this project.
That is the point: anyone can re-run ``python3 fetch_raw_data.py --verify`` and
get the same checksums back, which is what proves the figures are not
fabricated.  ``raw/SOURCES.md`` holds the human-readable citations.

Pandas-only (no Streamlit) so it can be reused from scripts/notebooks.
"""

# Keep the annotations lazy so "str | None" / "list[dict]" work on Python 3.9.
from __future__ import annotations

import json
import os

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
MANIFEST_PATH = os.path.join(RAW_DIR, "sources.json")
SOURCES_MD_PATH = os.path.join(RAW_DIR, "SOURCES.md")

# Label used for the derived ETL master in the UI dataset picker.
MASTER_LABEL = "Master \u00b7 Delaware ZCTA (derived)"

# Geography levels used by the per-column Geography_Level filter.
GEO_LEVELS = [
    "ZCTA",
    "City / place",
    "County",
    "State",
    "Derived from ZCTA-level ACS",
    "Not geographic",
]


def load_manifest() -> dict:
    """Return the parsed raw/sources.json, or a safe empty manifest."""
    if not os.path.exists(MANIFEST_PATH):
        return {"generated_utc": None, "sources": []}
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("sources", [])
    return data


def list_sources() -> list:
    """Every archived raw source, in manifest order."""
    return load_manifest()["sources"]


def get_source(source_id: str) -> dict | None:
    """Look one source up by its manifest id."""
    for source in list_sources():
        if source.get("id") == source_id:
            return source
    return None


def source_option_labels() -> dict:
    """Map the UI radio label -> source id, e.g. {"Raw \u00b7 ACS 2021...": "..."}."""
    return {f"Raw \u00b7 {src['label']}": src["id"] for src in list_sources()}


def raw_path(source: dict) -> str:
    """Absolute path of a source's archived snapshot."""
    return os.path.join(RAW_DIR, source["file"])


def load_raw_frame(source: dict):
    """Load a source's archived snapshot as a DataFrame (plain pandas read)."""
    import pandas as pd

    return pd.read_csv(raw_path(source), low_memory=False)


def citation(source: dict) -> str:
    """Markdown citation block for one raw source, shown next to that dataset."""
    lines = [
        f"**{source['publisher']}** \u2014 {source['dataset']} ({source['vintage']})",
        f"- Geography: {source['geography']} \u00b7 Access: {source['access']}",
        f"- Source URL: {source['url']}",
    ]
    if source.get("landing_page"):
        lines.append(f"- Landing page: {source['landing_page']}")
    if source.get("license"):
        lines.append(f"- License / terms: {source['license']}")
    lines.append(
        f"- Snapshot: `raw/{source['file']}` \u00b7 {source['rows']:,} rows \u00d7 "
        f"{source['columns']} columns \u00b7 retrieved {source['retrieved_utc']}"
    )
    if source.get("sha256"):
        lines.append(f"- SHA-256: `{source['sha256']}`")
    if source.get("note"):
        lines.append(f"- Note: {source['note']}")
    return "\n".join(lines)


def verify_source(source: dict, timeout: int = 60) -> tuple:
    """Confirm one source's live URL still resolves. Returns (ok, message)."""
    import requests

    try:
        resp = requests.get(source["url"], timeout=timeout, stream=True)
        if resp.status_code == 200:
            return True, f"HTTP 200 \u00b7 {resp.headers.get('Content-Length', '?')} bytes"
        return False, f"HTTP {resp.status_code}"
    except Exception as exc:  # pragma: no cover - network dependent
        return False, f"{type(exc).__name__}: {exc}"