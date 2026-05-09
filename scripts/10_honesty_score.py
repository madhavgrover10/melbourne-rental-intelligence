import sqlite3
import os
import json
import logging

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Amenity claim → OSM amenity_type mapping
# If a listing claims "near cafes", we check OSM cafe count
# -------------------------------------------------------------------
CLAIM_TO_OSM = {
    "cafe":         "cafe",
    "coffee":       "cafe",
    "restaurant":   "restaurant",
    "dining":       "restaurant",
    "shop":         "supermarket",
    "supermarket":  "supermarket",
    "park":         "park",
    "gym":          "gym",
    "school":       "school",
    "pharmacy":     "pharmacy",
    "nightlife":    "cafe",   # proxy — no bar count in OSM data
    "shopping":     "supermarket",
}

# Weights for composite honesty score (must sum to 1.0)
WEIGHTS = {
    "sentiment_score":      0.20,  # inverted VADER compound (lower sentiment = more honest)
    "superlative_density":  0.25,  # lower density = more honest
    "euphemism_rate":       0.20,  # fewer euphemisms = more honest
    "spin_rate":            0.20,  # fewer high-spin LLM classifications = more honest
    "buzzword_inflation":   0.15,  # lower claim vs reality gap = more honest
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_score_columns(conn):
    """Add scoring columns to suburbs table if not present."""
    existing = [r[1] for r in conn.execute("PRAGMA table_info(suburbs)").fetchall()]
    to_add = {
        "buzzword_inflation_score": "REAL",
        "honesty_score":            "REAL",
        "avg_sentiment_compound":   "REAL",
        "avg_superlative_density":  "REAL",
        "high_spin_rate":           "REAL",
        "euphemism_rate":           "REAL",
    }
    for col, dtype in to_add.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE suburbs ADD COLUMN {col} {dtype}")
            logger.info(f"Added column to suburbs: {col}")
    conn.commit()


def get_osm_medians(conn):
    """
    Compute median OSM amenity count per type across all suburbs.
    Used as baseline to judge whether a suburb is above/below average.
    """
    rows = conn.execute("""
        SELECT amenity_type, AVG(count) as avg_count
        FROM amenities
        GROUP BY amenity_type
    """).fetchall()
    return {r['amenity_type']: r['avg_count'] for r in rows}


def compute_buzzword_inflation(suburb_id, amenity_claims_list, osm_counts, osm_medians):
    """
    For each amenity type claimed in listings, check if OSM count is below median.
    buzzword_inflation = fraction of claims that are inflated (claim > reality).

    Returns float 0.0–1.0. Higher = more inflated.
    """
    if not amenity_claims_list or not osm_counts:
        return 0.5  # neutral if no data

    total_claims  = 0
    inflated      = 0

    for claims in amenity_claims_list:
        for claim in claims:
            osm_key = CLAIM_TO_OSM.get(claim)
            if not osm_key:
                continue
            total_claims += 1
            actual  = osm_counts.get(osm_key, 0)
            median  = osm_medians.get(osm_key, 1)
            # Inflated if suburb has below-median count for claimed amenity
            if actual < median * 0.75:
                inflated += 1

    if total_claims == 0:
        return 0.0
    return round(inflated / total_claims, 4)


def normalise(value, min_val, max_val):
    """Min-max normalise to 0–1. Returns 0.5 if range is zero."""
    if max_val == min_val:
        return 0.5
    return (value - min_val) / (max_val - min_val)


def compute_honesty_score(sentiment_norm, density_norm, euphemism_norm,
                          spin_norm, inflation_norm):
    """
    Composite honesty score. All inputs are 0–1 where 1 = most dishonest.
    Honesty score = 1 - weighted dishonesty score.
    Final score 0–1 where 1 = most honest suburb.
    """
    dishonesty = (
        WEIGHTS['sentiment_score']     * sentiment_norm  +
        WEIGHTS['superlative_density'] * density_norm    +
        WEIGHTS['euphemism_rate']      * euphemism_norm  +
        WEIGHTS['spin_rate']           * spin_norm       +
        WEIGHTS['buzzword_inflation']  * inflation_norm
    )
    return round(1.0 - dishonesty, 4)


def main():
    conn = get_db()
    ensure_score_columns(conn)

    osm_medians = get_osm_medians(conn)
    logger.info(f"OSM medians: {osm_medians}")

    # --- Fetch per-suburb aggregates ---
    suburbs = conn.execute("SELECT id, name FROM suburbs").fetchall()
    suburb_stats = {}

    for suburb in suburbs:
        sid = suburb['id']

        # Sentiment + superlative density
        sentiment_row = conn.execute("""
            SELECT
                AVG(l.sentiment_compound)  AS avg_compound,
                AVG(l.superlative_density) AS avg_density
            FROM listings l
            WHERE l.suburb_id = ?
              AND l.sentiment_compound IS NOT NULL
        """, (sid,)).fetchone()

        if not sentiment_row or sentiment_row['avg_compound'] is None:
            continue  # skip suburbs with no listings

        # Euphemism rate — avg euphemisms per listing
        euphemism_row = conn.execute("""
            SELECT AVG(n.euphemism_count) AS avg_euphemisms
            FROM nlp_features n
            JOIN listings l ON l.id = n.listing_id
            WHERE l.suburb_id = ?
        """, (sid,)).fetchone()

        # High spin rate — fraction of listings classified as high spin
        spin_row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN lf.spin_level = 'high' THEN 1 ELSE 0 END) AS high_count
            FROM llm_features lf
            JOIN listings l ON l.id = lf.listing_id
            WHERE l.suburb_id = ?
        """, (sid,)).fetchone()

        high_spin_rate = 0.0
        if spin_row and spin_row['total'] > 0:
            high_spin_rate = spin_row['high_count'] / spin_row['total']

        # Amenity claims — collect all claims across listings in this suburb
        claim_rows = conn.execute("""
            SELECT n.amenity_claims
            FROM nlp_features n
            JOIN listings l ON l.id = n.listing_id
            WHERE l.suburb_id = ?
              AND n.amenity_claims IS NOT NULL
        """, (sid,)).fetchall()

        amenity_claims_list = []
        for row in claim_rows:
            try:
                claims = json.loads(row['amenity_claims'])
                if claims:
                    amenity_claims_list.append(claims)
            except Exception:
                pass

        # OSM counts for this suburb
        osm_rows = conn.execute("""
            SELECT amenity_type, count
            FROM amenities
            WHERE suburb_id = ?
        """, (sid,)).fetchall()
        osm_counts = {r['amenity_type']: r['count'] for r in osm_rows}

        # Buzzword inflation
        inflation = compute_buzzword_inflation(
            sid, amenity_claims_list, osm_counts, osm_medians
        )

        suburb_stats[sid] = {
            "name":             suburb['name'],
            "avg_compound":     round(sentiment_row['avg_compound'], 4),
            "avg_density":      round(sentiment_row['avg_density'], 4),
            "avg_euphemisms":   round(euphemism_row['avg_euphemisms'] or 0, 4),
            "high_spin_rate":   round(high_spin_rate, 4),
            "inflation":        inflation,
        }

    if not suburb_stats:
        logger.error("No suburb stats computed — check listings and nlp_features tables")
        conn.close()
        return

    # --- Normalise each metric across all suburbs ---
    compounds   = [s['avg_compound']   for s in suburb_stats.values()]
    densities   = [s['avg_density']    for s in suburb_stats.values()]
    euphemisms  = [s['avg_euphemisms'] for s in suburb_stats.values()]
    spin_rates  = [s['high_spin_rate'] for s in suburb_stats.values()]
    inflations  = [s['inflation']      for s in suburb_stats.values()]

    def norm(val, vals):
        return normalise(val, min(vals), max(vals))

    # --- Compute and write honesty scores ---
    results = []
    for sid, stats in suburb_stats.items():
        # Higher compound = more positive = less honest → normalise and keep as-is
        sentiment_norm  = norm(stats['avg_compound'],   compounds)
        density_norm    = norm(stats['avg_density'],    densities)
        euphemism_norm  = norm(stats['avg_euphemisms'], euphemisms)
        spin_norm       = norm(stats['high_spin_rate'], spin_rates)
        inflation_norm  = norm(stats['inflation'],      inflations)

        honesty = compute_honesty_score(
            sentiment_norm, density_norm, euphemism_norm,
            spin_norm, inflation_norm
        )

        conn.execute("""
            UPDATE suburbs SET
                buzzword_inflation_score = ?,
                honesty_score            = ?,
                avg_sentiment_compound   = ?,
                avg_superlative_density  = ?,
                high_spin_rate           = ?,
                euphemism_rate           = ?
            WHERE id = ?
        """, (
            stats['inflation'],
            honesty,
            stats['avg_compound'],
            stats['avg_density'],
            stats['high_spin_rate'],
            stats['avg_euphemisms'],
            sid,
        ))
        results.append((stats['name'], honesty, stats['inflation'], stats['high_spin_rate']))

    conn.commit()
    conn.close()

    # --- Print leaderboard ---
    results.sort(key=lambda x: x[1], reverse=True)
    logger.info("Done. Suburb honesty leaderboard:")
    logger.info(f"  {'Suburb':<20} {'Honesty':>8} {'Inflation':>10} {'HighSpin':>10}")
    logger.info(f"  {'-'*52}")
    for name, honesty, inflation, spin in results[:10]:
        logger.info(f"  {name:<20} {honesty:>8.4f} {inflation:>10.4f} {spin:>10.4f}")
    logger.info("  ...")
    logger.info("Bottom 5 (most inflated):")
    for name, honesty, inflation, spin in results[-5:]:
        logger.info(f"  {name:<20} {honesty:>8.4f} {inflation:>10.4f} {spin:>10.4f}")


if __name__ == '__main__':
    main()