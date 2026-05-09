import sqlite3
import os
import json
import logging
import time
from openai import OpenAI

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

client = OpenAI()  # reads OPENAI_API_KEY from environment

MODEL         = "gpt-4o-mini"
BATCH_SIZE    = 20   # listings per API call — reduces cost vs one call per listing
DELAY_BETWEEN = 1.0  # seconds between batches — stays well under rate limits

SYSTEM_PROMPT = """You are a real estate listing analyser specialising in detecting 
euphemistic and misleading language in Australian rental listings.

For each listing description provided, extract a JSON object with these exact fields:
- claimed_walk_time: integer minutes if a walk time to transport is claimed, else null
- renovation_state: one of "renovated", "original", "needs_work", "unknown"
- size_indicator: one of "large", "medium", "small", "unknown"  
- noise_level: one of "quiet", "busy", "unknown"
- red_flags: array of strings — specific euphemistic phrases detected (e.g. "cosy", "good bones", "blank canvas", "investor special", "priced to reflect condition")
- spin_level: one of "low", "medium", "high" — overall marketing spin assessment

Return ONLY a JSON array with one object per listing, in the same order as input.
No preamble, no markdown, no explanation. Pure JSON array only."""


def ensure_llm_features_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_features (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id          INTEGER NOT NULL REFERENCES listings(id),
            claimed_walk_time   INTEGER,
            renovation_state    TEXT,
            size_indicator      TEXT,
            noise_level         TEXT,
            red_flags           TEXT,    -- JSON array
            spin_level          TEXT,
            model_used          TEXT,
            processed_at        TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_listing
        ON llm_features(listing_id)
    """)
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def parse_llm_response(response_text, batch_ids):
    """
    Parse LLM JSON array response. Returns list of (listing_id, parsed_dict).
    Handles malformed responses gracefully.
    """
    try:
        # Strip any accidental markdown fences
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        results = json.loads(cleaned)
        if not isinstance(results, list):
            raise ValueError("Expected JSON array")

        paired = []
        for i, item in enumerate(results):
            if i >= len(batch_ids):
                break
            paired.append((batch_ids[i], item))
        return paired

    except Exception as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        logger.debug(f"Raw response: {response_text[:300]}")
        return []


def process_batch(batch_listings):
    """Send a batch of listings to OpenAI and return parsed results."""
    # Build numbered prompt
    prompt_parts = []
    for i, listing in enumerate(batch_listings):
        prompt_parts.append(f"Listing {i+1}:\n{listing['description']}")
    prompt = "\n\n---\n\n".join(prompt_parts)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.1,   # low temp for consistent structured output
            max_tokens=BATCH_SIZE * 120,  # ~120 tokens per listing result
        )
        return response.choices[0].message.content

    except Exception as e:
        logger.warning(f"OpenAI API error: {e}")
        return None


def safe_get(d, key, default=None):
    """Safely extract from parsed dict — LLM output can be inconsistent."""
    if not isinstance(d, dict):
        return default
    val = d.get(key, default)
    return val if val is not None else default


def main():
    conn = get_db()
    ensure_llm_features_table(conn)

    # Only process listings not yet in llm_features
    listings = conn.execute("""
        SELECT l.id, l.description
        FROM listings l
        LEFT JOIN llm_features lf ON lf.listing_id = l.id
        WHERE lf.id IS NULL
          AND l.description IS NOT NULL
          AND TRIM(l.description) != ''
        ORDER BY l.id
    """).fetchall()

    total     = len(listings)
    batches   = [listings[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    inserted  = 0
    failed    = 0

    logger.info(f"Processing {total} listings in {len(batches)} batches of {BATCH_SIZE}...")

    for batch_num, batch in enumerate(batches, 1):
        batch_ids = [l['id'] for l in batch]

        logger.info(f"Batch {batch_num}/{len(batches)} (listings {batch_ids[0]}–{batch_ids[-1]})")

        raw_response = process_batch(batch)
        if not raw_response:
            logger.warning(f"  Batch {batch_num} failed — skipping")
            failed += len(batch)
            continue

        parsed = parse_llm_response(raw_response, batch_ids)
        if not parsed:
            logger.warning(f"  Batch {batch_num} parse failed — skipping")
            failed += len(batch)
            continue

        batch_inserted = 0
        for listing_id, features in parsed:
            try:
                red_flags = safe_get(features, 'red_flags', [])
                if not isinstance(red_flags, list):
                    red_flags = [str(red_flags)]

                conn.execute("""
                    INSERT OR IGNORE INTO llm_features (
                        listing_id, claimed_walk_time, renovation_state,
                        size_indicator, noise_level, red_flags,
                        spin_level, model_used, processed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    listing_id,
                    safe_get(features, 'claimed_walk_time'),
                    safe_get(features, 'renovation_state', 'unknown'),
                    safe_get(features, 'size_indicator',   'unknown'),
                    safe_get(features, 'noise_level',      'unknown'),
                    json.dumps(red_flags),
                    safe_get(features, 'spin_level',       'unknown'),
                    MODEL,
                ))
                batch_inserted += 1
                inserted += 1

            except Exception as e:
                logger.warning(f"  Insert failed for listing {listing_id}: {e}")
                failed += 1

        conn.commit()
        logger.info(f"  Inserted {batch_inserted}/{len(batch)}")

        time.sleep(DELAY_BETWEEN)

    # Summary
    stats = conn.execute("""
        SELECT
            spin_level,
            COUNT(*) as count,
            ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM llm_features), 1) as pct
        FROM llm_features
        GROUP BY spin_level
        ORDER BY count DESC
    """).fetchall()

    conn.close()
    logger.info(f"Done — {inserted} inserted, {failed} failed")
    logger.info("Spin level breakdown:")
    for row in stats:
        logger.info(f"  {row['spin_level']:10s}: {row['count']:4d} ({row['pct']}%)")


if __name__ == '__main__':
    main()