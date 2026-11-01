-- Melbourne Rental & Liveability Intelligence — schema (real public data only)
-- Sources: DFFH Rental Report (rent), ABS 2021 Census GCP (income, population),
--          Transport Victoria open data (station patronage).
DROP VIEW IF EXISTS area_summary;
DROP TABLE IF EXISTS rent;
DROP TABLE IF EXISTS station;
DROP TABLE IF EXISTS area_suburb;
DROP TABLE IF EXISTS rent_area;

CREATE TABLE rent_area (
    area_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    region     TEXT NOT NULL,              -- DFFH region, e.g. 'Inner Melbourne'
    area_name  TEXT NOT NULL UNIQUE        -- DFFH area, e.g. 'Richmond-Burnley'
);

-- Which ABS suburbs make up each DFFH rent area (some areas are groups of suburbs)
CREATE TABLE area_suburb (
    area_id        INTEGER NOT NULL REFERENCES rent_area(area_id),
    abs_name       TEXT NOT NULL,          -- ABS suburb name (Vic. suffix removed)
    sal_code       TEXT,
    population     INTEGER,                -- 2021 Census persons
    median_hhd_inc_weekly INTEGER,         -- 2021 Census median household income / week (NULL if suppressed)
    match_method   TEXT NOT NULL,          -- 'exact' | 'alias'
    PRIMARY KEY (area_id, abs_name)
);

-- Long-format rent history: one row per area x dwelling type x quarter
CREATE TABLE rent (
    area_id     INTEGER NOT NULL REFERENCES rent_area(area_id),
    dwelling    TEXT NOT NULL,             -- '1 bedroom flat', ... 'All properties'
    period_end  TEXT NOT NULL,             -- 'YYYY-MM' quarter end (moving annual)
    lease_count INTEGER,
    median_rent INTEGER,                   -- dollars per week
    PRIMARY KEY (area_id, dwelling, period_end)
);

CREATE TABLE station (
    stop_id      INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    lat          REAL,
    lon          REAL,
    pax_annual   INTEGER,                  -- FY2024-25 station entries
    pax_weekday  INTEGER,
    area_id      INTEGER REFERENCES rent_area(area_id),
    match_method TEXT NOT NULL             -- 'name' | 'alias' | 'nearest' | 'unmatched'
);

CREATE INDEX idx_rent_area ON rent(area_id);
CREATE INDEX idx_rent_period ON rent(period_end);
CREATE INDEX idx_station_area ON station(area_id);

CREATE VIEW area_summary AS
WITH latest AS (
    SELECT area_id, median_rent, lease_count FROM rent
    WHERE dwelling='All properties' AND period_end='2025-09'
), yr AS (
    SELECT area_id, median_rent AS rent_1y FROM rent WHERE dwelling='All properties' AND period_end='2024-09'
), y5 AS (
    SELECT area_id, median_rent AS rent_5y FROM rent WHERE dwelling='All properties' AND period_end='2020-09'
), inc AS (
    SELECT area_id,
           SUM(population) AS population,
           ROUND(SUM(median_hhd_inc_weekly * population) * 1.0 / NULLIF(SUM(CASE WHEN median_hhd_inc_weekly IS NOT NULL THEN population END),0)) AS hhd_income_weekly
    FROM area_suburb WHERE median_hhd_inc_weekly IS NOT NULL AND population > 0
    GROUP BY area_id
), st AS (
    SELECT area_id, COUNT(*) AS stations, COALESCE(SUM(pax_annual),0) AS station_entries
    FROM station WHERE area_id IS NOT NULL GROUP BY area_id
)
SELECT a.area_id, a.region, a.area_name,
       l.median_rent, l.lease_count,
       ROUND((l.median_rent - yr.rent_1y) * 100.0 / yr.rent_1y, 1) AS rent_growth_1y_pct,
       ROUND((l.median_rent - y5.rent_5y) * 100.0 / y5.rent_5y, 1) AS rent_growth_5y_pct,
       inc.population, inc.hhd_income_weekly,
       ROUND(l.median_rent * 100.0 / inc.hhd_income_weekly, 1) AS rent_to_income_pct,
       COALESCE(st.stations,0) AS stations, COALESCE(st.station_entries,0) AS station_entries
FROM rent_area a
LEFT JOIN latest l ON l.area_id=a.area_id
LEFT JOIN yr  ON yr.area_id=a.area_id
LEFT JOIN y5  ON y5.area_id=a.area_id
LEFT JOIN inc ON inc.area_id=a.area_id
LEFT JOIN st  ON st.area_id=a.area_id;
