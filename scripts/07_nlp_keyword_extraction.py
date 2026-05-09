import sqlite3
import os
import json
import logging
import re
import spacy

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Pattern libraries for feature extraction
# -------------------------------------------------------------------

# Transport proximity claims — "5 min walk to station", "close to tram"
TRANSPORT_PATTERNS = [
    r'(\d+)\s*min(?:ute)?s?\s*walk\s*to\s*(train|station|tram|bus|metro)',
    r'(\d+)\s*min(?:ute)?s?\s*from\s*(train|station|tram|bus|stop)',
    r'(walking distance|short walk|easy walk|stroll)\s*to\s*(train|station|tram|bus)',
    r'(close to|near|next to|opposite|adjacent to)\s*(train|station|tram|bus\s*stop)',
    r'(tram\s*at\s*door|tram\s*stop\s*outside|station\s*nearby)',
]

# Amenity proximity claims — "near shops", "close to cafes"
AMENITY_PATTERNS = [
    r'(close to|near|walking distance to|moments from|steps from|minutes from)\s*'
    r'(cafe|coffee|restaurant|shop|supermarket|park|gym|school|pharmacy|bar|pub)',
    r'(vibrant|bustling|thriving)\s*(cafe|dining|food|shopping|nightlife|precinct)',
    r'(world.?class|exceptional|excellent)\s*(dining|schools|shopping|amenities)',
]

# Superlative / marketing adjectives
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

# Euphemism signals — mapped to what they likely mean
EUPHEMISMS = {
    "cosy":             "small",
    "compact":          "small",
    "easy-care":        "small_garden",
    "low maintenance":  "small_or_no_garden",
    "character":        "old_needs_work",
    "original":         "dated_not_renovated",
    "potential":        "needs_renovation",
    "blank canvas":     "needs_renovation",
    "investor special": "below_average_condition",
    "priced to reflect": "poor_condition",
    "good bones":       "needs_renovation",
    "fresh eyes":       "needs_renovation",
    "functional":       "basic_not_modern",
    "convenient":       "nothing_special",
    "moments from":     "distance_unspecified",
    "short drive":      "not_walkable",
    "easy access":      "distance_unspecified",
}

# Location claim patterns — "in the heart of", "perfectly positioned"
LOCATION_SPIN = [
    "heart of", "sought-after", "tightly-held", "blue-chip",
    "vibrant precinct", "lifestyle precinct", "coveted",
    "perfectly positioned", "ideally located", "prime location",
    "prestigious address", "exclusive",
]


def load_spacy():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        logger.error("spaCy model not found. Run: python -m spacy download en_core_web_sm")
        raise


def extract_transport_claims(text):
    """
    Extract transport proximity claims.
    Returns list of dicts: {pattern_type, claimed_minutes, transport_type, raw_match}
    """
    claims = []
    text_lower = text.lower()
    for pattern in TRANSPORT_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            groups = match.groups()
            # Try to extract a minute claim if present
            minutes = None
            for g in groups:
                if g and re.match(r'^\d+$', g):
                    minutes = int(g)
                    break
            transport_type = None
            for g in groups:
                if g and any(t in g for t in ['train', 'station', 'tram', 'bus', 'metro']):
                    transport_type = g
                    break
            claims.append({
                "raw_match":      match.group(),
                "claimed_minutes": minutes,
                "transport_type":  transport_type or "unspecified",
            })
    return claims


def extract_amenity_claims(text):
    """
    Extract amenity proximity claims.
    Returns list of amenity types claimed to be nearby.
    """
    claimed = []
    text_lower = text.lower()
    amenity_keywords = [
        "cafe", "coffee", "restaurant", "shop", "supermarket",
        "park", "gym", "school", "pharmacy", "bar", "pub",
        "dining", "nightlife", "shopping"
    ]
    for pattern in AMENITY_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            raw = match.group()
            for kw in amenity_keywords:
                if kw in raw:
                    claimed.append(kw)
    return list(set(claimed))


def count_superlatives(text):
    """Count marketing superlatives. Returns count and list found."""
    text_lower = text.lower()
    found = [s for s in SUPERLATIVES if s in text_lower]
    return len(found), found


def detect_euphemisms(text):
    """Detect euphemistic phrases. Returns dict of {euphemism: implied_meaning}."""
    text_lower = text.lower()
    found = {}
    for phrase, meaning in EUPHEMISMS.items():
        if phrase in text_lower:
            found[phrase] = meaning
    return found


def count_location_spin(text):
    """Count location spin phrases."""
    text_lower = text.lower()
    return sum(1 for phrase in LOCATION_SPIN if phrase in text_lower)


def extract_spacy_features(nlp, text):
    """
    Run spaCy NER and linguistic analysis.
    Returns: entity counts, sentence count, word count, noun chunks
    """
    doc = nlp(text)

    entities = {}
    for ent in doc.ents:
        label = ent.label_
        entities[label] = entities.get(label, 0) + 1

    # Count sentences and words
    sentences   = len(list(doc.sents))
    word_count  = len([t for t in doc if not t.is_punct and not t.is_space])

    # Extract meaningful noun chunks (skip generic ones)
    skip_chunks = {"you", "we", "i", "it", "this", "that", "your", "our"}
    noun_chunks = [
        chunk.text.lower() for chunk in doc.noun_chunks
        if chunk.root.text.lower() not in skip_chunks and len(chunk.text) > 3
    ]

    return {
        "entities":    entities,
        "sentences":   sentences,
        "word_count":  word_count,
        "noun_chunks": noun_chunks[:20],  # cap at 20 for storage
    }


def ensure_nlp_features_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nlp_features (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id          INTEGER NOT NULL REFERENCES listings(id),
            word_count          INTEGER,
            sentence_count      INTEGER,
            superlative_count   INTEGER,
            superlatives_found  TEXT,   -- JSON array
            euphemism_count     INTEGER,
            euphemisms_found    TEXT,   -- JSON object {phrase: meaning}
            transport_claims    TEXT,   -- JSON array
            amenity_claims      TEXT,   -- JSON array
            location_spin_count INTEGER,
            spacy_entities      TEXT,   -- JSON object {LABEL: count}
            noun_chunks         TEXT,   -- JSON array
            processed_at        TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_nlp_listing
        ON nlp_features(listing_id)
    """)
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def main():
    nlp  = load_spacy()
    conn = get_db()
    ensure_nlp_features_table(conn)

    # Only process listings not yet in nlp_features
    listings = conn.execute("""
        SELECT l.id, l.description
        FROM listings l
        LEFT JOIN nlp_features n ON n.listing_id = l.id
        WHERE n.id IS NULL
          AND l.description IS NOT NULL
          AND TRIM(l.description) != ''
    """).fetchall()

    logger.info(f"Processing {len(listings)} listings through NLP pipeline...")

    processed = 0
    for listing in listings:
        text = listing['description']

        transport_claims  = extract_transport_claims(text)
        amenity_claims    = extract_amenity_claims(text)
        sup_count, sups   = count_superlatives(text)
        euphemisms        = detect_euphemisms(text)
        spin_count        = count_location_spin(text)
        spacy_feats       = extract_spacy_features(nlp, text)

        conn.execute("""
            INSERT OR IGNORE INTO nlp_features (
                listing_id, word_count, sentence_count,
                superlative_count, superlatives_found,
                euphemism_count, euphemisms_found,
                transport_claims, amenity_claims,
                location_spin_count, spacy_entities, noun_chunks,
                processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            listing['id'],
            spacy_feats['word_count'],
            spacy_feats['sentences'],
            sup_count,
            json.dumps(sups),
            len(euphemisms),
            json.dumps(euphemisms),
            json.dumps(transport_claims),
            json.dumps(amenity_claims),
            spin_count,
            json.dumps(spacy_feats['entities']),
            json.dumps(spacy_feats['noun_chunks']),
        ))

        processed += 1
        if processed % 100 == 0:
            conn.commit()
            logger.info(f"  Processed {processed}/{len(listings)}")

    conn.commit()
    conn.close()
    logger.info(f"Done — {processed} listings processed into nlp_features table")


if __name__ == '__main__':
    main()