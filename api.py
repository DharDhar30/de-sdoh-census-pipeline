import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
import subprocess
import sys
from datetime import datetime
import shutil
import zipfile

from exporter import (
    load_master_data,
    build_sector_tables,
    build_combined,
    export_multi_sheet_excel,
    export_separate_files,
    export_combined,
)
from sector_definitions import SECTORS, all_sector_columns

app = Flask(__name__)
CORS(app)

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(ROOT, "outputs")
EXPORTS_DIR = os.path.join(ROOT, "exports")
ETL_SCRIPT = os.path.join(ROOT, "extract_census.py")
GEOJSON_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Spatial.geojson")
GENERATED_FILES = [
    "Delaware_ZCTA_Health_Master_Wide.xlsx",
    "Delaware_ZCTA_Health_Master_Wide.csv",
]

def find_latest_source() -> str | None:
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


def resolve_columns(df: pd.DataFrame, payload: dict) -> list[str]:
    """Turn the UI selection payload into the list of picked columns.

    Two payload shapes are supported:
      - sector_columns: {"Sector Name": [cols...], "__extra__": [cols...]}
         mirrors the Streamlit "Refine columns per sector" workflow.
      - sectors: ["Sector Name", ...]  (legacy: all columns of each sector)
    """
    sector_columns = payload.get("sector_columns") or {}
    if sector_columns:
        picked = []
        for sector_name, cols in sector_columns.items():
            if sector_name == "__extra__":
                picked.extend(cols)
            elif sector_name in SECTORS:
                picked.extend(cols)
        return picked
    selected_sectors = payload.get("sectors") or list(SECTORS.keys())
    picked = []
    for sector in selected_sectors:
        if sector in SECTORS:
            available = [c for c in SECTORS[sector] if c in df.columns]
            picked.extend(available)
    return picked


@app.route("/api/status", methods=["GET"])
def api_status():
    source = find_latest_source()
    df = pd.DataFrame()
    if source and os.path.exists(source):
        try:
            df = load_master_data(source)
        except Exception:
            pass
    return jsonify({
        "status": "online",
        "source": os.path.relpath(source, ROOT) if source else None,
        "rows": len(df),
        "columns": len(df.columns) if not df.empty else 0,
        "sectors": list(SECTORS.keys())
    })


@app.route("/api/schema", methods=["GET"])
def api_schema():
    """Per-sector columns available in the active dataset (mirrors Streamlit)."""
    source = find_latest_source()
    if not source:
        return jsonify({"error": "No master dataset found."}), 404
    df = load_master_data(source)
    sectors = []
    for name, cols in SECTORS.items():
        available = [c for c in cols if c in df.columns]
        if available:
            sectors.append({"name": name, "columns": available})
    extra = [c for c in df.columns if c not in all_sector_columns()]
    return jsonify({
        "status": "online",
        "source": os.path.relpath(source, ROOT) if source else None,
        "rows": len(df),
        "columns": len(df.columns),
        "sectors": sectors,
        "extra_columns": extra,
    })


@app.route("/api/run-etl", methods=["POST"])
def api_run_etl():
    if not os.path.exists(ETL_SCRIPT):
        return jsonify({"success": False, "log": "extract_census.py not found."}), 404
    try:
        proc = subprocess.run(
            [sys.executable, ETL_SCRIPT],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=3600,
        )
        log = f"{proc.stdout}\n{proc.stderr}".strip()[-4000:]
        if proc.returncode != 0:
            return jsonify({"success": False, "log": log or "ETL failed."})
        moved = organize_outputs()
        source = moved[0] if moved else find_latest_source()
        return jsonify({
            "success": True,
            "log": log or "Done.",
            "source": os.path.relpath(source, ROOT) if source else None,
        })
    except Exception as exc:
        return jsonify({"success": False, "log": str(exc)}), 500


@app.route("/api/preview", methods=["POST"])
def api_preview():
    data = request.json or {}
    include_keys = data.get("include_keys", True)

    source = find_latest_source()
    if not source:
        return jsonify({"error": "No master dataset found."}), 404

    df = load_master_data(source)

    picked_columns = resolve_columns(df, data)

    tables = build_sector_tables(df, picked_columns, include_keys=include_keys)
    combined = build_combined(df, picked_columns, include_keys=include_keys)

    preview_data = combined.head(50).to_dict(orient="records")
    columns = list(combined.columns)

    return jsonify({
        "columns": columns,
        "data": preview_data,
        "tables": list(tables.keys()),
        "total_rows": len(df),
        "selected_columns_count": len(picked_columns)
    })


@app.route("/api/export", methods=["POST"])
def api_export():
    data = request.json or {}
    include_keys = data.get("include_keys", True)
    export_format = data.get("format", "excel_workbook")

    source = find_latest_source()
    if not source:
        return jsonify({"error": "No master dataset found."}), 404

    df = load_master_data(source)
    picked_columns = resolve_columns(df, data)

    tables = build_sector_tables(df, picked_columns, include_keys=include_keys)
    combined = build_combined(df, picked_columns, include_keys=include_keys)

    os.makedirs(EXPORTS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if export_format == "excel_workbook":
        out_path = os.path.join(EXPORTS_DIR, f"DE_Health_SectorExport_{stamp}.xlsx")
        export_multi_sheet_excel(tables, out_path)
        filename = os.path.basename(out_path)
        return jsonify({"success": True, "download_url": f"/api/download/{filename}"})
    elif export_format == "combined_excel":
        out_path = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.xlsx")
        export_combined(combined, out_path)
        filename = os.path.basename(out_path)
        return jsonify({"success": True, "download_url": f"/api/download/{filename}"})
    elif export_format == "combined_csv":
        out_path = os.path.join(EXPORTS_DIR, f"DE_Health_Combined_{stamp}.csv")
        export_combined(combined, out_path)
        filename = os.path.basename(out_path)
        return jsonify({"success": True, "download_url": f"/api/download/{filename}"})
    else:
        fmt = "csv" if "csv" in export_format else "xlsx"
        out_dir = os.path.join(EXPORTS_DIR, f"DE_Health_Export_{stamp}")
        downloads = export_separate_files(tables, out_dir, fmt=fmt)
        zip_path = f"{out_dir}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in downloads:
                zf.write(p, arcname=os.path.basename(p))
        filename = os.path.basename(zip_path)
        return jsonify({"success": True, "download_url": f"/api/download/{filename}"})


@app.route("/api/download/<filename>", methods=["GET"])
def api_download(filename):
    return send_from_directory(EXPORTS_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    print("Starting Flask API backend on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
