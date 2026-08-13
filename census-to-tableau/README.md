# census-to-tableau

Turn ACS Data Profile CSV downloads from [data.census.gov](https://data.census.gov)
into one clean, merged spreadsheet ready to drop into Tableau as a map.

No API key needed, no Census API calls — just merges files you download by hand
through the normal data.census.gov website.

## Setup

```bash
pip install -r requirements.txt
```

## 1. Download the data (manual, ~1 min per table)

1. Go to https://data.census.gov
2. Search a table code — `DP03` (Economic), `DP02` (Social), `DP05`
   (Demographic) are the most useful starting points.
3. Left sidebar → **Geography** → pick a level (Census Tract / County / Block
   Group) → pick your state → "All [level] within [state]" → **Apply**.
4. Top right → **Download** → CSV → **Download**.
5. Unzip it. You want the file ending in `-Data.csv`
   (e.g. `ACSDP5Y2024.DP03-Data.csv`). Ignore the `-Column-Metadata.csv` and
   `-Table-Notes.txt` files unless you're hunting for a new variable code.

Repeat for each table/topic you want.

## 2. Merge them

```bash
python merge_census_data.py \
    --inputs DP03=ACSDP5Y2024.DP03-Data.csv \
             DP02=ACSDP5Y2024.DP02-Data.csv \
             DP05=ACSDP5Y2024.DP05-Data.csv \
    --output my_state_tract_data.csv
```

You get one CSV with an 11-digit `GEOID` column (matches Tableau's built-in
"Census Tract" geographic role) plus every metric you configured, cleaned and
numeric.

## 3. Change which columns you pull

Open `merge_census_data.py` and edit the `VARIABLES` dict near the top. Each
entry is `{census_column_code: friendly_output_name}`. To find new codes,
open the `-Column-Metadata.csv` file from any download and search it for a
keyword (e.g. "poverty", "insurance", "broadband", "language").

```python
VARIABLES = {
    "DP03": {
        "DP03_0062E": "Median_Household_Income",
        "DP03_0128PE": "Pct_Below_Poverty",
    },
    ...
}
```

Add a new top-level key (e.g. `"DP04"`) to pull in a table you haven't used
before — just remember to also pass it on the command line with `--inputs`.

## 4. Build the map in Tableau

1. Connect → Text File → your merged CSV.
2. In the worksheet, right-click `GEOID` in the Data pane → **Geographic
   Role** → **Census Tract**.
3. Double-click `GEOID` — the map appears.
4. Drag any `Pct_...` or numeric column onto **Color** on the Marks card.
5. Optional — to switch between metrics with one control: create a
   Parameter listing your field names, a calculated field with a `CASE`
   statement that returns the chosen field, and drop that calculated field
   on Color instead.

## Notes

- This works for any US state, not just Delaware — just change the geography
  filter in step 1.
- Works at County, Census Tract, or Block Group level — Tableau has a
  built-in geographic role for all three, as long as you keep enough of the
  GEO_ID (the script keeps the right number of digits automatically based on
  what's in the source file).
- A handful of rows may come out blank for very low-population
  tracts/block groups — that's the Census Bureau itself suppressing unreliable
  estimates, not a bug in the script.
