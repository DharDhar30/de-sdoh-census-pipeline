"""Generate Delaware health-data CSV files directly from official public sources.

Run once to (re)download and process:

- BRFSS_Delaware.csv <- CDC BRFSS Prevalence API (2024, Delaware, Overall)
                       https://chronicdata.cdc.gov/
- CHR_Delaware.csv   <- County Health Rankings & Roadmaps 2024 Data Document
                       https://www.countyhealthrankings.org/

Only medical / public-health indicators are kept -- no education, commute,
housing, or other socioeconomic noise.

Usage:
    python3 gen_health_data.py
"""

import io
import requests
import pandas as pd

# Official data-source URLs
BRFSS_API_URL = (
    "https://chronicdata.cdc.gov/resource/dttw-5yxu.csv"
    "?$where=locationabbr='DE' and break_out_category='Overall' and year=2024"
    "&$limit=10000"
)
CHR_XLSX_URL = (
    "https://www.countyhealthrankings.org/"
    "sites/default/files/media/document/"
    "2024_county_health_release_data_-_v1.xlsx"
)
# Legacy (retired) document URL kept for provenance — CHR removed the old
# "/sites/default/files/...2024 County Health Rankings Data Document_2024.xls"
# path during their 2025-2026 site redesign (now HTTP 404). The v1.xlsx above
# is the live replacement on the Data & Documentation page:
# https://www.countyhealthrankings.org/health-data/methodology-and-sources/data-documentation
CHR_XLSX_URL_LEGACY_RETIRED = (
    "https://www.countyhealthrankings.org/"
    "sites/default/files/media/document/"
    "2024%20County%20Health%20Rankings%20Data%20Document_2024.xls"
)
BRFSS_OUT = "BRFSS_Delaware.csv"
CHR_OUT = "CHR_Delaware.csv"
DE_COUNTY_FIPS = {"10001", "10003", "10005"}  # Kent, New Castle, Sussex

# BRFSS state-level Delaware 2024: (output column stem, question substring, exact response)
BRFSS_MEASURES = [
    ("BRFSS_Pct_Cigarette_Smoking", "Adults who are current smokers", "Yes"),
    ("BRFSS_Pct_Smoke_Every_Day", "Four Level Smoking Status", "Smoke everyday"),
    ("BRFSS_Pct_Ecigarette_Use", "Adults who are current e-cigarette users", "Current E-cigarette user"),
    ("BRFSS_Pct_Binge_Drinking", "Binge drinkers", "Yes"),
    ("BRFSS_Pct_Heavy_Drinking", "Heavy drinkers", "Meet criteria for heavy drinking"),
    ("BRFSS_Pct_Adult_Obesity", "Weight classification by Body Mass Index", "Obese (BMI 30.0 - 99.8)"),
    ("BRFSS_Pct_Adult_Overweight", "Weight classification by Body Mass Index", "Overweight (BMI 25.0-29.9)"),
    ("BRFSS_Pct_No_Physical_Activity", "During the past month, did you participate in any physical activities", "No"),
    ("BRFSS_Pct_Arthritis", "Adults who have been told they have arthritis", "Yes"),
    ("BRFSS_Pct_Current_Asthma", "Adults who have been told they currently have asthma", "Yes"),
    ("BRFSS_Pct_Ever_Asthma", "Adults who have ever been told they have asthma", "Yes"),
    ("BRFSS_Pct_COPD", "Ever told you have COPD?", "Yes"),
    ("BRFSS_Pct_Coronary_Heart_Disease", "Respondents that have ever reported having coronary heart disease", "Reported having MI or CHD"),
    ("BRFSS_Pct_Had_Stroke", "Ever told you had a stroke?", "Yes"),
    ("BRFSS_Pct_Diabetes", "Have you ever been told by a doctor that you have diabetes?", "Yes"),
    ("BRFSS_Pct_Kidney_Disease", "Ever told you have kidney disease?", "Yes"),
    ("BRFSS_Pct_Depression", "Ever told you that you have a form of depression?", "Yes"),
    ("BRFSS_Pct_Skin_Cancer", "Ever told you had skin cancer?", "Yes"),
    ("BRFSS_Pct_Other_Cancer", "Ever told you had any other types of cancer?", "Yes"),
    ("BRFSS_Pct_Fair_Poor_Health", "Health Status", "Fair or Poor Health"),
    ("BRFSS_Pct_Frequent_Mental_Distress", "Days when mental health status not good", "14+ days when mental health not good"),
    ("BRFSS_Pct_Frequent_Physical_Distress", "Days when physical health status not good", "14+ days when physical health not good"),
    ("BRFSS_Pct_Uninsured", "Adults who had some form of health insurance", "Do not have some form of health insurance"),
    ("BRFSS_Pct_Uninsured_18_64", "Adults aged 18-64 who have any kind of health care coverage", "Do not have some form of health insurance"),
    ("BRFSS_Pct_Cost_Barrier_Medical_Care", "Was there a time in the past 12 months when you needed to see a doctor", "Yes"),
    ("BRFSS_Pct_No_Personal_Doctor", "Do you have one person (or a group of doctors)", "No"),
    ("BRFSS_Pct_Routine_Checkup_Past_Year", "About how long has it been since you last visited a doctor for a routine checkup?", "Within the past year"),
    ("BRFSS_Pct_Colorectal_Screening_45_75", "Respondents aged 45-75 who have fully met the USPSTF recommendation", "Received one or more of the recommended CRC tests within the recommended time interval"),
    ("BRFSS_Pct_Mammography_40_74", "Women aged 40-74 who have had a mammogram within the past two years", "Received a mammogram within the past 2 years"),
    ("BRFSS_Pct_Flu_Vaccinated_65_Plus", "Adults aged 65+ who have had a flu shot within the past year", "Yes"),
    ("BRFSS_Pct_Pneumonia_Vaccinated_65_Plus", "Adults aged 65+ who have ever had a pneumonia vaccination", "Yes"),
    ("BRFSS_Pct_HIV_Tested_Ever", "Have you ever been tested for HIV?", "Yes"),
    ("BRFSS_Pct_Permanent_Teeth_Removed", "Adults that have had any permanent teeth extracted", "Yes"),
    ("BRFSS_Pct_All_Teeth_Removed_65_Plus", "Adults aged 65+ who have had all their natural teeth extracted", "Yes"),
    ("BRFSS_Pct_Walking_Difficulty", "Do you have serious difficulty walking or climbing stairs?", "Yes"),
    ("BRFSS_Pct_Seeing_Difficulty", "Are you blind or do you have serious difficulty seeing", "Yes"),
    ("BRFSS_Pct_Cognitive_Difficulty", "Do you have serious difficulty concentrating, remembering, or making decisions?", "Yes"),
]


def build_brfss() -> pd.DataFrame:
    """Download Delaware 2024 BRFSS Overall-prevalence CSV from the CDC API
    and extract state-level percentages with sample sizes + 95% CIs."""
    print("Downloading CDC BRFSS 2024 Delaware prevalence from official API...")
    resp = requests.get(BRFSS_API_URL, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.lower() for c in df.columns]
    out = {"State": "Delaware", "BRFSS_Year": 2024}
    problems = []
    for name, qsub, resp_exact in BRFSS_MEASURES:
        qmask = df["question"].fillna("").astype(str).str.contains(qsub, case=False, regex=False)
        rmask = df["response"].fillna("").astype(str).str.strip().str.lower().eq(resp_exact.lower())
        hits = df[qmask & rmask]
        if len(hits) != 1:
            problems.append((name, len(hits)))
            continue
        row = hits.iloc[0]
        out[f"{name}_Sample_Size"] = int(row["sample_size"])
        for suffix, src in (
            ("", "data_value"),
            ("_CI_Low", "confidence_limit_low"),
            ("_CI_High", "confidence_limit_high"),
        ):
            out[f"{name}{suffix}"] = round(float(row[src]), 1)
    if problems:
        raise ValueError(f"BRFSS API extract incomplete for: {problems}")
    return pd.DataFrame([out])


# CHR: output-column -> source-column-name inside the "Select Measure Data"
# sheet of the 2024 County Health Release workbook (v1.xlsx). The retired
# "Ranked Measure Data" layout used different header text (e.g. lowercase
# "Fair or poor health__%", "Smoking__%", quartile columns) and no longer
# exists upstream; quartile columns were dropped from the release file, so
# those outputs are now NaN (schema preserved for downstream consumers).
CHR_TARGETS = {
    "Pct_Poor_Fair_Health": "Poor or Fair Health__% Fair or Poor Health",
    "Pct_Poor_Fair_Health_LowCI": "Poor or Fair Health__95% CI - Low",
    "Pct_Poor_Fair_Health_HighCI": "Poor or Fair Health__95% CI - High",
    "Pct_Poor_Fair_Health_Quartile": "__QUARTILE_DROPPED__",
    "Avg_Poor_Physical_Health_Days": "Poor Physical Health Days__Average Number of Physically Unhealthy Days",
    "Avg_Poor_Physical_Health_Days_LowCI": "Poor Physical Health Days__95% CI - Low",
    "Avg_Poor_Physical_Health_Days_HighCI": "Poor Physical Health Days__95% CI - High",
    "Avg_Poor_Physical_Health_Days_Quartile": "__QUARTILE_DROPPED__",
    "Avg_Poor_Mental_Health_Days": "Poor Mental Health Days__Average Number of Mentally Unhealthy Days",
    "Avg_Poor_Mental_Health_Days_LowCI": "Poor Mental Health Days__95% CI - Low",
    "Avg_Poor_Mental_Health_Days_HighCI": "Poor Mental Health Days__95% CI - High",
    "Avg_Poor_Mental_Health_Days_Quartile": "__QUARTILE_DROPPED__",
    "CHR_YPLL_Rate": "Premature Death__Years of Potential Life Lost Rate",
    "CHR_Premature_Deaths_Count": "Premature Death__Deaths",
    "CHR_Pct_Low_Birthweight": "Low Birthweight__% Low Birthweight",
    "CHR_Pct_Low_Birthweight_Quartile": "__QUARTILE_DROPPED__",
    "Pct_Adult_Smoking": "Adult Smoking__% Adults Reporting Currently Smoking",
    "Pct_Adult_Smoking_LowCI": "Adult Smoking__95% CI - Low",
    "Pct_Adult_Smoking_HighCI": "Adult Smoking__95% CI - High",
    "Pct_Adult_Smoking_Quartile": "__QUARTILE_DROPPED__",
    "Pct_Adult_Obesity": "Adult Obesity__% Adults with Obesity",
    "Pct_Adult_Obesity_LowCI": "Adult Obesity__95% CI - Low",
    "Pct_Adult_Obesity_HighCI": "Adult Obesity__95% CI - High",
    "Pct_Adult_Obesity_Quartile": "__QUARTILE_DROPPED__",
    "Pct_Physical_Inactivity": "Physical Inactivity__% Physically Inactive",
    "Pct_Physical_Inactivity_LowCI": "Physical Inactivity__95% CI - Low",
    "Pct_Physical_Inactivity_HighCI": "Physical Inactivity__95% CI - High",
    "Pct_Physical_Inactivity_Quartile": "__QUARTILE_DROPPED__",
    "Excessive_Drinking_Pct": "Excessive Drinking__% Excessive Drinking",
    "Excessive_Drinking_Pct_LowCI": "Excessive Drinking__95% CI - Low",
    "Excessive_Drinking_Pct_HighCI": "Excessive Drinking__95% CI - High",
    "Excessive_Drinking_Pct_Quartile": "__QUARTILE_DROPPED__",
    "CHR_Food_Environment_Index": "Food Environment Index__Food Environment Index",
    "CHR_Access_Exercise_Opportunities_Pct": "Access to Exercise Opportunities__% With Access to Exercise Opportunities",
    "CHR_Alcohol_Impaired_Driving_Deaths_Pct": "Alcohol-Impaired Driving Deaths__% Driving Deaths with Alcohol Involvement",
    "CHR_STI_Chlamydia_Rate": "Sexually Transmitted Infections__Chlamydia Rate",
    "CHR_Teen_Birth_Rate": "Teen Births__Teen Birth Rate",
    "CHR_Uninsured_Pct": "Uninsured__% Uninsured",
    "CHR_Uninsured_Pct_LowCI": "Uninsured__95% CI - Low",
    "CHR_Uninsured_Pct_HighCI": "Uninsured__95% CI - High",
    "CHR_Uninsured_Pct_Quartile": "__QUARTILE_DROPPED__",
    "CHR_PCP_Ratio_Population": "Primary Care Physicians__Primary Care Physicians Ratio",
    "Dentist_Ratio_Population": "Dentists__Dentist Ratio",
    "Mental_Health_Provider_Ratio": "Mental Health Providers__Mental Health Provider Ratio",
    "CHR_Preventable_Hospital_Stays_Rate": "Preventable Hospital Stays__Preventable Hospitalization Rate",
    "CHR_Mammography_Screening_Pct": "Mammography Screening__% with Annual Mammogram",
    "CHR_Mammography_Screening_Pct_Quartile": "__QUARTILE_DROPPED__",
    "CHR_Flu_Vaccination_Pct": "Flu Vaccinations__% Vaccinated",
    "CHR_Flu_Vaccination_Pct_Quartile": "__QUARTILE_DROPPED__",
    }


def _parse_chr_value(val):
    """CHR provider ratios ship as '2152:1' strings; convert to population count."""
    if isinstance(val, str) and ":" in val:
        try:
            return float(val.split(":")[0])
        except ValueError:
            return float("nan")
    return pd.to_numeric(val, errors="coerce")


def build_chr() -> pd.DataFrame:
    """Download the County Health Rankings 2024 release workbook from the
    official website, extract Delaware county-level medical / public-health
    measures from the "Select Measure Data" sheet."""
    print("Downloading 2024 County Health Rankings workbook from official site...")
    resp = requests.get(CHR_XLSX_URL, timeout=180)
    resp.raise_for_status()
    xl = pd.ExcelFile(io.BytesIO(resp.content))
    raw = xl.parse("Select Measure Data", header=None)
    hdr0 = raw.iloc[0].ffill()
    hdr1 = raw.iloc[1]
    cols = ["FIPS", "State", "County"]
    for j in range(3, raw.shape[1]):
        cols.append(f"{hdr0.iloc[j]}__{hdr1.iloc[j]}")
    body = raw.iloc[2:].copy()
    body.columns = cols
    live_targets = {v for v in CHR_TARGETS.values() if not v.startswith("__")}
    missing = [v for v in live_targets if v not in body.columns]
    if missing:
        print("CHR MISSING columns:", missing)
        raise SystemExit(1)
    de = body[body["State"].fillna("").astype(str).str.strip().eq("Delaware")].copy()
    de = de[de["FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5).isin(DE_COUNTY_FIPS)]
    out = pd.DataFrame(
        {"County_FIPS": de["FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5), "County_Name": de["County"].str.strip()}
    )
    for out_col, src in CHR_TARGETS.items():
        if src.startswith("__"):
            out[out_col] = float("nan")  # dropped from release file; keep schema
        else:
            out[out_col] = de[src].map(_parse_chr_value)
    out["CHR_Data_Year"] = 2022
    return out


if __name__ == "__main__":
    brfss = build_brfss()
    brfss.to_csv(BRFSS_OUT, index=False)
    print(f"Wrote {BRFSS_OUT}  shape={brfss.shape}")

    chr_df = build_chr()
    chr_df.to_csv(CHR_OUT, index=False)
    print(f"Wrote {CHR_OUT}  shape={chr_df.shape}")

    print(f"\nBRFSS: {len(brfss.columns)} columns, {len(BRFSS_MEASURES)} measures x 4")
    print(f"CHR:   {len(chr_df.columns)} columns, {len(chr_df)} Delaware counties")
    print("\nSample CHR provider ratios:")
    print(chr_df[["County_FIPS", "County_Name", "Dentist_Ratio_Population",
                  "CHR_PCP_Ratio_Population", "Mental_Health_Provider_Ratio"]].to_string())
