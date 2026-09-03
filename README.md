# Delaware SDOH & Census Health Data Pipeline

An automated Python ETL pipeline designed to extract, transform, and merge Delaware Social Determinants of Health (SDOH), Census ACS demographics, CDC BRFSS public-health indicators, and County Health Rankings (CHR) at the ZIP Code Tabulation Area (ZCTA) level.

The pipeline outputs ready-to-use tabular and spatial datasets specifically formatted for interactive mapping in Tableau, ArcGIS, and QGIS.

## Features

- Automated Spatial Extraction: Downloads official U.S. Census Bureau cartographic boundary files via pygris and clips boundaries specifically to Delaware ZCTAs.
- Census ACS Integration: Pulls 5-Year ACS Data Profile metrics (poverty, broadband, insurance, median income, age, language) directly via the Census API.
- CDC BRFSS (Public Health): Merges real CDC Behavioral Risk Factor Surveillance System 2024 state-level prevalence for Delaware - chronic disease (diabetes, asthma, COPD, heart disease, cancer, arthritis, kidney disease), risk behaviors (smoking, vaping, binge/heavy drinking, obesity, physical inactivity), health-care access (uninsured, cost barriers, routine checkups), screenings (mammogram, colorectal, flu/pneumonia vaccination), oral health, and disability. Each measure includes its sample size and 95% confidence interval.
- County Health Rankings (CHR): Merges medical / public-health indicators across Delaware's 3 counties (New Castle, Kent, Sussex) - health outcomes (poor/fair health, premature death, low birth weight, STIs, teen births), health behaviors (smoking, obesity, inactivity, excessive drinking, food environment, exercise access, alcohol-impaired driving deaths), and clinical care (uninsured, provider ratios, preventable hospital stays, screening & vaccination rates).
- Automated Transformations: Computes derived population counts and land density metrics directly in Python.
- Multi-Format Export: Generates wide-format outputs in CSV, Excel, and spatial GeoJSON formats simultaneously.

## Project Structure

- extract_census.py: Main ETL Pipeline Script (merges spatial, ACS, BRFSS, CHR, and calculated metrics)
- gen_health_data.py: Downloads BRFSS (CDC API) and CHR (County Health Rankings website) CSV files from official sources
- BRFSS_Delaware.csv: CDC BRFSS 2024 Delaware state-level prevalence (public-health measures)
- CHR_Delaware.csv: County Health Rankings 2022 medical/public-health indicators
- .env: API key configuration
- requirements.txt: Python dependencies
- Delaware_ZCTA_Health_Master_Spatial.geojson: Master Spatial GeoJSON for Tableau

## Installation & Local Execution Instructions

Run the following exact terminal commands from your terminal to run the pipeline and interactive UI locally:

```bash
# 1. Clone the repository
git clone https://github.com/DharDhar30/de-sdoh-census-pipeline.git
cd de-sdoh-census-pipeline

# 2. Set up virtual environment and install Python dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure API key (optional but recommended for Census API rate limits)
# Create a .env file in the root directory with:
# CENSUS_API_KEY="your_census_api_key_here"

# 4. (Optional) Re-download BRFSS & CHR data from official sources:
python3 gen_health_data.py

# 5. Run the master ETL pipeline script
python3 extract_census.py
```

### Interactive UI (Streamlit)

```bash
# 6. Launch the Streamlit UI locally
streamlit run app.py
```

Or use the provided shortcut script:
```bash
bash start_ui.sh
```

Then open the URL printed by Streamlit (default http://localhost:8501).

## Sector Export UI Usage

1. Launch the UI with `streamlit run app.py` (or `bash start_ui.sh`).
2. Click "Run ETL & Refresh Data" to regenerate data, or upload your own Excel/CSV.
3. Select the sectors you want (Demographics, Socioeconomic, Health Access, BRFSS (State Level), CHR - Health Outcomes, CHR - Health Behaviors, CHR - Clinical Care, Calculated Metrics, Geographic) and refine individual columns as needed.
4. Preview the result in the interactive table, then export as an Excel workbook with one sheet per sector, separate per-sector CSV/Excel files, or a single combined file.

Exports are saved in `./exports/` so your workspace stays clean.

## Derived Metrics & Formulas

- Population Density: Total Population / Land Area (Sq. Miles)
- Uninsured Population Volume: (Pct No Health Insurance / 100) * Total Population
- Poverty Population Volume: (Pct Below Poverty / 100) * Total Population
- Senior Population Volume: (Pct Age 65 Plus / 100) * Total Population

## Pipeline Output Schema

- Geographic: ZCTA, County_FIPS, County_Name (5-digit ZCTA and spatial county linkage)
- Demographics: Total_Population, Median_Age, Pct_Age_65_Plus (ACS population & age breakdown)
- Socioeconomic: Median_Household_Income, Pct_Below_Poverty (Economic prosperity indicators)
- Health Access: Pct_No_Health_Insurance, Pct_Broadband_Internet (Essential infrastructure access)
- BRFSS (State Level): CDC BRFSS 2024 Delaware prevalence - smoking, vaping, binge/heavy drinking, obesity, physical inactivity, arthritis, asthma, COPD, heart disease, stroke, diabetes, kidney disease, depression, cancer, fair/poor health, mental/physical distress, uninsured, cost barriers, checkups, colorectal & mammography screening, flu & pneumonia vaccination, HIV testing, oral health, and disability indicators (each with sample size + 95% CI)
- CHR - Health Outcomes: Pct_Poor_Fair_Health, Avg Poor Physical/Mental Health Days, CHR_YPLL_Rate, CHR_Pct_Low_Birthweight, CHR_STI_Chlamydia_Rate, CHR_Teen_Birth_Rate
- CHR - Health Behaviors: Pct_Adult_Smoking, Pct_Adult_Obesity, Pct_Physical_Inactivity, Excessive_Drinking_Pct, CHR_Food_Environment_Index, CHR_Access_Exercise_Opportunities_Pct, CHR_Alcohol_Impaired_Driving_Deaths_Pct
- CHR - Clinical Care: CHR_Uninsured_Pct, CHR_PCP_Ratio_Population, Dentist_Ratio_Population, Mental_Health_Provider_Ratio, CHR_Preventable_Hospital_Stays_Rate, CHR_Mammography_Screening_Pct, CHR_Flu_Vaccination_Pct
- Calculated Metrics: Population_Density_SqMi, Uninsured_Population_Count, No_Broadband_Households_Estimate (Derived volume & density counts)

## Tableau Visualization Guide

1. Open Tableau and select Connect -> Spatial File.
2. Select Delaware_ZCTA_Health_Master_Spatial.geojson.
3. Open a new Worksheet and double-click Geometry.
4. Drag Zcta (or Zcta5Ce20) onto Detail on the Marks Card to display individual ZIP code boundaries.
5. Drag any health metric onto Color.

## Troubleshooting

- Tableau Field Mismatches Warning Icons: If red exclamation marks appear on fields when opening Tableau, clear all existing worksheet fields, navigate to Data Sources, and ensure Delaware_ZCTA_Health_Master_Spatial.geojson is selected as the active primary source.
- Missing Geometry Fields in CSV Exports: The tabular CSV and Excel outputs drop spatial polygon geometry by design to optimize file sizes for analytical spreadsheets. To build polygon maps, always connect directly to the generated .geojson spatial file.
- Census API Rate Limits: If running bulk extractions repeatedly, populate your CENSUS_API_KEY in the .env file to prevent Census API request throttling.
