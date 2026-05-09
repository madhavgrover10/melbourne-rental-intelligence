import requests
import sqlite3
import os
import time
import json
import logging

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')
RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'raw')
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SEARCH_RADIUS = 1500  # metres from suburb centroid

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Master list — aligned with 02_load_abs_data.py
SUBURB_COORDS = {
    "Melbourne":      (-37.8136, 144.9631),
    "Richmond":       (-37.8183, 144.9981),
    "South Yarra":    (-37.8388, 144.9929),
    "Fitzroy":        (-37.7990, 144.9782),
    "Collingwood":    (-37.8030, 144.9870),
    "Carlton":        (-37.7941, 144.9672),
    "Brunswick":      (-37.7666, 144.9604),
    "Northcote":      (-37.7696, 145.0007),
    "Thornbury":      (-37.7545, 145.0057),
    "Preston":        (-37.7445, 145.0127),
    "Coburg":         (-37.7437, 144.9643),
    "Footscray":      (-37.7998, 144.8989),
    "Yarraville":     (-37.8167, 144.8892),
    "Williamstown":   (-37.8607, 144.8985),
    "Seddon":         (-37.8058, 144.8865),
    "St Kilda":       (-37.8582, 144.9741),
    "St Kilda East":  (-37.8666, 144.9960),
    "Elwood":         (-37.8793, 144.9849),
    "Brighton":       (-37.9053, 144.9856),
    "Caulfield":      (-37.8772, 145.0230),
    "Malvern":        (-37.8569, 145.0300),
    "Hawthorn":       (-37.8225, 145.0341),
    "Kew":            (-37.8053, 145.0363),
    "Camberwell":     (-37.8328, 145.0580),
    "Box Hill":       (-37.8192, 145.1218),
    "Doncaster":      (-37.7858, 145.1265),
    "Glen Waverley":  (-37.8784, 145.1649),
    "Clayton":        (-37.9254, 145.1198),
    "Oakleigh":       (-37.9001, 145.0883),
    "Bentleigh":      (-37.9191, 145.0360),
    "Moorabbin":      (-37.9281, 145.0618),
    "Cheltenham":     (-37.9574, 145.0569),
    "Mentone":        (-37.9821, 145.0683),
    "Frankston":      (-38.1432, 145.1254),
    "Dandenong":      (-37.9875, 145.2147),
    "Berwick":        (-38.0358, 145.3530),
    "Narre Warren":   (-38.0290, 145.3020),
    "Cranbourne":     (-38.0999, 145.2838),
    "Pakenham":       (-38.0712, 145.4875),
    "Werribee":       (-37.9020, 144.6621),
    "Point Cook":     (-37.8922, 144.7472),
    "Tarneit":        (-37.8530, 144.6890),
    "Sunshine":       (-37.7886, 144.8327),
    "Moonee Ponds":   (-37.7655, 144.9211),
    "Essendon":       (-37.7518, 144.9150),
    "Pascoe Vale":    (-37.7290, 144.9380),
    "Ascot Vale":     (-37.7772, 144.9178),
    "Glenroy":        (-37.7033, 144.9283),
    "Reservoir":      (-37.7172, 145.0073),
    "Heidelberg":     (-37.7558, 145.0668),
    "Ivanhoe":        (-37.7687, 145.0457),
    "Eltham":         (-37.7139, 145.1480),
    "Greensborough":  (-37.7038, 145.1015),
    "Bundoora":       (-37.6982, 145.0600),
    "South Morang":   (-37.6523, 145.0930),
    "Craigieburn":    (-37.6003, 144.9460),
    "Sunbury":        (-37.5767, 144.7267),
    "Broadmeadows":   (-37.6815, 144.9208),
    "Abbotsford":     (-37.8042, 144.9999),
    "Fitzroy North":  (-37.7870, 144.9782),
    "Prahran":        (-37.8497, 144.9920),
    "Windsor":        (-37.8558, 144.9910),
    "Balaclava":      (-37.8671, 144.9930),
    "Armadale":       (-37.8555, 145.0176),
    "Toorak":         (-37.8389, 145.0145),
    "Albert Park":    (-37.8425, 144.9549),
    "Port Melbourne": (-37.8362, 144.9284),
    "South Melbourne":(-37.8305, 144.9592),
    "Docklands":      (-37.8140, 144.9470),
    "Southbank":      (-37.8230, 144.9630),
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_suburb(conn, name):
    row = conn.execute(
        "SELECT id FROM suburbs WHERE LOWER(name) = LOWER(?)",
        (name,)
    ).fetchone()
    if row:
        return row['id']
    cursor = conn.execute("INSERT INTO suburbs (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid


def fetch_amenities(lat, lng, radius=SEARCH_RADIUS, retries=3):
    """
    Query Overpass API for amenity counts around a lat/lng centroid.
    Uses nw (node+way) union to avoid double-counting.
    Parks also include relations (polygon boundaries) which is how
    OSM models most parks.
    Returns a dict of amenity_type: count, or None on total failure.
    """
    query = f"""
    [out:json][timeout:60];
    (
      nw[shop=supermarket](around:{radius},{lat},{lng});
      nw[amenity=cafe](around:{radius},{lat},{lng});
      nw[amenity=restaurant](around:{radius},{lat},{lng});
      nw[leisure=park](around:{radius},{lat},{lng});
      relation[leisure=park](around:{radius},{lat},{lng});
      nw[leisure=fitness_centre](around:{radius},{lat},{lng});
      nw[amenity=pharmacy](around:{radius},{lat},{lng});
      nw[amenity=school](around:{radius},{lat},{lng});
    );
    out center tags;
    """

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                OVERPASS_URL,
                data={'data': query},
                timeout=60
            )
            if response.status_code == 429:
                wait = 30 * attempt
                logger.warning(f"Rate limited — waiting {wait}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue

            response.raise_for_status()

            elements = response.json().get('elements', [])
            counts = {
                'supermarket': 0, 'cafe': 0, 'restaurant': 0,
                'park': 0, 'gym': 0, 'pharmacy': 0, 'school': 0
            }

            seen = set()  # deduplicate by (type, id)
            for el in elements:
                uid = (el.get('type'), el.get('id'))
                if uid in seen:
                    continue
                seen.add(uid)

                tags = el.get('tags', {})
                amenity = tags.get('amenity', '')
                shop    = tags.get('shop', '')
                leisure = tags.get('leisure', '')

                if shop == 'supermarket':             counts['supermarket'] += 1
                elif amenity == 'cafe':               counts['cafe'] += 1
                elif amenity == 'restaurant':         counts['restaurant'] += 1
                elif leisure == 'park':               counts['park'] += 1
                elif leisure == 'fitness_centre':     counts['gym'] += 1
                elif amenity == 'pharmacy':           counts['pharmacy'] += 1
                elif amenity == 'school':             counts['school'] += 1

            return counts

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt}/{retries} for ({lat}, {lng})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error on attempt {attempt}/{retries}: {e}")

        if attempt < retries:
            time.sleep(5 * attempt)

    logger.error(f"All {retries} attempts failed for ({lat}, {lng})")
    return None


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    conn = get_db()
    all_results = {}
    failed = []

    logger.info(f"Fetching amenities for {len(SUBURB_COORDS)} suburbs...")

    for i, (suburb, (lat, lng)) in enumerate(SUBURB_COORDS.items()):
        logger.info(f"[{i+1}/{len(SUBURB_COORDS)}] {suburb}")

        counts = fetch_amenities(lat, lng)
        if counts is None:
            logger.warning(f"  Skipping {suburb} — all retries failed")
            failed.append(suburb)
            continue

        suburb_id = get_or_create_suburb(conn, suburb)

        # Update coordinates while we're here (area_sqkm populated in P3 via GeoPandas)
        conn.execute(
            "UPDATE suburbs SET latitude=?, longitude=? WHERE id=?",
            (lat, lng, suburb_id)
        )

        for amenity_type, count in counts.items():
            conn.execute("""
                INSERT INTO amenities (suburb_id, amenity_type, count)
                VALUES (?, ?, ?)
                ON CONFLICT(suburb_id, amenity_type) DO UPDATE SET
                    count = excluded.count
            """, (suburb_id, amenity_type, count))

        all_results[suburb] = counts
        conn.commit()

        logger.info(f"  → {counts}")
        time.sleep(3)  # polite delay — Overpass fair-use

    # Save raw backup
    with open(os.path.join(RAW_DIR, 'amenities_raw.json'), 'w') as f:
        json.dump(all_results, f, indent=2)

    total = conn.execute("SELECT COUNT(*) FROM amenities").fetchone()[0]
    conn.close()

    logger.info(f"Done — {total} amenity records in DB")
    if failed:
        logger.warning(f"Failed suburbs ({len(failed)}): {', '.join(failed)}")


if __name__ == '__main__':
    main()