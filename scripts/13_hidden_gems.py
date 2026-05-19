import sqlite3
import os
import json
import logging
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'processed')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_data(conn):
    return pd.read_sql_query("""
        SELECT
            s.id                        AS suburb_id,
            s.name                      AS suburb,
            s.latitude,
            s.longitude,
            s.liveability_score,
            s.affordability_score,
            s.transit_score,
            s.walkability_score,
            s.amenity_variety_score,
            s.honesty_score,
            s.median_weekly_rent,
            s.rent_to_income_ratio,
            s.value_gap,
            s.classification,
            s.buzzword_inflation_score,
            s.high_spin_rate,
            i.median_household_weekly   AS median_income,
            a_cafe.count                AS cafe_count,
            a_park.count                AS park_count,
            a_super.count               AS supermarket_count,
            a_gym.count                 AS gym_count,
            a_school.count              AS school_count,
            t.avg_on_time_pct,
            t.avg_delay_min,
            t.train_lines_count
        FROM suburbs s
        LEFT JOIN income i ON i.suburb_id = s.id
        LEFT JOIN amenities a_cafe  ON a_cafe.suburb_id  = s.id AND a_cafe.amenity_type  = 'cafe'
        LEFT JOIN amenities a_park  ON a_park.suburb_id  = s.id AND a_park.amenity_type  = 'park'
        LEFT JOIN amenities a_super ON a_super.suburb_id = s.id AND a_super.amenity_type = 'supermarket'
        LEFT JOIN amenities a_gym   ON a_gym.suburb_id   = s.id AND a_gym.amenity_type   = 'gym'
        LEFT JOIN amenities a_school ON a_school.suburb_id = s.id AND a_school.amenity_type = 'school'
        LEFT JOIN (
            SELECT suburb_id,
                   AVG(on_time_pct)         AS avg_on_time_pct,
                   AVG(avg_delay_min)       AS avg_delay_min,
                   COUNT(DISTINCT line_name) AS train_lines_count
            FROM transit_performance
            WHERE on_time_pct > 0
            GROUP BY suburb_id
        ) t ON t.suburb_id = s.id
        WHERE s.liveability_score IS NOT NULL
        ORDER BY s.value_gap DESC
    """, conn)


def ensure_analysis_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suburb_analysis (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            suburb_id           INTEGER NOT NULL REFERENCES suburbs(id),
            classification      TEXT,
            value_gap           REAL,
            strength_factors    TEXT,   -- JSON array of what makes it good/bad
            weakness_factors    TEXT,   -- JSON array
            renter_profile      TEXT,   -- who this suburb suits
            generated_at        TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_suburb
        ON suburb_analysis(suburb_id)
    """)
    conn.commit()


def identify_strengths(row):
    """Return list of strength factors based on scores."""
    strengths = []
    if row['affordability_score'] >= 0.70:
        strengths.append(f"highly affordable (rent ${row['median_weekly_rent']:.0f}/wk)")
    if row['walkability_score'] >= 0.60:
        strengths.append("strong walkability — high amenity density")
    if row['honesty_score'] and row['honesty_score'] >= 0.65:
        strengths.append("honest listings — low marketing inflation")
    if row['cafe_count'] and row['cafe_count'] >= 20:
        strengths.append(f"vibrant cafe scene ({int(row['cafe_count'])} nearby)")
    if row['park_count'] and row['park_count'] >= 10:
        strengths.append(f"good green space ({int(row['park_count'])} parks nearby)")
    if row['school_count'] and row['school_count'] >= 5:
        strengths.append(f"well-served by schools ({int(row['school_count'])} nearby)")
    if row['avg_on_time_pct'] and row['avg_on_time_pct'] >= 87:
        strengths.append(f"reliable transit ({row['avg_on_time_pct']:.1f}% on-time)")
    return strengths


def identify_weaknesses(row):
    """Return list of weakness factors."""
    weaknesses = []
    if row['affordability_score'] < 0.30:
        weaknesses.append(f"expensive — rent ${row['median_weekly_rent']:.0f}/wk")
    if row['walkability_score'] < 0.15:
        weaknesses.append("low walkability — car-dependent area")
    if row['honesty_score'] and row['honesty_score'] < 0.40:
        weaknesses.append("high listing spin — verify amenity claims in person")
    if not row['avg_on_time_pct'] or row['avg_on_time_pct'] == 0:
        weaknesses.append("no direct train access — bus dependent")
    elif row['avg_on_time_pct'] < 82:
        weaknesses.append(f"unreliable transit ({row['avg_on_time_pct']:.1f}% on-time)")
    if row['cafe_count'] and row['cafe_count'] < 5:
        weaknesses.append("limited cafe/dining options nearby")
    if row['park_count'] and row['park_count'] < 3:
        weaknesses.append("limited green space nearby")
    if row['buzzword_inflation_score'] and row['buzzword_inflation_score'] >= 0.75:
        weaknesses.append("listings frequently overclaim amenity proximity")
    return weaknesses


def infer_renter_profile(row):
    """Infer who this suburb suits based on its profile."""
    profiles = []
    if row['affordability_score'] >= 0.70 and row['school_count'] and row['school_count'] >= 5:
        profiles.append("families seeking value")
    if row['cafe_count'] and row['cafe_count'] >= 15 and row['affordability_score'] >= 0.40:
        profiles.append("young professionals")
    if row['affordability_score'] >= 0.80:
        profiles.append("budget-conscious renters")
    if row['walkability_score'] >= 0.60 and row['cafe_count'] and row['cafe_count'] >= 10:
        profiles.append("lifestyle seekers")
    if row['avg_on_time_pct'] and row['avg_on_time_pct'] >= 87 and row['affordability_score'] >= 0.50:
        profiles.append("CBD commuters")
    if not profiles:
        profiles.append("general renters")
    return profiles


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = get_db()
    ensure_analysis_table(conn)

    df = load_data(conn)
    logger.info(f"Loaded {len(df)} suburbs for analysis")

    records = []
    for _, row in df.iterrows():
        strengths  = identify_strengths(row)
        weaknesses = identify_weaknesses(row)
        profile    = infer_renter_profile(row)

        conn.execute("""
            INSERT OR REPLACE INTO suburb_analysis
                (suburb_id, classification, value_gap,
                 strength_factors, weakness_factors, renter_profile, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            int(row['suburb_id']),
            row['classification'],
            row['value_gap'],
            json.dumps(strengths),
            json.dumps(weaknesses),
            json.dumps(profile),
        ))

        records.append({
            'suburb':         row['suburb'],
            'classification': row['classification'],
            'value_gap':      row['value_gap'],
            'liveability':    row['liveability_score'],
            'rent':           row['median_weekly_rent'],
            'strengths':      strengths,
            'weaknesses':     weaknesses,
            'renter_profile': profile,
        })

    conn.commit()
    conn.close()

    # --- Console output ---
    logger.info("\n=== TOP 5 HIDDEN GEMS ===")
    gems = [r for r in records if r['classification'] == 'hidden gem']
    gems.sort(key=lambda x: x['value_gap'], reverse=True)
    for r in gems[:5]:
        logger.info(f"\n{r['suburb']} (gap: {r['value_gap']:+.2f}, "
                    f"liveability: {r['liveability']:.1f}/10, rent: ${r['rent']:.0f}/wk)")
        logger.info(f"  Strengths:  {', '.join(r['strengths']) or 'none identified'}")
        logger.info(f"  Weaknesses: {', '.join(r['weaknesses']) or 'none identified'}")
        logger.info(f"  Suits:      {', '.join(r['renter_profile'])}")

    logger.info("\n=== TOP 5 OVERPRICED TRAPS ===")
    traps = [r for r in records if r['classification'] == 'overpriced trap']
    traps.sort(key=lambda x: x['value_gap'])
    for r in traps[:5]:
        logger.info(f"\n{r['suburb']} (gap: {r['value_gap']:+.2f}, "
                    f"liveability: {r['liveability']:.1f}/10, rent: ${r['rent']:.0f}/wk)")
        logger.info(f"  Strengths:  {', '.join(r['strengths']) or 'none identified'}")
        logger.info(f"  Weaknesses: {', '.join(r['weaknesses']) or 'none identified'}")
        logger.info(f"  Suits:      {', '.join(r['renter_profile'])}")

    # --- Export for Tableau / Streamlit ---
    export = pd.DataFrame(records)
    export.to_csv(os.path.join(OUT_DIR, 'suburb_analysis.csv'), index=False)
    logger.info(f"\nExported suburb_analysis.csv → data/processed/")


if __name__ == '__main__':
    main()