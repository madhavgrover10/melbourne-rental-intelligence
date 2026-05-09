import sqlite3
import os
import json
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Marketing adjectives for superlative density calculation
# (same list as task 1 — density = count per 100 words)
SUPERLATIVES = [
    "stunning", "gorgeous", "magnificent", "exceptional", "incredible",
    "beautiful", "charming", "delightful", "impressive", "outstanding",
    "spectacular", "wonderful", "superb", "sensational", "brilliant",
    "luxurious", "luxury", "premium", "prestige", "prestigious",
    "unparalleled", "unrivalled", "breathtaking", "exquisite", "impeccable",
    "flawless", "pristine", "immaculate", "faultless", "perfect",
    "rare", "unique", "one-of-a-kind", "must-see", "don't miss",
    "dream", "paradise", "heaven", "oasis",
]

# Outlier threshold — listings in top 10% of superlative density get flagged
OUTLIER_PERCENTILE = 0.90


def ensure_sentiment_columns(conn):
    """Add sentiment columns to listings table if not already present."""
    existing = [
        row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()
    ]
    columns_to_add = {
        "sentiment_compound":   "REAL",   # VADER compound score (-1 to +1)
        "sentiment_positive":   "REAL",   # VADER pos component
        "sentiment_negative":   "REAL",   # VADER neg component
        "sentiment_neutral":    "REAL",   # VADER neu component
        "superlative_density":  "REAL",   # superlatives per 100 words
        "is_outlier":           "INTEGER" # 1 if flagged as high-spin listing
    }
    for col, dtype in columns_to_add.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {dtype}")
            logger.info(f"Added column: {col}")
    conn.commit()


def compute_superlative_density(text, word_count):
    """Superlatives per 100 words. Returns 0.0 if word_count is 0."""
    if not word_count or word_count == 0:
        return 0.0
    text_lower = text.lower()
    count = sum(1 for s in SUPERLATIVES if s in text_lower)
    return round((count / word_count) * 100, 4)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def main():
    conn = get_db()
    ensure_sentiment_columns(conn)

    analyzer = SentimentIntensityAnalyzer()

    # Fetch all listings that have nlp_features (word_count) but no sentiment yet
    listings = conn.execute("""
        SELECT l.id, l.description, n.word_count
        FROM listings l
        JOIN nlp_features n ON n.listing_id = l.id
        WHERE l.sentiment_compound IS NULL
          AND l.description IS NOT NULL
          AND TRIM(l.description) != ''
    """).fetchall()

    logger.info(f"Scoring sentiment for {len(listings)} listings...")

    scores = []  # collect for outlier detection
    processed = 0

    for listing in listings:
        text       = listing['description']
        word_count = listing['word_count'] or 0

        # VADER scores
        vs = analyzer.polarity_scores(text)

        # Superlative density
        density = compute_superlative_density(text, word_count)

        scores.append({
            "id":       listing['id'],
            "compound": vs['compound'],
            "pos":      vs['pos'],
            "neg":      vs['neg'],
            "neu":      vs['neu'],
            "density":  density,
        })
        processed += 1

    # --- Outlier detection ---
    # Flag listings in top 10% of superlative density
    if scores:
        densities = sorted([s['density'] for s in scores])
        threshold_idx = int(len(densities) * OUTLIER_PERCENTILE)
        outlier_threshold = densities[min(threshold_idx, len(densities) - 1)]
        logger.info(f"Outlier threshold (top 10% superlative density): {outlier_threshold:.4f}")
    else:
        outlier_threshold = 999

    # --- Write to DB ---
    for s in scores:
        is_outlier = 1 if s['density'] >= outlier_threshold else 0
        conn.execute("""
            UPDATE listings SET
                sentiment_compound  = ?,
                sentiment_positive  = ?,
                sentiment_negative  = ?,
                sentiment_neutral   = ?,
                superlative_density = ?,
                is_outlier          = ?
            WHERE id = ?
        """, (
            s['compound'], s['pos'], s['neg'], s['neu'],
            s['density'], is_outlier, s['id']
        ))

    conn.commit()

    # --- Summary stats ---
    stats = conn.execute("""
        SELECT
            ROUND(AVG(sentiment_compound), 4)  AS avg_compound,
            ROUND(MAX(sentiment_compound), 4)  AS max_compound,
            ROUND(MIN(sentiment_compound), 4)  AS min_compound,
            ROUND(AVG(superlative_density), 4) AS avg_density,
            SUM(is_outlier)                    AS outlier_count
        FROM listings
        WHERE sentiment_compound IS NOT NULL
    """).fetchone()

    conn.close()
    logger.info(f"Done — {processed} listings scored")
    logger.info(f"  Avg compound score : {stats['avg_compound']}")
    logger.info(f"  Score range        : {stats['min_compound']} to {stats['max_compound']}")
    logger.info(f"  Avg superlative density : {stats['avg_density']} per 100 words")
    logger.info(f"  Outlier listings flagged: {stats['outlier_count']}")


if __name__ == '__main__':
    main()