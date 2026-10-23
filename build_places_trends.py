"""Build PLACES ZCTA yearly trend sheets for DE_ZCTA_County_Analysis.xlsx.

Reads the raw PLACES ZCTA trends CSV (2021-2023), computes trend metrics,
and adds two sheets plus native Excel line charts to the analysis workbook.

Run: python3 build_places_trends.py
"""

from __future__ import annotations

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference, Series

ROOT = "/Users/dharshinisenthilnathan/DE_Health_Force/de-sdoh-census-pipeline"
TRENDS_CSV = f"{ROOT}/DE_PLACES_ZCTA_Trends_Raw.csv"
MASTER_CSV = f"{ROOT}/Delaware_ZCTA_Health_Master_Wide.csv"
OUTPUT_XLSX = f"{ROOT}/DE_ZCTA_County_Analysis.xlsx"

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=13, color="1F4E78")
NOTE_FONT = Font(italic=True, size=9, color="555555")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

MEASURE_DISPLAY = {
    "Diagnosed diabetes among adults": "Diabetes %",
    "Obesity among adults": "Obesity %",
    "Coronary heart disease among adults": "Coronary Heart Disease %",
    "Chronic obstructive pulmonary disease among adults": "COPD %",
    "Stroke among adults": "Stroke %",
    "High blood pressure among adults": "High Blood Pressure %",
    "Current asthma among adults": "Current Asthma %",
    "Depression among adults": "Depression %",
    "Current cigarette smoking among adults": "Current Smoking %",
    "No leisure-time physical activity among adults": "Physical Inactivity %",
    "Binge drinking among adults": "Binge Drinking %",
    "Short sleep duration among adults": "Short Sleep %",
    "Fair or poor self-rated health status among adults": "Fair/Poor Health %",
    "Frequent mental distress among adults": "Frequent Mental Distress %",
    "Current lack of health insurance among adults aged 18-64 years": "Uninsured 18-64 %",
    "Visits to doctor for routine checkup within the past year among adults": "Routine Checkup %",
    "Visited dentist or dental clinic in the past year among adults": "Dental Visit %",
    "Cholesterol screening among adults": "Cholesterol Screening %",
    "Food insecurity in the past 12 months among adults": "Food Insecurity %",
    "Housing insecurity in the past 12 months among adults": "Housing Insecurity %",
}


def load_data() -> tuple:
    trends = pd.read_csv(TRENDS_CSV, low_memory=False)
    trends["Year"] = trends["Year"].astype(int)
    master = pd.read_csv(MASTER_CSV, low_memory=False)
    master["ZCTA"] = master["ZCTA"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    zcta_county = (
        master[["ZCTA", "County_Name"]]
        .drop_duplicates(subset="ZCTA")
        .set_index("ZCTA")["County_Name"]
        .to_dict()
    )
    trends["ZCTA"] = trends["ZCTA"].astype(str).str.zfill(5)
    return trends, zcta_county


def compute_trend_metrics(trends: pd.DataFrame, zcta_county: dict) -> pd.DataFrame:
    pivot = trends.pivot_table(
        index=["ZCTA", "Measure"],
        columns="Year",
        values="DataValue",
        aggfunc="first",
    ).reset_index()
    pivot.columns = [str(c) for c in pivot.columns]

    year_cols = sorted([c for c in pivot.columns if c.isdigit()])
    for yc in year_cols:
        pivot = pivot.rename(columns={yc: f"Y{yc}"})

    # Need at least 2 years to compute a trend
    year_yn = [f"Y{c}" for c in year_cols]
    has_enough = pivot[year_yn].notna().sum(axis=1) >= 2
    result = pivot[has_enough].copy().reset_index(drop=True)

    # For each ZCTA x Measure, find the first and last year with actual data
    start_vals, end_vals, start_years, end_years = [], [], [], []
    changes, pct_changes, slopes, directions, abs_changes, years_covered = [], [], [], [], [], []

    for _, row in result.iterrows():
        data_years = []
        for yc in year_yn:
            if pd.notna(row[yc]):
                data_years.append((int(yc[1:]), float(row[yc])))
        data_years.sort()

        y_start_val = data_years[0][1]
        y_end_val = data_years[-1][1]
        y_start_yr = data_years[0][0]
        y_end_yr = data_years[-1][0]

        start_vals.append(y_start_val)
        end_vals.append(y_end_val)
        start_years.append(y_start_yr)
        end_years.append(y_end_yr)
        change = y_end_val - y_start_val
        changes.append(change)
        years_span = y_end_yr - y_start_yr
        pct_changes.append(change / y_start_val * 100 if y_start_val != 0 else float("nan"))
        slopes.append(change / max(years_span, 1))

        def direction(slope):
            if abs(slope) < 0.1:
                return "Stable"
            return "Increasing" if slope > 0 else "Decreasing"

        directions.append(direction(change / max(years_span, 1)))
        abs_changes.append(abs(change))
        years_covered.append(f"{y_start_yr}-{y_end_yr}")

    result["Start_Value"] = start_vals
    result["End_Value"] = end_vals
    result["Start_Year"] = start_years
    result["End_Year"] = end_years
    result["Change_Total"] = changes
    result["Pct_Change"] = pct_changes
    result["Slope_Per_Year"] = slopes
    result["Trend_Direction"] = directions
    result["Abs_Change"] = abs_changes
    result["Years_Covered"] = years_covered

    # YoY changes for adjacent years available
    for i in range(len(year_yn) - 1):
        y_a, y_b = year_yn[i], year_yn[i + 1]
        result[f"Change_{y_a}_{y_b}"] = result[y_b] - result[y_a]

    result["County"] = result["ZCTA"].map(zcta_county)
    return result


def compute_statewide_summary(trends: pd.DataFrame) -> pd.DataFrame:
    yearly_avg = (
        trends.groupby(["Measure", "Year"])["DataValue"]
        .mean()
        .reset_index()
    )
    pivot = yearly_avg.pivot_table(
        index="Measure", columns="Year", values="DataValue", aggfunc="mean"
    ).reset_index()
    pivot.columns = [str(c) for c in pivot.columns]

    year_cols = sorted([c for c in pivot.columns if c.isdigit()])
    for yc in year_cols:
        pivot = pivot.rename(columns={yc: f"Y{yc}"})

    year_yn = [f"Y{c}" for c in year_cols]
    has_enough = pivot[year_yn].notna().sum(axis=1) >= 2
    result = pivot[has_enough].copy().reset_index(drop=True)
    result["Measure_Display"] = result["Measure"].map(
        lambda m: MEASURE_DISPLAY.get(m, m)
    )

    # For each measure, find the first and last year with actual data
    start_vals, end_vals, start_years, end_years = [], [], [], []
    changes, pct_changes, slopes, directions, abs_changes, years_covered = [], [], [], [], [], []

    for _, row in result.iterrows():
        data_years = []
        for yc in year_yn:
            if pd.notna(row[yc]):
                data_years.append((int(yc[1:]), float(row[yc])))
        data_years.sort()

        y_start_val = data_years[0][1]
        y_end_val = data_years[-1][1]
        y_start_yr = data_years[0][0]
        y_end_yr = data_years[-1][0]

        start_vals.append(y_start_val)
        end_vals.append(y_end_val)
        start_years.append(y_start_yr)
        end_years.append(y_end_yr)
        change = y_end_val - y_start_val
        changes.append(change)
        years_span = y_end_yr - y_start_yr
        pct_changes.append(change / y_start_val * 100 if y_start_val != 0 else float("nan"))
        slopes.append(change / max(years_span, 1))

        def direction(slope):
            if abs(slope) < 0.1:
                return "Stable"
            return "Increasing" if slope > 0 else "Decreasing"

        directions.append(direction(change / max(years_span, 1)))
        abs_changes.append(abs(change))
        years_covered.append(f"{y_start_yr}-{y_end_yr}")

    result["Start_Value"] = start_vals
    result["End_Value"] = end_vals
    result["Start_Year"] = start_years
    result["End_Year"] = end_years
    result["Change_Total"] = changes
    result["Pct_Change"] = pct_changes
    result["Slope_Per_Year"] = slopes
    result["Trend_Direction"] = directions
    result["Abs_Change"] = abs_changes
    result["Years_Covered"] = years_covered

    # YoY changes for adjacent years available
    for i in range(len(year_yn) - 1):
        y_a, y_b = year_yn[i], year_yn[i + 1]
        result[f"Change_{y_a}_{y_b}"] = result[y_b] - result[y_a]

    result = result.sort_values("Abs_Change", ascending=False)
    return result


def add_trends_sheets(wb, trends, zcta_county, summary):
    # ---- Sheet 1: PLACES_Trends_By_ZCTA ----
    ws_zcta = wb.create_sheet("PLACES_Trends_By_ZCTA")
    trends_with_county = trends.copy()
    trends_with_county["County"] = trends_with_county["ZCTA"].map(zcta_county)
    col_order = ["Measure", "ZCTA", "County", "Year", "DataValue", "CI_Low", "CI_High"]
    col_order = [c for c in col_order if c in trends_with_county.columns]
    trends_with_county = trends_with_county[col_order]

    headers = ["Measure", "ZCTA", "County", "Year", "Value (%)", "95% CI Low", "95% CI High"]
    ws_zcta.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws_zcta.cell(row=1, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")

    start_row = 2
    for i, (_, r) in enumerate(trends_with_county.iterrows()):
        row = start_row + i
        vals = [
            r["Measure"], str(r["ZCTA"]), r.get("County", ""),
            int(r["Year"]), round(float(r["DataValue"]), 2),
            round(float(r["CI_Low"]), 2) if pd.notna(r.get("CI_Low")) else None,
            round(float(r["CI_High"]), 2) if pd.notna(r.get("CI_High")) else None,
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws_zcta.cell(row=row, column=c, value=v)
            cell.border = BORDER
            if c in (5, 6, 7):
                cell.number_format = "0.00"
    ws_zcta.freeze_panes = "A2"

    # ---- Sheet 2: PLACES_Trends_Summary ----
    ws_sum = wb.create_sheet("PLACES_Trends_Summary")

    # Build dynamic headers based on available years (needed for merge width)
    year_cols = sorted([c for c in summary.columns if c.startswith("Y") and c[1:].isdigit()])
    year_labels = [c[1:] for c in year_cols]  # e.g. ["2022", "2023"]
    n_header_cols = 4 + len(year_cols) + 6  # Measure, Years, Start, End + year cols + change/pct/slope/direction/zctas

    # Title (merged across width for clean look)
    ws_sum["A1"] = "PLACES ZCTA Yearly Trends Summary"
    ws_sum["A1"].font = TITLE_FONT
    ws_sum.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_header_cols)

    ws_sum["A2"] = (
        "State-wide average of CDC PLACES ZCTA-level model-based estimates. "
        "Years covered vary by measure (2021-2023 from CDC PLACES API releases). "
        "Slope = avg annual change in percentage points. "
        "Trend direction: |slope| >= 0.1 = Increasing/Decreasing, otherwise Stable."
    )
    ws_sum["A2"].font = NOTE_FONT
    ws_sum.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_header_cols)

    # Row 3 = blank spacer so title doesn't crowd the blue header

    # Build dynamic headers based on available years
    year_cols = sorted([c for c in summary.columns if c.startswith("Y") and c[1:].isdigit()])
    year_labels = [c[1:] for c in year_cols]  # e.g. ["2022", "2023"]

    headers = ["Measure", "Years Covered", "Start Value (%)", "End Value (%)"]
    for yl in year_labels:
        headers.append(f"{yl} Avg (%)")
    headers += ["Total Change (pp)", "Pct Change (%)", "Slope / Year (pp)", "Trend Direction", "ZCTAs with Data"]

    header_row = 4
    for c, h in enumerate(headers, start=1):
        cell = ws_sum.cell(row=header_row, column=c, value=h)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    start_row = header_row + 1
    for i, (_, r) in enumerate(summary.iterrows()):
        row = start_row + i
        zcta_count_n = int(trends[trends["Measure"] == r["Measure"]]["ZCTA"].nunique())
        year_vals = []
        for yc in year_cols:
            v = r[yc]
            year_vals.append(round(float(v), 2) if pd.notna(v) else "—")
        vals = [
            r["Measure_Display"],
            r["Years_Covered"],
            round(float(r["Start_Value"]), 2),
            round(float(r["End_Value"]), 2),
        ] + year_vals + [
            round(float(r["Change_Total"]), 2),
            round(float(r["Pct_Change"]), 1),
            round(float(r["Slope_Per_Year"]), 2),
            r["Trend_Direction"],
            zcta_count_n,
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws_sum.cell(row=row, column=c, value=v)
            cell.border = BORDER
            # Number columns: Start Value, End Value, year cols, Change, Pct Change, Slope
            num_cols = [3, 4] + list(range(5, 5 + len(year_cols))) + [5 + len(year_cols), 6 + len(year_cols), 7 + len(year_cols)]
            if c in num_cols:
                cell.number_format = "0.00" if c != 6 + len(year_cols) else "0.0"
            # Fill blanks in year columns with em-dash
            if c in list(range(5, 5 + len(year_cols))) and v == "—":
                cell.alignment = Alignment(horizontal="center", vertical="center")

    end_row = start_row + len(summary) - 1

    # Hidden chart data block
    chart_data_start = end_row + 3
    ws_sum.cell(row=chart_data_start, column=1, value="Chart Data (hidden)").font = NOTE_FONT
    chart_headers = ["Measure"] + year_labels
    for c, h in enumerate(chart_headers, start=1):
        cell = ws_sum.cell(row=chart_data_start + 1, column=c, value=h)
        cell.font = HDR_FONT
        cell.border = BORDER

    chart_rows = {}
    for i, (_, r) in enumerate(summary.iterrows()):
        row = chart_data_start + 2 + i
        ws_sum.cell(row=row, column=1, value=r["Measure_Display"]).border = BORDER
        for j, yc in enumerate(year_cols, start=2):
            v = r[yc]
            cell = ws_sum.cell(row=row, column=j, value=round(float(v), 2) if pd.notna(v) else None)
            cell.number_format = "0.00"
            cell.border = BORDER
        chart_rows[r["Measure_Display"]] = row

    for rr in range(chart_data_start, chart_data_start + 2 + len(summary)):
        ws_sum.row_dimensions[rr].hidden = True

    # Charts for top 6 measures (placed below the data table to avoid overlap)
    top_measures = summary.head(6)["Measure_Display"].tolist()
    chart_start_col = 2
    chart_row = end_row + 3
    year_col_start = 5  # year avg columns start at column 5
    year_col_end = 5 + len(year_cols) - 1
    for measure_name in top_measures:
        chart = LineChart()
        chart.title = measure_name
        chart.style = 12
        chart.y_axis.title = "Value (%)"
        chart.x_axis.title = "Year"
        chart.height = 7
        chart.width = 15
        data_row = chart_rows[measure_name]
        cats = Reference(ws_sum, min_col=year_col_start, min_row=chart_data_start + 1, max_col=year_col_end, max_row=chart_data_start + 1)
        s = Series(
            values=Reference(ws_sum, min_col=year_col_start, min_row=data_row, max_col=year_col_end, max_row=data_row),
            title=measure_name,
        )
        chart.series = [s]
        chart.set_categories(cats)
        col_letter = get_column_letter(chart_start_col)
        ws_sum.add_chart(chart, f"{col_letter}{chart_row}")
        chart_row += 18


def main():
    trends, zcta_county = load_data()
    zcta_trends = compute_trend_metrics(trends, zcta_county)
    summary = compute_statewide_summary(trends)

    wb = load_workbook(OUTPUT_XLSX)

    # Remove existing trend sheets (and any numbered duplicates like ...1, ...2) to keep clean
    for base in ["PLACES_Trends_By_ZCTA", "PLACES_Trends_Summary"]:
        to_delete = [s for s in wb.sheetnames if s == base or s.startswith(base)]
        for s in to_delete:
            del wb[s]

    add_trends_sheets(wb, trends, zcta_county, summary)
    wb.save(OUTPUT_XLSX)

    print(f"\nAdded trends sheets to {OUTPUT_XLSX}")
    print(f"  PLACES_Trends_By_ZCTA: {len(trends)} rows")
    print(f"  PLACES_Trends_Summary: {len(summary)} measures")
    print("\nTrend Summary (state-wide average):")
    year_cols = sorted([c for c in summary.columns if c.startswith("Y") and c[1:].isdigit()])
    for _, r in summary.head(10).iterrows():
        y_str = " ".join(f"{c[1:]}={r[c]:5.2f}" for c in year_cols)
        print(
            f"  {r['Measure_Display']:35s} {y_str} "
            f"Total={r['Change_Total']:+.2f}pp Slope={r['Slope_Per_Year']:+.2f} "
            f"[{r['Trend_Direction']}] {r['Years_Covered']}"
        )


if __name__ == "__main__":
    main()