def main():
    gdf_boundaries = fetch_spatial_boundaries()
    df_metrics = fetch_acs_data(CENSUS_API_KEY)

    print("Merging spatial data with ACS metrics...")
    master_gdf = gdf_boundaries.merge(df_metrics, on="ZCTA", how="inner")

    print("Executing Python-side transformations and metric calculations...")
    
    # 1. Spatial area conversions
    master_gdf["Land_Area_SqMi"] = (master_gdf["ALAND"] / 2_589_988.110336).round(2)
    master_gdf["Water_Area_SqMi"] = (master_gdf["AWATER"] / 2_589_988.110336).round(2)

    # 2. Derived population counts
    master_gdf["Population_Density_SqMi"] = (
        master_gdf["Total_Population"] / master_gdf["Land_Area_SqMi"]
    ).round(1)

    master_gdf["Uninsured_Population_Count"] = (
        (master_gdf["Pct_No_Health_Insurance"] / 100) * master_gdf["Total_Population"]
    ).round(0)

    master_gdf["Poverty_Population_Count"] = (
        (master_gdf["Pct_Below_Poverty"] / 100) * master_gdf["Total_Population"]
    ).round(0)

    master_gdf["Seniors_65_Plus_Count"] = (
        (master_gdf["Pct_Age_65_Plus"] / 100) * master_gdf["Total_Population"]
    ).round(0)

    # 3. Clean remaining null sentinel codes
    numeric_cols = master_gdf.select_dtypes(include=["number"]).columns
    for col in numeric_cols:
        master_gdf[col] = master_gdf[col].apply(lambda x: pd.NA if x in NULL_CODES else x)

    # Drop spatial geometry for tabular outputs
    df_out = master_gdf.drop(columns=["geometry"])

    # 4. Export Wide CSV
    output_csv = "Delaware_ZCTA_Health_Master_Wide.csv"
    df_out.to_csv(output_csv, index=False)
    print(f"--> Saved Wide Master CSV: {output_csv} ({len(df_out)} rows)")

    # 5. Export Wide Excel (.xlsx)
    output_excel = "Delaware_ZCTA_Health_Master_Wide.xlsx"
    df_out.to_excel(output_excel, index=False, sheet_name="ZCTA_Health_Master")
    print(f"--> Saved Wide Master Excel: {output_excel}")

    # 6. Export Spatial GeoJSON for Tableau
    output_geojson = "Delaware_ZCTA_Health_Master_Spatial.geojson"
    master_gdf.to_file(output_geojson, driver="GeoJSON")
    print(f"--> Saved Master GeoJSON: {output_geojson}")


if __name__ == "__main__":
    main()