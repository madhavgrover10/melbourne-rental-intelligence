import requests
import sqlite3
import os
import time
import json
import logging
import re
from bs4 import BeautifulSoup
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')
RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'raw')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://www.domain.com.au"
SEARCH_URL = "https://www.domain.com.au/rent/?suburb={suburb}-vic&page={page}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.domain.com.au/",
}

MAX_PAGES = 5       # per suburb — Domain shows ~20 listings/page = ~100 per suburb
DELAY_MIN = 4.0     # seconds between requests — polite scraping
DELAY_MAX = 7.0
MAX_RETRIES = 3

SUBURBS = [
    "melbourne", "richmond", "south-yarra", "fitzroy", "collingwood",
    "carlton", "brunswick", "northcote", "thornbury", "preston",
    "st-kilda", "elwood", "brighton", "caulfield", "malvern",
    "hawthorn", "camberwell", "box-hill", "footscray", "yarraville",
    "sunshine", "essendon", "moonee-ponds", "coburg", "reservoir",
    "heidelberg", "ivanhoe", "frankston", "dandenong", "werribee",
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_suburb(conn, name):
    # Normalise: "st-kilda" → "St Kilda"
    display = name.replace("-", " ").title()
    row = conn.execute(
        "SELECT id FROM suburbs WHERE LOWER(name) = LOWER(?)", (display,)
    ).fetchone()
    if row:
        return row['id'], display
    cursor = conn.execute("INSERT INTO suburbs (name) VALUES (?)", (display,))
    conn.commit()
    return cursor.lastrowid, display


def fetch_page(session, suburb_slug, page, retries=MAX_RETRIES):
    url = SEARCH_URL.format(suburb=suburb_slug, page=page)
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 403:
                logger.warning(f"403 Forbidden — Domain may be blocking. Attempt {attempt}/{retries}")
                time.sleep(30 * attempt)
                continue
            if resp.status_code == 429:
                logger.warning(f"Rate limited. Waiting 60s...")
                time.sleep(60)
                continue
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Request failed ({attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(10 * attempt)
    return None


def parse_price(price_str):
    """Extract weekly rent as integer from strings like '$450 per week', '$1,200/wk'."""
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d]', '', price_str.split('/')[0].split('per')[0])
    try:
        val = int(cleaned)
        return val if 200 <= val <= 10000 else None
    except ValueError:
        return None


def parse_listing(card, suburb_id):
    """
    Parse a single listing card from Domain search results.
    Returns a dict ready for DB insert, or None if essential fields missing.
    """
    try:
        # Price
        price_el = card.select_one('[data-testid="listing-card-price"]')
        price = parse_price(price_el.get_text(strip=True) if price_el else None)
        if not price:
            return None

        # Address / URL
        link_el = card.select_one('a[href*="/rent/"]')
        url = BASE_URL + link_el['href'] if link_el and link_el.get('href', '').startswith('/') else (
            link_el['href'] if link_el else None
        )

        # Bedrooms / bathrooms / parking
        features = card.select('[data-testid="property-features-text"]')
        beds = baths = parking = 0
        for f in features:
            text = f.get_text(strip=True).lower()
            num = re.search(r'\d+', text)
            val = int(num.group()) if num else 0
            if 'bed' in text:   beds    = val
            if 'bath' in text:  baths   = val
            if 'park' in text or 'car' in text:  parking = val

        # Property type
        type_el = card.select_one('[data-testid="listing-card-property-type"]')
        prop_type_raw = type_el.get_text(strip=True).lower() if type_el else ""
        if "house" in prop_type_raw or "townhouse" in prop_type_raw:
            prop_type = "house"
        elif "unit" in prop_type_raw or "villa" in prop_type_raw:
            prop_type = "unit"
        else:
            prop_type = "apartment"

        # Description
        desc_el = card.select_one('[data-testid="listing-card-description"]')
        description = desc_el.get_text(strip=True) if desc_el else ""

        return {
            "suburb_id":     suburb_id,
            "price":         price,
            "bedrooms":      beds,
            "bathrooms":     baths,
            "parking":       parking,
            "property_type": prop_type,
            "latitude":      None,   # Domain search cards don't expose coords
            "longitude":     None,   # populated if you scrape individual listing pages
            "description":   description,
            "url":           url,
            "bond":          price * 4,
            "days_on_market": None,
            "scraped_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        logger.debug(f"Parse error on listing card: {e}")
        return None


def listing_exists(conn, url):
    if not url:
        return False
    return conn.execute(
        "SELECT 1 FROM listings WHERE url = ?", (url,)
    ).fetchone() is not None


def insert_listing(conn, data):
    conn.execute("""
        INSERT INTO listings
            (suburb_id, price, bedrooms, bathrooms, parking,
             property_type, latitude, longitude,
             description, url, bond, days_on_market, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data['suburb_id'], data['price'], data['bedrooms'], data['bathrooms'],
        data['parking'], data['property_type'], data['latitude'], data['longitude'],
        data['description'], data['url'], data['bond'],
        data['days_on_market'], data['scraped_at']
    ))


def scrape_all():
    os.makedirs(RAW_DIR, exist_ok=True)
    conn = get_db()
    session = requests.Session()
    all_raw = []
    total_inserted = 0

    for suburb_slug in SUBURBS:
        suburb_id, suburb_name = get_or_create_suburb(conn, suburb_slug)
        logger.info(f"Scraping {suburb_name}...")
        suburb_count = 0

        for page in range(1, MAX_PAGES + 1):
            html = fetch_page(session, suburb_slug, page)
            if not html:
                logger.warning(f"  No response for {suburb_name} page {page} — stopping")
                break

            soup = BeautifulSoup(html, 'html.parser')
            cards = soup.select('[data-testid="listing-card-wrapper-premiumplus"], '
                                '[data-testid="listing-card-wrapper-standard"]')

            if not cards:
                logger.info(f"  No listings on page {page} — end of results")
                break

            page_count = 0
            for card in cards:
                listing = parse_listing(card, suburb_id)
                if not listing:
                    continue
                if listing_exists(conn, listing['url']):
                    continue
                insert_listing(conn, listing)
                all_raw.append(listing)
                page_count += 1
                suburb_count += 1
                total_inserted += 1

            conn.commit()
            logger.info(f"  Page {page}: {page_count} listings")

            # Randomised polite delay
            time.sleep(time.monotonic() % 1 + DELAY_MIN +
                       (DELAY_MAX - DELAY_MIN) * (hash(suburb_slug + str(page)) % 100) / 100)

        logger.info(f"  {suburb_name} total: {suburb_count}")

    # Save raw backup
    raw_path = os.path.join(RAW_DIR, 'listings_raw.json')
    with open(raw_path, 'w') as f:
        # url and description only — don't bloat the raw file
        json.dump([
            {k: v for k, v in l.items() if k in ('url', 'price', 'suburb_id', 'property_type')}
            for l in all_raw
        ], f, indent=2)

    total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    conn.close()
    logger.info(f"Scrape complete — {total_inserted} new listings inserted ({total} total in DB)")


if __name__ == '__main__':
    scrape_all()