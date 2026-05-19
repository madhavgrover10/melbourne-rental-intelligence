import sqlite3
import os
import json
import logging
import time
import pandas as pd
from openai import OpenAI

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')
OUT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'processed')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

client = OpenAI()
MODEL  = "gpt-4o-mini"

SYSTEM_PROMPT = """You are a data-driven Melbourne rental market analyst. 
You write concise, honest suburb summaries for renters based purely on data — 
no marketing spin, no fluff. 

Each summary must be exactly 3 sentences:
1. Overall verdict with liveability score context
2. Key strengths (data-backed — mention actual numbers)
3. Key weaknesses or who should avoid it

Tone: direct, helpful, slightly opinionated. Like a knowledgeable friend, not a real estate agent.
Never use the words: stunning, gorgeous, vibrant, sought-after, nestled, boasts."""


def ensure_summary_column(conn):
    existing = [r[1] for r in conn.execute("PRAGMA table_info(suburbs)").fetchall()]
    if 'ai_summary' not in existing:
        conn.execute("ALTER TABLE suburbs ADD COLUMN ai_summary TEXT")
        conn.commit()
        logger.info("Added column: ai_summary")


def load_suburbs(conn):
    return pd.read_sql_query("""
        SELECT
            s.id                        AS suburb_id,
            s.name                      AS suburb,
            s.liveability_score,
            s.affordability_score,
            s.walkability_score,
            s.honesty_score,
            s.median_weekly_rent,
            s.rent_to_income_ratio,
            s.value_gap,
            s.classification,
            s.high_spin_rate,
            s.buzzword_inflation_score,
            i.median_household_weekly   AS median_income,
            a.suburb_id                 AS has_amenities,
            sa.strength_factors,
            sa.weakness_factors,
            sa.renter_profile
        FROM suburbs s
        LEFT JOIN income i ON i.suburb_id = s.id
        LEFT JOIN (
            SELECT suburb_id, COUNT(*) as cnt
            FROM amenities GROUP BY suburb_id
        ) a ON a.suburb_id = s.id
        LEFT JOIN suburb_analysis sa ON sa.suburb_id = s.id
        WHERE s.liveability_score IS NOT NULL
          AND s.ai_summary IS NULL
        ORDER BY s.liveability_score DESC
    """, conn)


def build_prompt(row):
    """Build a data-rich prompt for a single suburb."""
    strengths  = json.loads(row['strength_factors'])  if row['strength_factors']  else []
    weaknesses = json.loads(row['weakness_factors'])  if row['weakness_factors']  else []
    profile    = json.loads(row['renter_profile'])    if row['renter_profile']    else []

    rti = f"{row['rent_to_income_ratio']:.2f}x" if row['rent_to_income_ratio'] else "unknown"

    return f"""Write a 3-sentence renter summary for {row['suburb']}, Melbourne.

Data:
- Liveability score: {row['liveability_score']:.1f}/10
- Classification: {row['classification']}
- Median weekly rent: ${row['median_weekly_rent']:.0f}
- Median household income: ${row['median_income']:.0f}/wk
- Rent-to-income ratio: {rti}
- Affordability score: {row['affordability_score']:.2f}/1.0
- Walkability score: {row['walkability_score']:.2f}/1.0
- Honesty score: {row['honesty_score']:.2f}/1.0 (higher = listings are more honest)
- High spin rate: {row['high_spin_rate']:.0%} of listings are heavily marketed
- Value gap: {row['value_gap']:+.2f} (positive = better value than rent suggests)
- Strengths: {', '.join(strengths) if strengths else 'none identified'}
- Weaknesses: {', '.join(weaknesses) if weaknesses else 'none identified'}
- Best suits: {', '.join(profile) if profile else 'general renters'}"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = get_db()
    ensure_summary_column(conn)

    df = load_suburbs(conn)
    logger.info(f"Generating summaries for {len(df)} suburbs...")

    summaries   = []
    processed   = 0
    failed      = 0

    for _, row in df.iterrows():
        prompt = build_prompt(row)

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.4,
                max_tokens=180,
            )
            summary = response.choices[0].message.content.strip()

            conn.execute(
                "UPDATE suburbs SET ai_summary = ? WHERE id = ?",
                (summary, int(row['suburb_id']))
            )
            conn.commit()

            summaries.append({'suburb': row['suburb'], 'summary': summary})
            processed += 1

            if processed % 10 == 0:
                logger.info(f"  {processed}/{len(df)} done")

            time.sleep(0.3)  # stay under RPM limit

        except Exception as e:
            logger.warning(f"Failed for {row['suburb']}: {e}")
            failed += 1
            time.sleep(2)

    # Export all summaries to JSON for Streamlit / blog
    out_path = os.path.join(OUT_DIR, 'suburb_summaries.json')
    with open(out_path, 'w') as f:
        json.dump(summaries, f, indent=2)

    conn.close()
    logger.info(f"Done — {processed} summaries generated, {failed} failed")
    logger.info(f"Exported → data/processed/suburb_summaries.json")

    # Print sample
    logger.info("\nSample summaries:")
    for s in summaries[:3]:
        logger.info(f"\n{s['suburb']}:\n{s['summary']}")


if __name__ == '__main__':
    main()