# Delaware ZCTA Health & Demographic Data Extractor

An automated ETL pipeline that fetches 5-year American Community Survey (ACS) demographic data from the U.S. Census Bureau API, pairs it with spatial boundaries via `pygris`, performs geographic/population calculations, and exports clean master datasets for Tableau, GIS tools, and Excel analysis.

---

## Project Architecture

           ┌────────────────────────┐
           │ U.S. Census Bureau API │
           └───────────┬────────────┘
                       │ ACS5 Profile Metrics
                       ▼
┌──────────────┐   ┌────────────────────┐   ┌─────────────────────────┐
│ pygris State │──▶│ Merge & Transform  │──▶│ Output Master Datasets  │
│ & ZCTA Map   │   │ Null Suppression   │   │ - .csv (Tabular)        │
└──────────────┘   │ Derived Metrics    │   │ - .xlsx (Excel)         │
└────────────────────┘   │ - .geojson (Spatial)    │
└─────────────────────────┘
---

## Output Metrics & Data Dictionary

| Variable Name | Source / Formula | Description |
| :--- | :--- | :--- |
| `ZCTA` | Spatial Boundary Key | 5-Digit ZIP Code Tabulation Area |
| `Total_Population` | ACS `DP05_0001E` | Total estimated population |
| `Median_Age` | ACS `DP05_0018E` | Median population age |
| `Pct_Age_65_Plus` | ACS `DP05_0024PE` | Percent of population aged 65 and older |
| `Median_Household_Income` | ACS `DP03_0062E` | Median household income ($) |
| `Pct_Below_Poverty` | ACS `DP03_0128PE` | Percent of population below poverty line |
| `Pct_No_Health_Insurance` | ACS `DP03_0099PE` | Percent of population without health insurance |
| `Pct_Commute_Public_Transit` | ACS `DP03_0021PE` | Percent of workers commuting via public transit |
| `Pct_Broadband_Internet` | ACS `DP02_0154PE` | Percent of households with broadband internet |
| `Pct_NonEnglish_Language_Home` | ACS `DP02_0114PE` | Percent speaking non-English language at home |
| `Land_Area_SqMi` | `ALAND / 2,589,988.11` | Total land area in square miles |
| `Water_Area_SqMi` | `AWATER / 2,589,988.11` | Total water area in square miles |
| `Population_Density_SqMi` | `Total_Population / Land_Area_SqMi` | Persons per square mile |
| `Uninsured_Population_Count` | `(Pct_No_Health_Insurance / 100) * Total_Population` | Calculated count of uninsured residents |
| `Poverty_Population_Count` | `(Pct_Below_Poverty / 100) * Total_Population` | Calculated count of poverty-impacted residents |
| `Seniors_65_Plus_Count` | `(Pct_Age_65_Plus / 100) * Total_Population` | Calculated count of senior residents |

---

## Prerequisites

* **Python 3.9+**
* **U.S. Census API Key** ([Request a free key here](https://api.census.gov/data/key_signup.html))

---

## Installation

1. **Clone the repository or navigate to your project folder:**
   ```bash
   cd path/to/your/project
Install required dependencies:Bashpip install geopandas pandas pygris requests python-dotenv openpyxl
Configure Environment Variables:
Create a .env file in the root directory and insert your Census API Key:Code snippetCENSUS_API_KEY=your_actual_census_api_key_here
UsageRun the primary ETL script:Bashpython3 extract_census.py
Script Execution WorkflowDownloads Delaware state boundaries and national ZCTA maps via pygris.Clips ZCTA polygons strictly to Delaware borders and removes pure-water tracts (ALAND == 0).Fetches 5-Year ACS Data Profile variables via Census REST API endpoints.Cleans sentinel/null values (-666666666, (X), N, etc.) to standard NA.Computes square mileage conversions and derived population counts.Generates 3 synchronized master outputs in the working directory:Delaware_ZCTA_Health_Master_Wide.csvDelaware_ZCTA_Health_Master_Wide.xlsxDelaware_ZCTA_Health_Master_Spatial.geojsonGenerated Files & VisualizationsFilePrimary Use Case..._Wide.csvFast tabular imports, Pandas/R analysis, Tableau Data Sources..._Wide.xlsxExecutive spreadsheet distribution & pivot tables..._Spatial.geojsonGIS mapping (QGIS, ArcGIS, Mapbox, Tableau Spatial Layers)File Verification CommandsOpen Excel on macOS:Bashopen Delaware_ZCTA_Health_Master_Wide.xlsx
Preview CSV Header:Bashhead -n 5 Delaware_ZCTA_Health_Master_Wide.csv
Note: Never run cat Delaware_ZCTA_Health_Master_Wide.xlsx directly in your terminal, as .xlsx files are compressed binary archives and will print unreadable binary output to your screen. If this happens, type reset and press Enter to restore your terminal.
<ElicitationsGroup message="To extend this project further:">

  <Elicitation label="Add interactive visualization guide for Tableau/QGIS" query="Show me how to connect the generated GeoJSON and CSV outputs to Tableau and QGIS to create a choropleth map."/>

  <Elicitation label="Add GitHub Actions automation setup" query="Write a GitHub Actions workflow YAML file to run this ETL script automatically every year."/>

</ElicitationsGroup>