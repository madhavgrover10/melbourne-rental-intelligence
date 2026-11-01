-- Melbourne Rental & Liveability Intelligence — analysis queries
-- Run any query:  sqlite3 -header -column data/melbourne.db < scripts/03_analysis_queries.sql
-- Data: DFFH rent (Sep 2025), ABS Census 2021 income, Transport Victoria station entries FY24-25.
-- Note: rent is 2025 and income is 2021, so rent_to_income_pct is a RELATIVE comparison between areas.

-- Q1. Which areas are the most expensive to rent?
SELECT area_name, median_rent, lease_count
FROM area_summary
ORDER BY median_rent DESC
LIMIT 10;

-- Q2. Where have rents grown fastest over 5 years (Sep 2020 -> Sep 2025)?
SELECT area_name, median_rent, rent_growth_5y_pct
FROM area_summary
ORDER BY rent_growth_5y_pct DESC
LIMIT 10;

-- Q3. Where does rent take the biggest share of household income?
SELECT area_name, median_rent, hhd_income_weekly, rent_to_income_pct
FROM area_summary
WHERE hhd_income_weekly IS NOT NULL
ORDER BY rent_to_income_pct DESC
LIMIT 10;

-- Q4. Areas in BOTH the top-20 for rent growth AND the top-20 for rent-to-income (CTEs + JOIN).
WITH growth AS (
    SELECT area_name FROM area_summary ORDER BY rent_growth_5y_pct DESC LIMIT 20
), burden AS (
    SELECT area_name FROM area_summary WHERE hhd_income_weekly IS NOT NULL
    ORDER BY rent_to_income_pct DESC LIMIT 20
)
SELECT g.area_name, s.median_rent, s.rent_growth_5y_pct, s.rent_to_income_pct
FROM growth g
JOIN burden b USING (area_name)
JOIN area_summary s USING (area_name)
ORDER BY s.rent_growth_5y_pct DESC;

-- Q5. Cheapest areas within each region (window function: RANK over a partition).
SELECT region, area_name, median_rent, region_rank
FROM (
    SELECT region, area_name, median_rent,
           RANK() OVER (PARTITION BY region ORDER BY median_rent ASC) AS region_rank
    FROM area_summary
)
WHERE region_rank <= 2
ORDER BY region, region_rank;

-- Q6. "Value picks": rent below the all-area average AND above-average train access (subqueries).
SELECT area_name, region, median_rent, stations, station_entries
FROM area_summary
WHERE median_rent < (SELECT AVG(median_rent) FROM area_summary)
  AND station_entries > (SELECT AVG(station_entries) FROM area_summary WHERE station_entries > 0)
ORDER BY median_rent ASC;

-- Q7. Rent trend for one area over time (Richmond-Burnley, all properties, each September).
SELECT r.period_end, r.median_rent,
       r.median_rent - LAG(r.median_rent) OVER (ORDER BY r.period_end) AS change_vs_prev_year
FROM rent r
JOIN rent_area a USING (area_id)
WHERE a.area_name = 'Richmond-Burnley'
  AND r.dwelling = 'All properties'
  AND r.period_end LIKE '%-09'
ORDER BY r.period_end;
