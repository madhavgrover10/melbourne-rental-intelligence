import sqlite3
import os
import pandas as pd
import numpy as np
import logging

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Liveability score weights (must sum to 1.0)
# As per roadmap: affordability 30%, transit 25%, walkability 20%,
# honesty 15%, amenity variety 10%
# -------------------------------------------------------------------
WEIGHTS = {
    'affordability':    0.30,
    'transit':          0.25,
    'walkability':      0.20,
    'honesty':          0.15,
    'amenity_variety':  0.10,
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_suburbs(conn):
    """Load all suburb-level data into a single DataFrame."""
    df = pd.read_sql_query("""
        SELECT
            s.id                        AS suburb_id,
            s.name                      AS suburb,
            s.latitude,
            s.longitude,
            s.honesty_score,
            s.buzzword_inflation_score,
            s.avg_sentiment_compound,
            s.avg_superlative_density,
            s.high_spin_rate
        FROM suburbs s
        WHERE s.latitude IS NOT NULL
    """, conn)
    return df


def load_income(conn):
    """Load median household income per suburb."""
    df = pd.read_sql_query("""
        SELECT suburb_id, median_household_weekly AS median_weekly_income
        FROM income
    """, conn)
    return df


def load_rent(conn):
    """Compute median weekly rent per suburb from listings."""
    df = pd.read_sql_query("""
        SELECT
            suburb_id,
            ROUND(AVG(price_weekly), 0)    AS avg_rent,
            COUNT(*)                        AS listing_count
        FROM listings
        WHERE price_weekly IS NOT NULL
        GROUP BY suburb_id
    """, conn)
    return df


def load_transit(conn):
    """Compute avg on-time % and avg delay per suburb."""
    df = pd.read_sql_query("""
        SELECT
            suburb_id,
            ROUND(AVG(on_time_pct), 2)  AS avg_on_time_pct,
            ROUND(AVG(avg_delay_min), 2) AS avg_delay_min,
            COUNT(DISTINCT line_name)    AS train_lines_count
        FROM transit_performance
        WHERE on_time_pct > 0
        GROUP BY suburb_id
    """, conn)
    return df


def load_amenities(conn):
    """Pivot amenity counts per suburb into wide format."""
    df = pd.read_sql_query("""
        SELECT suburb_id, amenity_type, count
        FROM amenities
    """, conn)
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(
        index='suburb_id',
        columns='amenity_type',
        values='count',
        fill_value=0
    ).reset_index()
    pivot.columns.name = None

    # Total amenity count and variety (number of types with count > 0)
    amenity_cols = [c for c in pivot.columns if c != 'suburb_id']
    pivot['total_amenities'] = pivot[amenity_cols].sum(axis=1)
    pivot['amenity_variety'] = (pivot[amenity_cols] > 0).sum(axis=1)
    return pivot


def percentile_rank(series):
    """Rank a series to 0–1 percentile (higher = better rank)."""
    return series.rank(pct=True)


def min_max_norm(series):
    """Normalise series to 0–1."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - mn) / (mx - mn)


def ensure_liveability_columns(conn):
    existing = [r[1] for r in conn.execute("PRAGMA table_info(suburbs)").fetchall()]
    to_add = {
        'median_weekly_rent':       'REAL',
        'rent_to_income_ratio':     'REAL',
        'walkability_index':        'REAL',
        'transit_reliability_pct':  'REAL',
        'liveability_score':        'REAL',
        'affordability_score':      'REAL',
        'transit_score':            'REAL',
        'walkability_score':        'REAL',
        'amenity_variety_score':    'REAL',
        'value_gap':                'REAL',
        'classification':           'TEXT',
    }
    for col, dtype in to_add.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE suburbs ADD COLUMN {col} {dtype}")
    conn.commit()


def main():
    conn = get_db()
    ensure_liveability_columns(conn)

    # --- Load all data ---
    suburbs   = load_suburbs(conn)
    income    = load_income(conn)
    rent      = load_rent(conn)
    transit   = load_transit(conn)
    amenities = load_amenities(conn)

    logger.info(f"Suburbs with coordinates: {len(suburbs)}")
    logger.info(f"Income records: {len(income)}")
    logger.info(f"Rent records:   {len(rent)}")
    logger.info(f"Transit records:{len(transit)}")

    # --- Merge everything ---
    df = suburbs.merge(income,    on='suburb_id', how='left')
    df = df.merge(rent,           on='suburb_id', how='left')
    df = df.merge(transit,        on='suburb_id', how='left')
    if not amenities.empty:
        df = df.merge(amenities,  on='suburb_id', how='left')
    else:
        df['total_amenities'] = 0
        df['amenity_variety'] = 0

    logger.info(f"Merged DataFrame: {len(df)} suburbs, {len(df.columns)} columns")

    # --- Derived metrics ---

    # 1. Rent-to-income ratio (lower = more affordable)
    df['rent_to_income_ratio'] = np.where(
        df['median_weekly_income'] > 0,
        df['avg_rent'] / df['median_weekly_income'],
        np.nan
    )

    # 2. Walkability index — total amenities per suburb, normalised
    #    Proxy for density since we don't have area_sqkm yet
    df['walkability_index'] = min_max_norm(
        df['total_amenities'].fillna(0)
    )

    # 3. Transit reliability percentile
    df['transit_reliability_pct'] = percentile_rank(
        df['avg_on_time_pct'].fillna(0)
    )

    # --- Component scores (all 0–1, higher = better) ---

    # Affordability: lower rent-to-income = better
    # Invert so 1 = most affordable
    rti = df['rent_to_income_ratio'].fillna(df['rent_to_income_ratio'].median())
    df['affordability_score'] = 1 - min_max_norm(rti)

    # Transit: higher on-time % = better
    df['transit_score'] = df['transit_reliability_pct'].fillna(0.5)

    # Walkability: already 0–1
    df['walkability_score'] = df['walkability_index'].fillna(0)

    # Honesty: already 0–1 from P2
    df['honesty_score_norm'] = df['honesty_score'].fillna(
        df['honesty_score'].median()
    )

    # Amenity variety: number of amenity types with count > 0
    df['amenity_variety_score'] = min_max_norm(
        df['amenity_variety'].fillna(0)
    )

    # --- Composite liveability score (0–10) ---
    df['liveability_raw'] = (
        WEIGHTS['affordability']   * df['affordability_score']   +
        WEIGHTS['transit']         * df['transit_score']         +
        WEIGHTS['walkability']     * df['walkability_score']      +
        WEIGHTS['honesty']         * df['honesty_score_norm']     +
        WEIGHTS['amenity_variety'] * df['amenity_variety_score']
    )
    df['liveability_score'] = (df['liveability_raw'] * 10).round(2)

    # --- Value gap: liveability rank minus rent rank ---
    # Positive = high liveability, low rent = hidden gem
    # Negative = low liveability, high rent = overpriced trap
    df['liveability_rank'] = df['liveability_score'].rank(pct=True)
    df['rent_rank']        = df['avg_rent'].fillna(
        df['avg_rent'].median()
    ).rank(pct=True)
    df['value_gap'] = (df['liveability_rank'] - df['rent_rank']).round(4)

    # --- Classification ---
    def classify(row):
        if pd.isna(row['value_gap']):
            return 'insufficient data'
        if row['value_gap'] >= 0.25:
            return 'hidden gem'
        if row['value_gap'] <= -0.25:
            return 'overpriced trap'
        return 'fair value'

    df['classification'] = df.apply(classify, axis=1)

    # --- Write back to DB ---
    cursor = conn.cursor()
    for _, row in df.iterrows():
        cursor.execute("""
            UPDATE suburbs SET
                median_weekly_rent      = ?,
                rent_to_income_ratio    = ?,
                walkability_index       = ?,
                transit_reliability_pct = ?,
                liveability_score       = ?,
                affordability_score     = ?,
                transit_score           = ?,
                walkability_score       = ?,
                amenity_variety_score   = ?,
                value_gap               = ?,
                classification          = ?
            WHERE id = ?
        """, (
            row.get('avg_rent'),
            row.get('rent_to_income_ratio'),
            row.get('walkability_index'),
            row.get('transit_reliability_pct'),
            row.get('liveability_score'),
            row.get('affordability_score'),
            row.get('transit_score'),
            row.get('walkability_score'),
            row.get('amenity_variety_score'),
            row.get('value_gap'),
            row.get('classification'),
            int(row['suburb_id']),
        ))
    conn.commit()
    conn.close()

    # --- Console summary ---
    logger.info("\nLiveability leaderboard (top 10):")
    top = df.nlargest(10, 'liveability_score')[
        ['suburb', 'liveability_score', 'affordability_score',
         'transit_score', 'walkability_score', 'classification']
    ]
    logger.info(f"\n{top.to_string(index=False)}")

    logger.info("\nHidden gems (high liveability, low rent):")
    gems = df[df['classification'] == 'hidden gem'].nlargest(5, 'value_gap')[
        ['suburb', 'liveability_score', 'avg_rent', 'value_gap']
    ]
    logger.info(f"\n{gems.to_string(index=False)}")

    logger.info("\nOverpriced traps (low liveability, high rent):")
    traps = df[df['classification'] == 'overpriced trap'].nsmallest(5, 'value_gap')[
        ['suburb', 'liveability_score', 'avg_rent', 'value_gap']
    ]
    logger.info(f"\n{traps.to_string(index=False)}")

    # --- Export processed CSV for Tableau (P4) ---
    export_cols = [
        'suburb', 'latitude', 'longitude',
        'liveability_score', 'affordability_score', 'transit_score',
        'walkability_score', 'honesty_score_norm', 'amenity_variety_score',
        'avg_rent', 'median_weekly_income', 'rent_to_income_ratio',
        'avg_on_time_pct', 'avg_delay_min', 'train_lines_count',
        'total_amenities', 'amenity_variety',
        'honesty_score', 'buzzword_inflation_score', 'high_spin_rate',
        'value_gap', 'classification',
    ]
    export_cols = [c for c in export_cols if c in df.columns]
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'processed'
    )
    os.makedirs(out_path, exist_ok=True)
    df[export_cols].to_csv(os.path.join(out_path, 'suburb_scores.csv'), index=False)
    logger.info(f"\nExported suburb_scores.csv → data/processed/")


if __name__ == '__main__':
    main()