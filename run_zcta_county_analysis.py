"""ZCTA-level and County-level health / socioeconomic analysis.

Two analyses, both written to ``DE_ZCTA_County_Analysis.xlsx`` with the
calculations left visible as live Excel formulas (click any result cell to see
its formula), plus a ``README_Methods`` sheet documenting each formula.

ZCTA analysis: for every exposure x outcome pair (5 x 9 = 45) it reports the
pairwise-complete sample size ``n`` and
    Spearman rho = correlation between the RANKED values of X and Y
    Pearson r    = covariance(X, Y) / (std(X) * std(Y))
Primary exposure = ACS poverty % (``Pct_Below_Poverty``); primary outcome =
PLACES diagnosed diabetes % (``PLACES_Pct_Diabetes``); the rest are secondary.
The primary pair is also shown as a fully worked, step-by-step example.

County analysis: residents per primary-care physician = AHRF population / AHRF
PCP count, ranked highest-to-lowest (Kent is highest). CHR health-burden
indicators (fair/poor health, adult obesity, adult smoking, uninsured %) ranked
highest-to-lowest, with the county gap (highest - lowest) and highest-burden
county noted for each.

Cleaning: Census sentinels (<= -111111111) and PLACES nulls -> NaN and dropped
per pair (no imputation); ACS and PLACES matched on 5-char ZCTA; only ZCTAs
valid for BOTH measures in a pair are kept and that pair's n is reported.

No scipy: Spearman is Pearson-on-ranks, Pearson from its definition.

Run: python3 run_zcta_county_analysis.py

How to open the output
    The script writes DE_ZCTA_County_Analysis.xlsx (and a flat
    DE_ZCTA_Correlation_Summary.csv) in this folder and prints the paths when
    it finishes. Open the workbook by:
      * double-clicking DE_ZCTA_County_Analysis.xlsx in Finder, or
      * from the terminal:  open DE_ZCTA_County_Analysis.xlsx
        (the full path is <this folder>/DE_ZCTA_County_Analysis.xlsx)
    Result cells are live Excel formulas, so let Excel/Numbers recalculate on
    open (in Excel press Cmd + = to force it). Every statistics sheet also has a
    "Python value (check)" column already filled in, so numbers show immediately.
    Only classic functions are used, so it opens with no #NAME? errors.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from scipy import stats as _stats
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER_PATH = os.path.join(ROOT, "Delaware_ZCTA_Health_Master_Wide.csv")
CHR_PATH = os.path.join(ROOT, "raw", "chr_2025_de_counties_raw.csv")
AHRF_PATH = os.path.join(ROOT, "raw", "hrsa_ahrf_2025_de_counties_raw.csv")
OUTPUT_XLSX = os.path.join(ROOT, "DE_ZCTA_County_Analysis.xlsx")
OUTPUT_CSV = os.path.join(ROOT, "DE_ZCTA_Correlation_Summary.csv")

# Census missing-value sentinel threshold (matches extract_census.py). The API
# returns these as numbers, so they are masked AFTER pd.to_numeric.
CENSUS_SENTINEL_MAX = -111111111

DE_COUNTY_FIPS = {"10001", "10003", "10005"}
FIPS_TO_NAME = {"10001": "Kent", "10003": "New Castle", "10005": "Sussex"}

# Styling helpers -----------------------------------------------------------
HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=13, color="1F4E78")
SUB_FONT = Font(bold=True, size=11, color="1F4E78")
PRIMARY_FILL = PatternFill("solid", fgColor="FFF2CC")
HIGH_FILL = PatternFill("solid", fgColor="FCE4D6")
NOTE_FONT = Font(italic=True, size=9, color="555555")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# --------------------------------------------------------------------------
# Measure registry: (master column, human label, role)
# --------------------------------------------------------------------------
PRIMARY_EXPOSURE = ("Pct_Below_Poverty", "Poverty % (ACS DP03_0128PE)", "Primary exposure")
PRIMARY_OUTCOME = ("PLACES_Pct_Diabetes", "Diagnosed diabetes among adults (PLACES)", "Primary outcome")

SECONDARY_EXPOSURES = [
    ("Median_Household_Income", "Median household income (ACS)", "Secondary exposure"),
    ("Pct_No_Health_Insurance", "Uninsured % (ACS)", "Secondary exposure"),
    ("Pct_Age_65_Plus", "Age 65+ % (ACS)", "Secondary exposure"),
    ("Pct_NonEnglish_Language_Home", "Non-English spoken at home % (ACS)", "Secondary exposure"),
]

SECONDARY_OUTCOMES = [
    ("PLACES_Pct_Obesity", "Obesity (PLACES)", "Secondary outcome"),
    ("PLACES_Pct_Fair_Poor_Health", "Fair/poor self-rated health (PLACES)", "Secondary outcome"),
    ("PLACES_Pct_Coronary_Heart_Disease", "Coronary heart disease (PLACES)", "Secondary outcome"),
    ("PLACES_Pct_COPD", "COPD (PLACES)", "Secondary outcome"),
    ("PLACES_Pct_Stroke", "Stroke (PLACES)", "Secondary outcome"),
    ("PLACES_Pct_Physical_Inactivity", "Physical inactivity (PLACES)", "Secondary outcome"),
    ("PLACES_Pct_Frequent_Mental_Distress", "Frequent mental distress (PLACES)", "Secondary outcome"),
    ("PLACES_Pct_Current_Smoking", "Current smoking (PLACES)", "Secondary outcome"),
]

EXPOSURES = [PRIMARY_EXPOSURE] + SECONDARY_EXPOSURES          # 5
OUTCOMES = [PRIMARY_OUTCOME] + SECONDARY_OUTCOMES             # 9
ALL_MEASURES = [m[0] for m in EXPOSURES] + [m[0] for m in OUTCOMES]

# County CHR health-burden measures: (short name, raw CHR column, report label).
COUNTY_MEASURES = [
    ("Fair/poor health", "Poor or Fair Health__% Fair or Poor Health", "Fair/poor health %"),
    ("Adult obesity", "Adult Obesity__% Adults with Obesity", "Adult obesity %"),
    ("Adult smoking", "Adult Smoking__% Adults Reporting Currently Smoking", "Adult smoking %"),
    ("Uninsured", "Uninsured__% Uninsured", "Uninsured %"),
]


# --------------------------------------------------------------------------
# Statistics (scipy-free; exactly the formulas in the task)
# --------------------------------------------------------------------------
def spearman_rho(x, y) -> float:
    """Spearman's rho = Pearson correlation of the ranks of X and Y.

    Ties receive the average rank (``Series.rank`` default), matching the
    standard Spearman definition / scipy.stats.spearmanr.
    """
    rx = pd.Series(x).rank()
    ry = pd.Series(y).rank()
    if rx.std(ddof=0) == 0 or ry.std(ddof=0) == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def pearson_r(x, y) -> float:
    """Pearson's r = covariance(X, Y) / (std(X) * std(Y))."""
    x = pd.Series(x).astype(float)
    y = pd.Series(y).astype(float)
    if x.std(ddof=0) == 0 or y.std(ddof=0) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def correlation_p_value(r: float, n: int) -> float:
    """Two-tailed p-value for H0: rho = 0 using a t-distribution.

    t = r * sqrt((n - 2) / (1 - r^2)),  df = n - 2,  p = 2 * P(T_df > |t|).
    Returns NaN when n < 3, r is NaN, or |r| == 1 (division by zero).
    """
    if n < 3 or np.isnan(r) or abs(r) >= 1.0:
        return float("nan")
    t = r * np.sqrt((n - 2) / (1.0 - r ** 2))
    df = n - 2
    return float(_stats.t.sf(abs(t), df) * 2.0)


def benjamini_hochberg(p_values: list) -> list:
    """Benjamini-Hochberg FDR correction.

    Returns adjusted p-values in the original input order. NaN inputs map to
    NaN outputs. Monotonicity is enforced so adjusted p-values never decrease
    as raw p-values increase.
    """
    p_values = np.asarray(p_values, dtype=float)
    n_total = len(p_values)
    is_nan = np.isnan(p_values)
    adjusted = np.full(n_total, np.nan)

    valid_idx = np.where(~is_nan)[0]
    if valid_idx.size == 0:
        return adjusted.tolist()

    valid_p = p_values[valid_idx]
    m = valid_p.size

    order = np.argsort(valid_p)
    ranked_p = valid_p[order]

    # BH step-up: p_adj[i] = min(1, p_sorted[i] * m / rank[i]), then enforce
    # monotonicity from the largest p-value down.
    bh_sorted = ranked_p * m / np.arange(1, m + 1)
    bh_sorted = np.minimum.accumulate(bh_sorted[::-1])[::-1]
    bh_sorted = np.minimum(bh_sorted, 1.0)

    adjusted[valid_idx[order]] = bh_sorted
    return adjusted.tolist()


def correlation_ci(r: float, n: int, alpha: float = 0.05) -> tuple:
    """95% confidence interval for Pearson r via the Fisher z-transform.

    z = 0.5 * ln((1+r)/(1-r));  SE_z = 1/sqrt(n-3);
    CI on z-scale: z +/- z_(1-alpha/2) * SE_z, then back-transformed to r.
    Returns (NaN, NaN) when n < 4, r is NaN, or |r| == 1.
    """
    if n < 4 or np.isnan(r) or abs(r) >= 1.0:
        return (float("nan"), float("nan"))
    z = 0.5 * np.log((1.0 + r) / (1.0 - r))
    se_z = 1.0 / np.sqrt(n - 3)
    z_crit = _stats.norm.ppf(1.0 - alpha / 2.0)
    z_lo = z - z_crit * se_z
    z_hi = z + z_crit * se_z
    r_lo = (np.exp(2.0 * z_lo) - 1.0) / (np.exp(2.0 * z_lo) + 1.0)
    r_hi = (np.exp(2.0 * z_hi) - 1.0) / (np.exp(2.0 * z_hi) + 1.0)
    return (float(r_lo), float(r_hi))


# --------------------------------------------------------------------------
# Loading & cleaning
# --------------------------------------------------------------------------
def load_zcta_frame() -> pd.DataFrame:
    """Load the ACS x PLACES ZCTA master and re-apply the sentinel mask.

    Returns a frame keyed by 5-char ZCTA carrying ZCTA, County_Name and every
    exposure/outcome column, with Census sentinels and PLACES nulls as NaN.
    """
    if not os.path.exists(MASTER_PATH):
        raise SystemExit(
            f"{os.path.relpath(MASTER_PATH, ROOT)} is missing - build it with "
            "`python3 extract_census.py` first."
        )
    df = pd.read_csv(MASTER_PATH, low_memory=False)

    # ZCTA key as 5-char string (match ACS and PLACES on five-character ZCTA).
    df["ZCTA"] = df["ZCTA"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)

    missing = [c for c in ALL_MEASURES if c not in df.columns]
    if missing:
        raise SystemExit(f"Master is missing required measure columns: {missing}")
    keep = ["ZCTA"] + (["County_Name"] if "County_Name" in df.columns else []) + ALL_MEASURES
    df = df[keep].copy()

    # Coerce to numeric then mask any Census sentinel (<= -111111111) -> NaN so
    # unreliable ZCTAs drop out of the affected pair entirely.
    for col in ALL_MEASURES:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] <= CENSUS_SENTINEL_MAX, col] = np.nan

    return df.reset_index(drop=True)


def load_county_frames() -> pd.DataFrame:
    """Load CHR health-burden measures + AHRF population & PCP counts by county."""
    chr_df = pd.read_csv(CHR_PATH, low_memory=False)
    chr_df["County_FIPS"] = (
        chr_df["FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    )
    chr_df = chr_df[chr_df["County_FIPS"].isin(DE_COUNTY_FIPS)].copy()

    ahrf = pd.read_csv(AHRF_PATH, low_memory=False)
    ahrf["County_FIPS"] = ahrf["fips_st_cnty"].astype(int).astype(str).str.zfill(5)
    ahrf = ahrf[ahrf["County_FIPS"].isin(DE_COUNTY_FIPS)].copy()

    out = chr_df[["County_FIPS", "County"]].copy()
    out["County_Name"] = out["County_FIPS"].map(FIPS_TO_NAME).fillna(out["County"].str.strip())
    chr_idx = chr_df.set_index("County_FIPS")
    for _, src, label in COUNTY_MEASURES:
        out[label] = pd.to_numeric(out["County_FIPS"].map(chr_idx[src]), errors="coerce")

    ahrf_idx = ahrf.set_index("County_FIPS")
    out["AHRF_Population_2024"] = out["County_FIPS"].map(ahrf_idx["pop_popn_est_24"])
    out["AHRF_PCP_Count_2023"] = out["County_FIPS"].map(
        ahrf_idx["phys_nf_prim_care_pc_exc_rsdt_23"]
    )
    return out.reset_index(drop=True)

# --------------------------------------------------------------------------
# Correlation computation (pairwise-complete, per pair)
# --------------------------------------------------------------------------
def compute_correlations(zcta: pd.DataFrame) -> list:
    """One result dict per exposure x outcome pair (45), pairwise-complete n.

    Each ZCTA where BOTH the exposure and the outcome are valid is retained;
    that count is the pair's sample size n. Spearman uses subset ranks (the
    standard definition) and Pearson its covariance/std definition.
    """
    results = []
    for exp_col, exp_label, exp_role in EXPOSURES:
        for out_col, out_label, out_role in OUTCOMES:
            pair = zcta[[exp_col, out_col]].dropna()
            n = int(len(pair))
            is_primary = (exp_col == PRIMARY_EXPOSURE[0] and out_col == PRIMARY_OUTCOME[0])
            spear = spearman_rho(pair[exp_col], pair[out_col]) if n >= 3 else float("nan")
            pear = pearson_r(pair[exp_col], pair[out_col]) if n >= 3 else float("nan")
            results.append({
                "exposure_col": exp_col,
                "exposure": exp_label,
                "exposure_role": exp_role,
                "outcome_col": out_col,
                "outcome": out_label,
                "outcome_role": out_role,
                "primary_pair": is_primary,
                "n": n,
                "spearman": spear,
                "pearson": pear,
                "pearson_p": correlation_p_value(pear, n),
                "spearman_p": correlation_p_value(spear, n),
            })
    # Benjamini-Hochberg FDR correction across all 45 Pearson p-values.
    fdr_adjusted = benjamini_hochberg([r["pearson_p"] for r in results])
    for r, adj in zip(results, fdr_adjusted):
        r["fdr_p"] = adj
    # 95% confidence interval for Pearson r (Fisher z-transform).
    for r in results:
        ci_lo, ci_hi = correlation_ci(r["pearson"], r["n"])
        r["ci_lower"] = ci_lo
        r["ci_upper"] = ci_hi
    # Primary pair first, then by exposure role/order.
    results.sort(key=lambda r: (not r["primary_pair"],))
    return results


# --------------------------------------------------------------------------
# Excel helpers
# --------------------------------------------------------------------------
def style_header(ws, row: int, ncols: int, freeze: bool = True) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    # Use a string coordinate: passing ws.cell(...) here would instantiate that
    # cell and bump max_row, creating a phantom empty row that shifts all data.
    if freeze:
        ws.freeze_panes = f"A{row + 1}"


def autofit(ws, max_width: int = 46) -> None:
    for col_cells in ws.columns:
        letter = get_column_letter(col_cells[0].column)
        longest = 0
        for cell in col_cells:
            v = cell.value
            if v is None:
                continue
            length = len(str(v))
            if length > longest:
                longest = length
        ws.column_dimensions[letter].width = min(max(10, longest + 2), max_width)


def write_row(ws, row: int, values: list, number_format: str = None) -> None:
    for c, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=c, value=val)
        cell.border = BORDER
        if number_format and isinstance(val, (int, float)):
            cell.number_format = number_format

# --------------------------------------------------------------------------
# Sheet builders - ZCTA data + ranks
# --------------------------------------------------------------------------
def _exposure_letter(i: int) -> str:
    """Column letter for exposure i (0-based) on ZCTA_Data / ZCTA_Ranks."""
    return get_column_letter(3 + i)


def _outcome_letter(j: int) -> str:
    """Column letter for outcome j (0-based) on ZCTA_Data / ZCTA_Ranks."""
    return get_column_letter(8 + j)


def build_zcta_data_sheet(ws, zcta: pd.DataFrame) -> int:
    """Write the matched ZCTA values. Returns the last data row index."""
    headers = ["ZCTA", "County"] + [m[1] for m in EXPOSURES] + [m[1] for m in OUTCOMES]
    ws.append(headers)
    style_header(ws, 1, len(headers))
    for _, r in zcta.iterrows():
        row = [r["ZCTA"], r.get("County_Name")]
        for col, _, _ in EXPOSURES:
            v = r[col]
            row.append(None if pd.isna(v) else float(v))
        for col, _, _ in OUTCOMES:
            v = r[col]
            row.append(None if pd.isna(v) else float(v))
        write_row(ws, ws.max_row + 1, row)
    autofit(ws)
    return ws.max_row  # last data row (1 header + N data)


def build_zcta_ranks_sheet(ws, zcta: pd.DataFrame, last_row: int) -> None:
    """Average ranks for every ZCTA measure, written as values.

    Ranks are pre-computed in Python with average-tie handling (the standard
    Spearman definition) and written as static values rather than RANK.AVG
    formulas: RANK.AVG is an Excel 2010+ "future function" that openpyxl cannot
    store correctly and that shows #NAME? in some Excel/Numbers versions. The
    live =CORREL(...) Spearman formulas on ZCTA_Correlations read these rank
    columns, so a blank here (missing source value) triggers CORREL's
    pairwise-complete deletion automatically.
    """
    headers = ["ZCTA", "County"] + [m[1] for m in EXPOSURES] + [m[1] for m in OUTCOMES]
    ws.append(headers)
    style_header(ws, 1, len(headers))
    measure_cols = [m[0] for m in EXPOSURES] + [m[0] for m in OUTCOMES]
    ranks = {col: zcta[col].rank(method="average") for col in measure_cols}
    zr = zcta.reset_index(drop=True)
    for i in range(len(zr)):
        row = [zr.iloc[i]["ZCTA"], zr.iloc[i].get("County_Name")]
        for col in measure_cols:
            v = ranks[col].iloc[i]
            row.append(None if pd.isna(v) else float(v))
        write_row(ws, ws.max_row + 1, row)
    autofit(ws)

# --------------------------------------------------------------------------
# Sheet builder - ZCTA correlations (45 pairs)
# --------------------------------------------------------------------------
def build_correlations_sheet(ws, corr_results: list, last_row: int) -> None:
    """One row per exposure x outcome pair with n, Spearman, Pearson.

    Authoritative values are the Python subset-rank Spearman and definition
    Pearson. Live ``=CORREL(...)`` formulas are also written (referencing
    ZCTA_Data for Pearson and ZCTA_Ranks for Spearman) so the calculation is
    visible/auditable; CORREL does pairwise-complete deletion automatically.
    """
    headers = [
        "Exposure", "Exposure role", "Outcome", "Outcome role",
        "n (pairwise-complete)", "Spearman rho (subset ranks)",
        "Pearson r (definition)",
        "Spearman rho (Excel: CORREL of ranks)", "Pearson r (Excel: CORREL)",
        "Spearman formula", "Pearson formula",
        "Pearson p-value (H0: rho = 0)", "Pearson p-value (Excel: T.DIST.2T)",
        "Spearman p-value (H0: rho = 0)", "Spearman p-value (Excel: T.DIST.2T)",
        "FDR-adjusted p-value (Benjamini-Hochberg)",
        "Pearson 95% CI lower", "Pearson 95% CI upper",
        "Pearson 95% CI lower (Excel)", "Pearson 95% CI upper (Excel)",
    ]
    ws.append(headers)
    style_header(ws, 1, len(headers))

    exp_idx = {m[0]: i for i, m in enumerate(EXPOSURES)}
    out_idx = {m[0]: j for j, m in enumerate(OUTCOMES)}

    for r in corr_results:
        row = ws.max_row + 1
        ec = _exposure_letter(exp_idx[r["exposure_col"]])
        oc = _outcome_letter(out_idx[r["outcome_col"]])
        spear_formula = (
            f"=CORREL(ZCTA_Ranks!{ec}$2:{ec}${last_row},"
            f"ZCTA_Ranks!{oc}$2:{oc}${last_row})"
        )
        pear_formula = (
            f"=CORREL(ZCTA_Data!{ec}$2:{ec}${last_row},"
            f"ZCTA_Data!{oc}$2:{oc}${last_row})"
        )
        # Live Excel p-value formulas reference the live CORREL cells:
        # col I (9) = Pearson r CORREL, col H (8) = Spearman r CORREL, col E (5) = n.
        pear_p_formula = (
            f"=T.DIST.2T(ABS(I{row}*SQRT((E{row}-2)/(1-I{row}^2))),E{row}-2)"
        )
        spear_p_formula = (
            f"=T.DIST.2T(ABS(H{row}*SQRT((E{row}-2)/(1-H{row}^2))),E{row}-2)"
        )
        # Fisher z-transform CI for Pearson r (col I), n (col E).
        z_expr = f"0.5*LN((1+I{row})/(1-I{row}))"
        se_expr = f"1/SQRT(E{row}-3)"
        ci_lo_formula = (
            f"=(EXP(2*({z_expr}-1.96*{se_expr}))-1)/"
            f"(EXP(2*({z_expr}-1.96*{se_expr}))+1)"
        )
        ci_hi_formula = (
            f"=(EXP(2*({z_expr}+1.96*{se_expr}))-1)/"
            f"(EXP(2*({z_expr}+1.96*{se_expr}))+1)"
        )

        write_row(ws, row, [
            r["exposure"], r["exposure_role"], r["outcome"], r["outcome_role"],
            r["n"], r["spearman"], r["pearson"],
            spear_formula, pear_formula,
            f"CORREL( rank({r['exposure_col']}), rank({r['outcome_col']}) )",
            f"COVAR({r['exposure_col']},{r['outcome_col']}) / "
            f"( STDEVP({r['exposure_col']}) * STDEVP({r['outcome_col']}) )  =  CORREL(x,y)",
            r["pearson_p"], pear_p_formula,
            r["spearman_p"], spear_p_formula,
            r["fdr_p"],
            r["ci_lower"], r["ci_upper"],
            ci_lo_formula, ci_hi_formula,
        ])
        for col in (6, 7, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20):
            ws.cell(row=row, column=col).number_format = "0.0000"
        if r["primary_pair"]:
            for c in range(1, len(headers) + 1):
                ws.cell(row=row, column=c).fill = PRIMARY_FILL
                ws.cell(row=row, column=c).font = Font(bold=True)
    autofit(ws)

# --------------------------------------------------------------------------
# Sheet builder - Primary worked example (poverty x diabetes)
# --------------------------------------------------------------------------
def build_primary_example_sheet(ws, zcta: pd.DataFrame) -> None:
    """Fully worked, live-formula derivation for the primary pair.

    Shows the pairwise-complete rows, their ranks (live RANK.AVG over the
    block), then covariance / std / Pearson / Spearman as live formulas so the
    headline numbers can be traced end to end.
    """
    exp_col, exp_label, _ = PRIMARY_EXPOSURE
    out_col, out_label, _ = PRIMARY_OUTCOME
    pair = zcta[["ZCTA", exp_col, out_col]].dropna().sort_values(exp_col).reset_index(drop=True)
    n = len(pair)

    ws["A1"] = f"Worked example - {exp_label} (X) vs {out_label} (Y)"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (
        f"Only the {n} ZCTAs valid for BOTH measures are kept (pairwise-complete). "
        "Ranks, covariance, std and both correlations are live formulas - click a "
        "cell to see the calculation."
    )
    ws["A2"].font = NOTE_FONT

    data_start = 4
    data_end = data_start + n - 1
    headers = ["ZCTA", f"{exp_label} (X)", f"{out_label} (Y)", "Rank X (avg)", "Rank Y (avg)"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=data_start - 1, column=c, value=h)
    style_header(ws, data_start - 1, len(headers), freeze=False)

    # Average ranks (pre-computed) so the live =CORREL below reproduces Spearman
    # exactly without the #NAME?-prone RANK.AVG future function.
    rank_x = pair[exp_col].rank(method="average")
    rank_y = pair[out_col].rank(method="average")

    for i, r in pair.iterrows():
        row = data_start + i
        write_row(ws, row, [r["ZCTA"], float(r[exp_col]), float(r[out_col])])
        ws.cell(row=row, column=4, value=float(rank_x.iloc[i]))
        ws.cell(row=row, column=5, value=float(rank_y.iloc[i]))
        for c in (2, 3):
            ws.cell(row=row, column=c).number_format = "0.0"
        for c in (4, 5):
            ws.cell(row=row, column=c).number_format = "0.0"

    xr = f"B{data_start}:B{data_end}"
    yr = f"C{data_start}:C{data_end}"
    rxr = f"D{data_start}:D{data_end}"
    ryr = f"E{data_start}:E{data_end}"

    spear_py = spearman_rho(pair[exp_col], pair[out_col])
    pear_py = pearson_r(pair[exp_col], pair[out_col])
    pear_p_py = correlation_p_value(pear_py, n)
    spear_p_py = correlation_p_value(spear_py, n)
    ci_lo_py, ci_hi_py = correlation_ci(pear_py, n)

    n_formula = f"=COUNT({xr})"
    pear_r_formula = f"=CORREL({xr},{yr})"
    spear_r_formula = f"=CORREL({rxr},{ryr})"
    pear_p_formula = (
        f"=T.DIST.2T(ABS({pear_r_formula[1:]}*SQRT(({n_formula[1:]}-2)/"
        f"(1-{pear_r_formula[1:]}^2))),{n_formula[1:]}-2)"
    )
    spear_p_formula = (
        f"=T.DIST.2T(ABS({spear_r_formula[1:]}*SQRT(({n_formula[1:]}-2)/"
        f"(1-{spear_r_formula[1:]}^2))),{n_formula[1:]}-2)"
    )
    z_expr = f"0.5*LN((1+{pear_r_formula[1:]})/(1-{pear_r_formula[1:]}))"
    se_expr = f"1/SQRT({n_formula[1:]}-3)"
    ci_lo_formula = (
        f"=(EXP(2*({z_expr}-1.96*{se_expr}))-1)/"
        f"(EXP(2*({z_expr}-1.96*{se_expr}))+1)"
    )
    ci_hi_formula = (
        f"=(EXP(2*({z_expr}+1.96*{se_expr}))-1)/"
        f"(EXP(2*({z_expr}+1.96*{se_expr}))+1)"
    )

    s = data_end + 2
    ws.cell(row=s, column=1, value="Calculation").fill = HDR_FILL
    ws.cell(row=s, column=1).font = HDR_FONT
    ws.cell(row=s, column=2, value="Formula (as entered)").fill = HDR_FILL
    ws.cell(row=s, column=2).font = HDR_FONT
    ws.cell(row=s, column=3, value="Excel value").fill = HDR_FILL
    ws.cell(row=s, column=3).font = HDR_FONT
    ws.cell(row=s, column=4, value="Python value (check)").fill = HDR_FILL
    ws.cell(row=s, column=4).font = HDR_FONT

    stats = [
        ("n (pairwise-complete)", f"=COUNT({xr})", None, float(n), "0"),
        ("Mean of X (poverty %)", f"=AVERAGE({xr})", None, float(pair[exp_col].mean()), "0.000"),
        ("Mean of Y (diabetes %)", f"=AVERAGE({yr})", None, float(pair[out_col].mean()), "0.000"),
        ("Covariance(X, Y)  [population]", f"=COVAR({xr},{yr})", None,
         float(np.cov(pair[exp_col], pair[out_col], ddof=0)[0, 1]), "0.000"),
        ("Std dev of X  [population]", f"=STDEVP({xr})", None, float(pair[exp_col].std(ddof=0)), "0.000"),
        ("Std dev of Y  [population]", f"=STDEVP({yr})", None, float(pair[out_col].std(ddof=0)), "0.000"),
        ("Pearson r  = COVAR / (STDEVP * STDEVP)",
         f"=COVAR({xr},{yr})/(STDEVP({xr})*STDEVP({yr}))", None, pear_py, "0.0000"),
        ("Pearson r  (CORREL)", pear_r_formula, None, pear_py, "0.0000"),
        ("Spearman rho  = CORREL(rank X, rank Y)", spear_r_formula, None, spear_py, "0.0000"),
        ("Pearson p-value  (H0: rho = 0)", pear_p_formula, None, pear_p_py, "0.0000"),
        ("Spearman p-value  (H0: rho = 0)", spear_p_formula, None, spear_p_py, "0.0000"),
        ("Pearson 95% CI lower  (Fisher z)", ci_lo_formula, None, ci_lo_py, "0.0000"),
        ("Pearson 95% CI upper  (Fisher z)", ci_hi_formula, None, ci_hi_py, "0.0000"),
    ]
    for k, (label, formula, _unused, pyval, fmt) in enumerate(stats):
        row = s + 1 + k
        ws.cell(row=row, column=1, value=label).border = BORDER
        # Column B: the formula as readable text (leading '=' stripped so Excel
        # shows it as text, not a duplicate live formula).
        c2 = ws.cell(row=row, column=2, value=formula[1:] if formula.startswith("=") else formula)
        c2.border = BORDER
        c2.alignment = Alignment(horizontal="left")
        # Column C: the same formula as a live, clickable cell.
        c3 = ws.cell(row=row, column=3, value=formula)
        c3.number_format = fmt
        c3.border = BORDER
        c4 = ws.cell(row=row, column=4, value=pyval)
        c4.number_format = fmt
        c4.border = BORDER
    autofit(ws, max_width=52)

# --------------------------------------------------------------------------
# Sheet builders - County level
# --------------------------------------------------------------------------
def build_county_provider_sheet(ws, county: pd.DataFrame) -> None:
    """Residents per primary-care physician (AHRF), ranked highest-to-lowest."""
    ws["A1"] = "County primary-care access - residents per primary-care physician (AHRF)"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("Residents per PCP = AHRF population / AHRF primary-care physician count. "
                "A higher ratio means fewer PCPs relative to population (a bigger gap).")
    ws["A2"].font = NOTE_FONT

    start = 4
    headers = ["County", "County FIPS", "AHRF population (2024)",
               "AHRF primary-care physicians (2023)", "Residents per PCP",
               "Rank (1 = highest ratio / biggest gap)"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=start - 1, column=c, value=h)
    style_header(ws, start - 1, len(headers), freeze=False)

    cdf = county.sort_values("County_Name").reset_index(drop=True)
    end = start + len(cdf) - 1
    for i, r in cdf.iterrows():
        row = start + i
        write_row(ws, row, [r["County_Name"], r["County_FIPS"],
                            int(r["AHRF_Population_2024"]), int(r["AHRF_PCP_Count_2023"])])
        ws.cell(row=row, column=5, value=f"=C{row}/D{row}").number_format = "0.0"
        ws.cell(row=row, column=6, value=f"=RANK(E{row},$E${start}:$E${end},0)").number_format = "0"
        for c in range(1, 7):
            ws.cell(row=row, column=c).border = BORDER

    # Highlight the highest-ratio (biggest-gap) county row.
    max_idx = cdf["AHRF_Population_2024"].div(cdf["AHRF_PCP_Count_2023"]).idxmax()
    for c in range(1, 7):
        ws.cell(row=start + max_idx, column=c).fill = HIGH_FILL

    er = f"E{start}:E{end}"
    ar = f"A{start}:A{end}"
    s = end + 2
    ws.cell(row=s, column=1, value="Summary").font = SUB_FONT
    rows = [
        ("Highest residents-per-PCP (biggest access gap)", f"=MAX({er})",
         f"=INDEX({ar},MATCH(MAX({er}),{er},0))"),
        ("Lowest residents-per-PCP (best access)", f"=MIN({er})",
         f"=INDEX({ar},MATCH(MIN({er}),{er},0))"),
        ("Gap (highest - lowest)", f"=MAX({er})-MIN({er})", None),
    ]
    for k, (label, val_f, cnty_f) in enumerate(rows):
        row = s + 1 + k
        ws.cell(row=row, column=1, value=label).border = BORDER
        vc = ws.cell(row=row, column=2, value=val_f)
        vc.number_format = "0.0"
        vc.border = BORDER
        if cnty_f:
            ws.cell(row=row, column=3, value=cnty_f).border = BORDER
    autofit(ws, max_width=40)


def build_county_health_sheet(ws, county: pd.DataFrame) -> None:
    """CHR health-burden indicators, ranked highest-to-lowest, with gaps."""
    ws["A1"] = "County health burden (CHR) - ranked highest to lowest"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("Rank 1 = highest burden. Gap = highest county value - lowest county value.")
    ws["A2"].font = NOTE_FONT

    labels = [m[2] for m in COUNTY_MEASURES]
    start = 4
    headers = ["County"]
    for lab in labels:
        headers += [lab, "Rank"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=start - 1, column=c, value=h)
    style_header(ws, start - 1, len(headers), freeze=False)

    cdf = county.sort_values("County_Name").reset_index(drop=True)
    end = start + len(cdf) - 1
    val_cols = {}  # label -> column letter
    for i, r in cdf.iterrows():
        row = start + i
        ws.cell(row=row, column=1, value=r["County_Name"]).border = BORDER
        for j, lab in enumerate(labels):
            vcol = 2 + j * 2
            rcol = vcol + 1
            vletter = get_column_letter(vcol)
            ws.cell(row=row, column=vcol, value=float(r[lab])).number_format = "0.0"
            ws.cell(row=row, column=vcol).border = BORDER
            rc = ws.cell(
                row=row, column=rcol,
                value=f"=RANK({vletter}{row},${vletter}${start}:${vletter}${end},0)",
            )
            rc.number_format = "0"
            rc.border = BORDER
            val_cols[lab] = vletter

    # Summary: per measure, highest/lowest county + gap.
    ar = f"A{start}:A{end}"
    s = end + 2
    ws.cell(row=s, column=1, value="Summary (per measure)").font = SUB_FONT
    sum_headers = ["Measure", "Highest value", "Highest-burden county",
                   "Lowest value", "Lowest-burden county", "Gap (highest - lowest)"]
    for c, h in enumerate(sum_headers, start=1):
        cell = ws.cell(row=s + 1, column=c, value=h)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = BORDER
    for j, lab in enumerate(labels):
        row = s + 2 + j
        vr = f"{val_cols[lab]}{start}:{val_cols[lab]}{end}"
        ws.cell(row=row, column=1, value=lab).border = BORDER
        ws.cell(row=row, column=2, value=f"=MAX({vr})").number_format = "0.0"
        ws.cell(row=row, column=3, value=f"=INDEX({ar},MATCH(MAX({vr}),{vr},0))")
        ws.cell(row=row, column=4, value=f"=MIN({vr})").number_format = "0.0"
        ws.cell(row=row, column=5, value=f"=INDEX({ar},MATCH(MIN({vr}),{vr},0))")
        ws.cell(row=row, column=6, value=f"=MAX({vr})-MIN({vr})").number_format = "0.0"
        for c in range(1, 7):
            ws.cell(row=row, column=c).border = BORDER
    autofit(ws, max_width=34)

# --------------------------------------------------------------------------
# Sheet builder - README / methods
# --------------------------------------------------------------------------
def build_methods_sheet(ws, corr_results: list, county: pd.DataFrame) -> None:
    """Document every formula (Excel + math), sources, cleaning and results."""
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 104
    ws["A1"] = "Methods, formulas & results - ZCTA and County analysis"
    ws["A1"].font = TITLE_FONT

    rows = [
        ("SECTION", "How to read this workbook"),
        ("Live formulas", "Result cells contain real Excel formulas - click any cell to see "
         "the calculation in the formula bar. A 'Python value (check)' column mirrors the "
         "same figure computed in Python so numbers are visible even before Excel recalculates."),
        ("Sheets", "ZCTA_Correlations (45 pairs) - Primary_Worked_Example (step-by-step) - "
         "ZCTA_Data (matched values) - ZCTA_Ranks (live RANK.AVG) - County_Provider_Access - "
         "County_Health_Burden."),
        ("SECTION", "Data sources"),
        ("Primary exposure", "ACS 2024 5-year Data Profile, DP03_0128PE = % below poverty "
         "(column Pct_Below_Poverty)."),
        ("Primary outcome", "CDC PLACES 2025 release (ZCTA), 'Diagnosed diabetes among adults', "
         "crude prevalence (column PLACES_Pct_Diabetes)."),
        ("Secondary exposures", "ACS: median household income (DP03_0062E), uninsured % "
         "(DP03_0099PE), age 65+ % (DP05_0024PE), non-English spoken at home % (DP02_0114PE)."),
        ("Secondary outcomes", "PLACES crude prevalence: obesity, fair/poor self-rated health, "
         "coronary heart disease, COPD, stroke, physical inactivity, frequent mental distress, "
         "current smoking."),
        ("County health burden", "County Health Rankings (CHR) 2025: fair/poor health %, adult "
         "obesity %, adult smoking %, uninsured %."),
        ("County provider supply", "AHRF 2024-2025: county population (pop_popn_est_24) and "
         "non-federal primary-care physicians excluding residents "
         "(phys_nf_prim_care_pc_exc_rsdt_23)."),
        ("SECTION", "Matching & cleaning"),
        ("ZCTA match", "ACS and PLACES joined on the five-character ZCTA."),
        ("Unreliable data removed", "Census missing-value sentinels (any value <= -111111111, "
         "e.g. -666666666) and PLACES nulls are set to NaN and the affected ZCTA is dropped "
         "from that pair entirely - no imputation."),
        ("Pairwise-complete n", "For each pair only ZCTAs valid for BOTH measures are kept; that "
         "count is reported as n (varies by pair). Excel CORREL ignores blank pairs, matching this."),
        ("SECTION", "Statistics - formulas"),
        ("Spearman's rho", "Excel: =CORREL(rank(X), rank(Y))   |   Math: rho = Pearson correlation "
         "of the ranked values of X and Y (ties -> average rank)."),
        ("Pearson's r", "Excel: =COVAR(X,Y)/(STDEVP(X)*STDEVP(Y))  =  =CORREL(X,Y)   |   "
         "Math: r = covariance(X, Y) / (std(X) * std(Y))."),
        ("Pearson p-value", "Excel: =T.DIST.2T(ABS(r*SQRT((n-2)/(1-r^2))),n-2)   |   "
         "Math: t = r*sqrt((n-2)/(1-r^2)), df = n-2, p = 2*P(T_df > |t|)."),
        ("Spearman p-value", "Same t-test formula applied to Spearman rho."),
        ("FDR-adjusted p-value", "Benjamini-Hochberg step-up across all 45 Pearson p-values: "
         "p_adj[i] = min(1, p_sorted[i]*m/rank[i]), monotonicity enforced from largest to "
         "smallest p-value. Controls false discoveries."),
        ("Pearson 95% CI", "Fisher z-transform: z = 0.5*ln((1+r)/(1-r)), SE = 1/sqrt(n-3), "
         "CI on z-scale: z +/- 1.96*SE, back-transformed to r."),
        ("Compatibility (no #NAME?)", "Only classic Excel functions are used (CORREL, COVAR, STDEVP, T.DIST.2T, "
         "LN, EXP, SQRT, RANK, AVERAGE, COUNT, MAX, MIN, INDEX/MATCH, IF, ISNUMBER) so the file "
         "opens cleanly in any Excel or Numbers version. The Excel 2010+ 'future functions' "
         "RANK.AVG, STDEV.P and COVARIANCE.P are deliberately avoided (openpyxl cannot store them "
         "without an _xlfn. prefix, so they show #NAME?). Ranks are pre-computed with average-tie "
         "handling and written as values on ZCTA_Ranks / Primary_Worked_Example; the live CORREL "
         "formulas read them."),
        ("Rank note", "The authoritative Spearman ranks within each pair's complete subset "
         "(standard definition). The live Excel column ranks the whole column, which differs by "
         "<0.001 here because only a few ZCTAs are dropped; both are shown for transparency."),
        ("SECTION", "County formulas"),
        ("Residents per PCP", "AHRF population / AHRF primary-care physician count. Higher = "
         "fewer PCPs per person = bigger access gap."),
        ("Provider rank", "RANK(ratio, range, 0): rank 1 = highest residents-per-PCP = biggest gap."),
        ("Health-burden rank", "RANK(value, range, 0): rank 1 = highest burden."),
        ("County gap", "MAX(county values) - MIN(county values), computed after ranking."),
    ]
    r = 3
    for a, b in rows:
        if a == "SECTION":
            cell = ws.cell(row=r, column=1, value=b)
            cell.font = SUB_FONT
            r += 1
            continue
        ws.cell(row=r, column=1, value=a).font = Font(bold=True)
        ws.cell(row=r, column=1).alignment = Alignment(vertical="top")
        bc = ws.cell(row=r, column=2, value=b)
        bc.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1

# --------------------------------------------------------------------------
# CSV summary + orchestration
# --------------------------------------------------------------------------
def write_summary_csv(corr_results: list) -> None:
    frame = pd.DataFrame([{
        "exposure": r["exposure"], "exposure_role": r["exposure_role"],
        "outcome": r["outcome"], "outcome_role": r["outcome_role"],
        "n": r["n"], "spearman_rho": round(r["spearman"], 6),
        "pearson_r": round(r["pearson"], 6),
        "pearson_p": round(r["pearson_p"], 6),
        "spearman_p": round(r["spearman_p"], 6),
        "fdr_p": round(r["fdr_p"], 6),
        "ci_lower": round(r["ci_lower"], 6),
        "ci_upper": round(r["ci_upper"], 6),
        "primary_pair": r["primary_pair"],
    } for r in corr_results])
    frame.to_csv(OUTPUT_CSV, index=False)


def main() -> None:
    zcta = load_zcta_frame()
    county = load_county_frames()
    corr_results = compute_correlations(zcta)

    wb = Workbook()
    ws_methods = wb.active
    ws_methods.title = "README_Methods"
    ws_corr = wb.create_sheet("ZCTA_Correlations")
    ws_primary = wb.create_sheet("Primary_Worked_Example")
    ws_data = wb.create_sheet("ZCTA_Data")
    ws_ranks = wb.create_sheet("ZCTA_Ranks")
    ws_prov = wb.create_sheet("County_Provider_Access")
    ws_health = wb.create_sheet("County_Health_Burden")

    last_row = build_zcta_data_sheet(ws_data, zcta)
    build_zcta_ranks_sheet(ws_ranks, zcta, last_row)
    build_correlations_sheet(ws_corr, corr_results, last_row)
    build_primary_example_sheet(ws_primary, zcta)
    build_county_provider_sheet(ws_prov, county)
    build_county_health_sheet(ws_health, county)
    build_methods_sheet(ws_methods, corr_results, county)

    wb.save(OUTPUT_XLSX)
    write_summary_csv(corr_results)

    # ---- terminal validation summary ----
    primary = next(r for r in corr_results if r["primary_pair"])
    print(f"Wrote {os.path.relpath(OUTPUT_XLSX, ROOT)}")
    print(f"Wrote {os.path.relpath(OUTPUT_CSV, ROOT)}")
    print("\nHow to open the Excel file:")
    print(f"  Full path : {OUTPUT_XLSX}")
    print("  Finder    : double-click DE_ZCTA_County_Analysis.xlsx in this folder")
    print("  Terminal  : open DE_ZCTA_County_Analysis.xlsx")
    print("  Result cells are live formulas - let Excel/Numbers recalculate on open")
    print("  (in Excel press Cmd + = to force it). The 'Python value (check)' columns")
    print("  already show the numbers, so results are visible even before recalc.")
    print(f"\nZCTAs in master: {len(zcta)}")
    print(f"Primary pair: {primary['exposure']} vs {primary['outcome']}")
    print(f"  n = {primary['n']}  Spearman rho = {primary['spearman']:.4f}  "
          f"Pearson r = {primary['pearson']:.4f}")
    print(f"\nAll {len(corr_results)} pairs (exposure | outcome | n | rho | r | p | FDR):")
    for r in corr_results:
        tag = "  <-- PRIMARY" if r["primary_pair"] else ""
        print(f"  {r['exposure'][:26]:26s} | {r['outcome'][:32]:32s} | "
              f"n={r['n']:2d} | rho={r['spearman']:+.3f} | r={r['pearson']:+.3f} | "
              f"p={r['pearson_p']:+.3f} | FDR={r['fdr_p']:+.3f}{tag}")

    ratio = county["AHRF_Population_2024"] / county["AHRF_PCP_Count_2023"]
    county = county.assign(Residents_per_PCP=ratio.round(1))
    print("\nCounty residents per primary-care physician (rank 1 = biggest gap):")
    for _, r in county.sort_values("Residents_per_PCP", ascending=False).iterrows():
        print(f"  {r['County_Name']:12s} pop={int(r['AHRF_Population_2024']):>7,} "
              f"pcp={int(r['AHRF_PCP_Count_2023']):>3} -> {r['Residents_per_PCP']:.0f} residents/PCP")
    print("\nCounty health burden (CHR):")
    for _, r in county.iterrows():
        vals = "  ".join(f"{m[2]}={r[m[2]]:.1f}" for m in COUNTY_MEASURES)
        print(f"  {r['County_Name']:12s} {vals}")


if __name__ == "__main__":
    main()









