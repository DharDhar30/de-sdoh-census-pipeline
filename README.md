# Delaware SDOH & Census Health Data Pipeline

An automated Python ETL pipeline designed to extract, transform, and merge Delaware Social Determinants of Health (SDOH), Census ACS demographics, and County Health Rankings (CHR) at the ZIP Code Tabulation Area (ZCTA) level.

The pipeline outputs ready-to-use tabular and spatial datasets specifically formatted for interactive mapping in Tableau, ArcGIS, and QGIS.

## Features

- Automated Spatial Extraction: Downloads official U.S. Census Bureau cartographic boundary files via pygris and clips boundaries specifically to Delaware ZCTAs.
- Census ACS Integration: Pulls 5-Year ACS Data Profile metrics (poverty, broadband, insurance, median income, age, language) directly via the Census API.
- County Health Rankings (CHR): Merges physical, dental, and behavioral health indicators across Delaware's 3 counties (New Castle, Kent, Sussex).
- Automated Transformations: Computes derived population counts and land density metrics directly in Python.
- Multi-Format Export: Generates wide-format outputs in CSV, Excel, and spatial GeoJSON formats simultaneously.

## Project Structure

- extract_census.py: Main ETL Pipeline Script
- CHR_Delaware.csv: County Health Rankings dataset
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

# 4. Run the master ETL pipeline script
python3 extract_census.py
```

### Option A: Streamlit UI (Python)

```bash
# 5a. Launch the Streamlit UI locally
streamlit run app.py
```

Or use the provided shortcut script:
```bash
bash start_ui.sh
```

### Option B: React + Flask UI (modern web app)

```bash
# 5b. Install the React frontend dependencies
cd frontend
npm install
cd ..

# 6b. Launch both the React frontend (port 3000) and Flask API backend (port 5001)
bash start_react.sh
```

Or run them in two separate terminal windows:

```bash
# Terminal 1 - Flask API backend
source venv/bin/activate
python3 api.py

# Terminal 2 - React frontend
cd frontend
npm start
```

Then open http://localhost:3000 in your browser. The React app proxies `/api` requests to the Flask backend on port 5001, so the two services talk to each other automatically.

## Sector Export UI Usage

1. Launch the UI (either the Streamlit app with `streamlit run app.py`, or the React app with `bash start_react.sh`).
2. Click "Run ETL & Refresh Data" to regenerate data, or upload your own Excel/CSV.
3. Select the sectors you want (Demographics, Socioeconomic, Health Access, CHR - Physical Health, CHR - Dental Care, CHR - Behavioral Health, Calculated, Geographic) and refine individual columns as needed.
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
- Physical Health: Pct_Poor_Fair_Health, Pct_Adult_Obesity (Overall health outcome metrics)
- Dental Care: Dentist_Ratio_Population, Pct_Dental_Visit_Past_Year (Local oral healthcare provider density)
- Behavioral Health: Mental_Health_Provider_Ratio, Avg_Poor_Mental_Health_Days (Mental health coverage & distress)
- Calculated Metrics: Population_Density_SqMi, Uninsured_Population_Count (Derived volume & density counts)

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
- Port 5000 is busy on macOS (AirPlay Receiver): The React/Flask app deliberately uses port 5001 for the Flask API backend to avoid the macOS ControlCenter conflict. If port 5001 is also busy, change `port=5001` in `api.py` and the `"proxy"` value in `frontend/package.json` to a free port.
- React frontend shows "No dataset loaded": Make sure the Flask backend (`python3 api.py`) is running on port 5001 before opening http://localhost:3000, or run `bash start_react.sh` to start both together.
