CREATE TABLE IF NOT EXISTS suburbs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    postcode TEXT,
    latitude REAL,
    longitude REAL,
    area_sqkm REAL
);

CREATE TABLE IF NOT EXISTS listings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    suburb_id     INTEGER NOT NULL,
    price_weekly  REAL,
    bedrooms      INTEGER,
    bathrooms     INTEGER,
    property_type TEXT,
    address       TEXT,
    description   TEXT,
    listing_url   TEXT,
    source        TEXT DEFAULT 'domain',
    scraped_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (suburb_id) REFERENCES suburbs(id)
);

CREATE TABLE IF NOT EXISTS transit_performance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    suburb_id     INTEGER NOT NULL,
    line_name     TEXT NOT NULL,
    station_name  TEXT NOT NULL,
    on_time_pct   REAL,
    avg_delay_min REAL,
    period        TEXT,
    FOREIGN KEY (suburb_id) REFERENCES suburbs(id)
);

CREATE TABLE IF NOT EXISTS amenities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    suburb_id     INTEGER NOT NULL,
    amenity_type  TEXT NOT NULL,
    count         INTEGER DEFAULT 0,
    FOREIGN KEY (suburb_id) REFERENCES suburbs(id),
    UNIQUE(suburb_id, amenity_type)
);

CREATE TABLE IF NOT EXISTS income (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    suburb_id               INTEGER NOT NULL,
    median_household_weekly REAL,
    median_personal_weekly  REAL,
    census_year             INTEGER DEFAULT 2021,
    FOREIGN KEY (suburb_id) REFERENCES suburbs(id),
    UNIQUE(suburb_id, census_year)
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_suburbs_name ON suburbs(name);
CREATE INDEX IF NOT EXISTS idx_listings_suburb ON listings(suburb_id);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_weekly);
CREATE INDEX IF NOT EXISTS idx_listings_bedrooms ON listings(bedrooms);
CREATE INDEX IF NOT EXISTS idx_transit_suburb ON transit_performance(suburb_id);
CREATE INDEX IF NOT EXISTS idx_transit_line ON transit_performance(line_name);
CREATE INDEX IF NOT EXISTS idx_amenities_suburb ON amenities(suburb_id);
CREATE INDEX IF NOT EXISTS idx_income_suburb ON income(suburb_id);

-- Views
CREATE VIEW IF NOT EXISTS suburb_rental_summary AS
SELECT
    s.id AS suburb_id,
    s.name AS suburb_name,
    s.postcode,
    COUNT(l.id) AS listing_count,
    ROUND(AVG(l.price_weekly), 0) AS avg_rent,
    ROUND(MIN(l.price_weekly), 0) AS min_rent,
    ROUND(MAX(l.price_weekly), 0) AS max_rent,
    ROUND(AVG(CASE WHEN l.bedrooms = 1 THEN l.price_weekly END), 0) AS avg_rent_1br,
    ROUND(AVG(CASE WHEN l.bedrooms = 2 THEN l.price_weekly END), 0) AS avg_rent_2br,
    ROUND(AVG(CASE WHEN l.bedrooms = 3 THEN l.price_weekly END), 0) AS avg_rent_3br
FROM suburbs s
LEFT JOIN listings l ON l.suburb_id = s.id
GROUP BY s.id, s.name, s.postcode;

CREATE VIEW IF NOT EXISTS suburb_transit_summary AS
SELECT
    s.id AS suburb_id,
    s.name AS suburb_name,
    COUNT(DISTINCT tp.line_name) AS train_lines_count,
    GROUP_CONCAT(DISTINCT tp.station_name) AS stations,
    ROUND(AVG(tp.on_time_pct), 1) AS avg_on_time_pct,
    ROUND(AVG(tp.avg_delay_min), 2) AS avg_delay_min
FROM suburbs s
LEFT JOIN transit_performance tp ON tp.suburb_id = s.id
GROUP BY s.id, s.name;

CREATE VIEW IF NOT EXISTS suburb_amenity_summary AS
SELECT
    s.id AS suburb_id,
    s.name AS suburb_name,
    s.area_sqkm,
    COALESCE(SUM(a.count), 0) AS total_amenities,
    ROUND(COALESCE(SUM(a.count), 0) * 1.0 / NULLIF(s.area_sqkm, 0), 1) AS amenity_density,
    COALESCE(SUM(CASE WHEN a.amenity_type = 'supermarket' THEN a.count END), 0) AS supermarkets,
    COALESCE(SUM(CASE WHEN a.amenity_type = 'cafe' THEN a.count END), 0) AS cafes,
    COALESCE(SUM(CASE WHEN a.amenity_type = 'park' THEN a.count END), 0) AS parks,
    COALESCE(SUM(CASE WHEN a.amenity_type = 'gym' THEN a.count END), 0) AS gyms,
    COALESCE(SUM(CASE WHEN a.amenity_type = 'pharmacy' THEN a.count END), 0) AS pharmacies,
    COALESCE(SUM(CASE WHEN a.amenity_type = 'restaurant' THEN a.count END), 0) AS restaurants
FROM suburbs s
LEFT JOIN amenities a ON a.suburb_id = s.id
GROUP BY s.id, s.name, s.area_sqkm;

CREATE VIEW IF NOT EXISTS suburb_full_summary AS
SELECT
    rs.suburb_id,
    rs.suburb_name,
    rs.postcode,
    s.latitude,
    s.longitude,
    s.area_sqkm,
    rs.listing_count,
    rs.avg_rent,
    rs.min_rent,
    rs.max_rent,
    rs.avg_rent_1br,
    rs.avg_rent_2br,
    rs.avg_rent_3br,
    i.median_household_weekly,
    ROUND(rs.avg_rent * 1.0 / NULLIF(i.median_household_weekly, 0), 3) AS rent_to_income_ratio,
    ts.train_lines_count,
    ts.avg_on_time_pct,
    ts.avg_delay_min,
    ams.total_amenities,
    ams.amenity_density,
    ams.supermarkets,
    ams.cafes,
    ams.parks,
    ams.restaurants
FROM suburb_rental_summary rs
JOIN suburbs s ON s.id = rs.suburb_id
LEFT JOIN income i ON i.suburb_id = rs.suburb_id
LEFT JOIN suburb_transit_summary ts ON ts.suburb_id = rs.suburb_id
LEFT JOIN suburb_amenity_summary ams ON ams.suburb_id = rs.suburb_id;