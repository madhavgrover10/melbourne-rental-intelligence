# Melbourne Rental Affordability

**Question:** Where in Melbourne are renters being squeezed hardest, and where have rents been rising fastest?

I combined three public datasets (rent, income and train station usage) in a SQLite database, answered the question with SQL, summarised it in Excel, and built an interactive dashboard in Tableau Public.

**Dashboard:** https://public.tableau.com/app/profile/madhav.grover/viz/MelbourneRentalAffordability/MelbourneRentalAffordabilityWhereIsRentingGettingSqueezed

**Recommendation brief:** [docs/recommendation_brief.md](docs/recommendation_brief.md)

## What I found

All figures are for the 110 rent areas in Greater Melbourne and the Mornington Peninsula (rent: Sep 2025 quarter).

- **Rents differ a lot by area.** The median weekly rent ranges from $450 to $835. The most expensive areas are Brighton East ($835), Brighton ($825) and Port Melbourne ($795).
- **Rents have risen fastest in outer areas, and slowest in some of the most expensive inner and bayside areas.** Over the five years to Sep 2025 the typical area rose 33.7%. Keilor (58.5%), Pakenham (54.3%), Dromana-Portsea (50.6%), Berwick (50.0%) and Cranbourne (48.7%) rose fastest. Brighton East (14.4%) and Brighton (20.8%) rose slowest.
- **Lower-income areas saw faster rent growth.** Across 109 areas, household income (2021 Census) and 5-year rent growth have a correlation of -0.52. This is a pattern in the data, not proof of cause.
- **34 of 110 areas are "squeezed"**, which I define as both 5-year rent growth and rent-to-income at or above the all-area averages (35.2% and 31.8%). They are concentrated in the south-east: 7 of 8 areas in South Eastern Melbourne and all 5 on the Mornington Peninsula, against 3 of 22 in Inner Melbourne and 0 of 12 in Outer Western Melbourne.
- **Nine areas appear in both the top 20 for rent growth and the top 20 for rent-to-income**, including Dandenong, Frankston, Cranbourne and Dromana-Portsea.

### What this suggests, and what it doesn't
It suggests that rental pressure may have shifted towards lower-income areas in the outer south-east, which would make them the places to watch for affordability problems. It does **not** show why rents rose, and it does not measure the true rent burden for individual households (see the limits below).

## Data

| Data | Source | Used for |
|---|---|---|
| Moving annual median rent by suburb and town, Mar 2000 to Sep 2025 | Victorian Department of Families, Fairness and Housing, Rental Report | Rent level and growth |
| Median household income and population, 2021 | ABS 2021 Census General Community Profile (G01, G02), Suburbs and Localities, Victoria | Rent-to-income |
| Annual metropolitan train station entries, FY2024-25 | Transport Victoria open data (CC BY 4.0) | Train access (SQL only) |

## How it works

1. `scripts/02_load_data.py` loads the three files into `data/melbourne.db` (SQLite). The schema is in `scripts/01_create_schema.sql`.
2. The rent file groups some suburbs (for example "Richmond-Burnley"). I matched each group to its ABS suburbs, using a few manual aliases (for example "West St Kilda" to "St Kilda West"). Income for a grouped area is the population-weighted average of its suburbs' medians.
3. Stations are matched to areas by name, or by the nearest already-matched station within 2.5 km.
4. `scripts/03_analysis_queries.sql` holds seven documented queries (joins, CTEs, window functions with `RANK` and `LAG`, subqueries).
5. `scripts/03_export_for_dashboard.py` exports CSVs for Tableau.
6. `excel/Melbourne_Rental_Affordability_Summary.xlsx` has a region summary, a top-10 list, a what-if scenario (what happens to affordability if rents rise by a chosen percentage), and a pivot table.

## Limits

- **Time mismatch:** rent is Sep 2025 but income is from the 2021 Census. Rent-to-income only compares areas against each other; it is not a true current rent burden.
- **Grouped areas:** income for a group of suburbs is an approximation (a weighted average of medians, not a true median).
- **Student areas:** Box Hill, Carlton-Parkville, the CBD and Clayton have low household incomes because many residents are students, so they look worse than they are.
- **Averages:** region averages are simple averages across areas, not weighted by population or leases.
- **Missing data:** Yarra Ranges has no income figure and is left out of the rent-to-income analysis. 31 of the 222 stations (mostly outer ones) could not be placed in a rent area, and 90 were placed using the nearest-station rule.
- **No cause:** the data shows where rents rose, not why.

## Run it yourself

```
pip install openpyxl
python3 scripts/02_load_data.py
sqlite3 -header -column data/melbourne.db < scripts/03_analysis_queries.sql
python3 scripts/03_export_for_dashboard.py
```

## Possible next steps

- Add amenity counts (cafes, parks, supermarkets) from OpenStreetMap.
- Add an LLM-written plain-English summary for each area, restricted to numbers in the database.
- Update income when the next Census data is released.

## History

An earlier version of this project used generated listings and hand-typed income and transit figures. I replaced all of those with the real public data above. The earlier version is still in the git history.
