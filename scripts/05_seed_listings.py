import sqlite3
import os
import random
import uuid
from datetime import datetime, timedelta
import logging

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

random.seed(42)

# -------------------------------------------------------------------
# Suburb config: (lat, lng, price_range, property_mix)
# price_range: (min_pw, max_pw) realistic weekly rent
# mix: weights for [house, unit, apartment]
# -------------------------------------------------------------------
SUBURB_CONFIG = {
    "Melbourne":       ((-37.8136, 144.9631), (1800, 4500), [0.05, 0.35, 0.60]),
    "Docklands":       ((-37.8140, 144.9470), (2200, 5000), [0.00, 0.25, 0.75]),
    "Southbank":       ((-37.8230, 144.9630), (2000, 4800), [0.00, 0.20, 0.80]),
    "South Yarra":     ((-37.8388, 144.9929), (1600, 3800), [0.10, 0.35, 0.55]),
    "Toorak":          ((-37.8389, 145.0145), (2500, 6500), [0.45, 0.35, 0.20]),
    "Richmond":        ((-37.8183, 144.9981), (1400, 3200), [0.20, 0.40, 0.40]),
    "Fitzroy":         ((-37.7990, 144.9782), (1400, 3000), [0.25, 0.40, 0.35]),
    "Fitzroy North":   ((-37.7870, 144.9782), (1300, 2800), [0.30, 0.40, 0.30]),
    "Collingwood":     ((-37.8030, 144.9870), (1300, 2800), [0.20, 0.45, 0.35]),
    "Abbotsford":      ((-37.8042, 144.9999), (1300, 2600), [0.25, 0.45, 0.30]),
    "Carlton":         ((-37.7941, 144.9672), (1200, 2600), [0.15, 0.40, 0.45]),
    "Prahran":         ((-37.8497, 144.9920), (1400, 3000), [0.15, 0.40, 0.45]),
    "Windsor":         ((-37.8558, 144.9910), (1300, 2800), [0.20, 0.45, 0.35]),
    "Balaclava":       ((-37.8671, 144.9930), (1300, 2700), [0.20, 0.45, 0.35]),
    "St Kilda":        ((-37.8582, 144.9741), (1300, 3000), [0.15, 0.40, 0.45]),
    "St Kilda East":   ((-37.8666, 144.9960), (1200, 2700), [0.20, 0.45, 0.35]),
    "Elwood":          ((-37.8793, 144.9849), (1400, 3200), [0.30, 0.40, 0.30]),
    "Albert Park":     ((-37.8425, 144.9549), (1600, 3500), [0.35, 0.40, 0.25]),
    "Port Melbourne":  ((-37.8362, 144.9284), (1500, 3200), [0.25, 0.40, 0.35]),
    "South Melbourne": ((-37.8305, 144.9592), (1500, 3200), [0.20, 0.40, 0.40]),
    "Armadale":        ((-37.8555, 145.0176), (1500, 3500), [0.35, 0.40, 0.25]),
    "Malvern":         ((-37.8569, 145.0300), (1600, 3800), [0.40, 0.38, 0.22]),
    "Hawthorn":        ((-37.8225, 145.0341), (1500, 3500), [0.35, 0.40, 0.25]),
    "Camberwell":      ((-37.8328, 145.0580), (1500, 3500), [0.40, 0.38, 0.22]),
    "Kew":             ((-37.8053, 145.0363), (1500, 3500), [0.45, 0.35, 0.20]),
    "Northcote":       ((-37.7696, 145.0007), (1200, 2600), [0.35, 0.40, 0.25]),
    "Thornbury":       ((-37.7545, 145.0057), (1100, 2400), [0.35, 0.40, 0.25]),
    "Preston":         ((-37.7445, 145.0127), (1000, 2200), [0.40, 0.38, 0.22]),
    "Reservoir":       ((-37.7172, 145.0073), (950,  2000), [0.45, 0.38, 0.17]),
    "Brunswick":       ((-37.7666, 144.9604), (1200, 2500), [0.30, 0.42, 0.28]),
    "Coburg":          ((-37.7437, 144.9643), (1000, 2200), [0.38, 0.40, 0.22]),
    "Pascoe Vale":     ((-37.7290, 144.9380), (950,  2000), [0.45, 0.38, 0.17]),
    "Glenroy":         ((-37.7033, 144.9283), (900,  1900), [0.50, 0.35, 0.15]),
    "Moonee Ponds":    ((-37.7655, 144.9211), (1100, 2400), [0.35, 0.40, 0.25]),
    "Essendon":        ((-37.7518, 144.9150), (1100, 2400), [0.40, 0.38, 0.22]),
    "Ascot Vale":      ((-37.7772, 144.9178), (1100, 2300), [0.38, 0.40, 0.22]),
    "Footscray":       ((-37.7998, 144.8989), (950,  2100), [0.30, 0.42, 0.28]),
    "Yarraville":      ((-37.8167, 144.8892), (1000, 2200), [0.38, 0.40, 0.22]),
    "Seddon":          ((-37.8058, 144.8865), (1000, 2100), [0.40, 0.38, 0.22]),
    "Sunshine":        ((-37.7886, 144.8327), (850,  1800), [0.50, 0.35, 0.15]),
    "Williamstown":    ((-37.8607, 144.8985), (1200, 2600), [0.42, 0.38, 0.20]),
    "Werribee":        ((-37.9020, 144.6621), (750,  1600), [0.55, 0.33, 0.12]),
    "Point Cook":      ((-37.8922, 144.7472), (800,  1750), [0.55, 0.33, 0.12]),
    "Tarneit":         ((-37.8530, 144.6890), (750,  1650), [0.58, 0.30, 0.12]),
    "Brighton":        ((-37.9053, 144.9856), (1600, 4000), [0.45, 0.35, 0.20]),
    "Bentleigh":       ((-37.9191, 145.0360), (1200, 2600), [0.42, 0.38, 0.20]),
    "Moorabbin":       ((-37.9281, 145.0618), (1100, 2300), [0.42, 0.38, 0.20]),
    "Cheltenham":      ((-37.9574, 145.0569), (1100, 2300), [0.42, 0.38, 0.20]),
    "Mentone":         ((-37.9821, 145.0683), (1100, 2400), [0.42, 0.38, 0.20]),
    "Caulfield":       ((-37.8772, 145.0230), (1200, 2700), [0.30, 0.42, 0.28]),
    "Oakleigh":        ((-37.9001, 145.0883), (1000, 2200), [0.40, 0.38, 0.22]),
    "Clayton":         ((-37.9254, 145.1198), (950,  2000), [0.40, 0.38, 0.22]),
    "Glen Waverley":   ((-37.8784, 145.1649), (1100, 2400), [0.45, 0.35, 0.20]),
    "Box Hill":        ((-37.8192, 145.1218), (1000, 2200), [0.38, 0.40, 0.22]),
    "Doncaster":       ((-37.7858, 145.1265), (1100, 2400), [0.45, 0.35, 0.20]),
    "Ivanhoe":         ((-37.7687, 145.0457), (1200, 2600), [0.45, 0.35, 0.20]),
    "Heidelberg":      ((-37.7558, 145.0668), (1000, 2200), [0.42, 0.38, 0.20]),
    "Northcote":       ((-37.7696, 145.0007), (1200, 2600), [0.35, 0.40, 0.25]),
    "Eltham":          ((-37.7139, 145.1480), (1000, 2200), [0.55, 0.33, 0.12]),
    "Greensborough":   ((-37.7038, 145.1015), (950,  2000), [0.52, 0.33, 0.15]),
    "Bundoora":        ((-37.6982, 145.0600), (900,  1900), [0.48, 0.35, 0.17]),
    "South Morang":    ((-37.6523, 145.0930), (850,  1850), [0.52, 0.33, 0.15]),
    "Craigieburn":     ((-37.6003, 144.9460), (780,  1650), [0.58, 0.30, 0.12]),
    "Sunbury":         ((-37.5767, 144.7267), (750,  1600), [0.60, 0.28, 0.12]),
    "Broadmeadows":    ((-37.6815, 144.9208), (750,  1550), [0.55, 0.33, 0.12]),
    "Frankston":       ((-38.1432, 145.1254), (800,  1750), [0.50, 0.35, 0.15]),
    "Dandenong":       ((-37.9875, 145.2147), (750,  1600), [0.48, 0.35, 0.17]),
    "Berwick":         ((-38.0358, 145.3530), (850,  1850), [0.55, 0.33, 0.12]),
    "Narre Warren":    ((-38.0290, 145.3020), (800,  1750), [0.55, 0.33, 0.12]),
    "Cranbourne":      ((-38.0999, 145.2838), (750,  1600), [0.58, 0.30, 0.12]),
    "Pakenham":        ((-38.0712, 145.4875), (700,  1550), [0.60, 0.28, 0.12]),
}

PROPERTY_TYPES = ["house", "unit", "apartment"]

# -------------------------------------------------------------------
# Description templates — designed for P2 NLP
# Mix of honest and euphemistic language across tiers
# -------------------------------------------------------------------

# Euphemistic / high-spin templates (triggers LLM detection in P2)
SPIN_TEMPLATES = [
    "Nestled in the heart of {suburb}, this {adj} {prop_type} offers an unparalleled urban lifestyle. "
    "Featuring {beds} generous bedrooms and {baths} sleek bathrooms, you'll love the {adj2} open-plan living. "
    "A short stroll to vibrant cafes, stunning parks, and excellent transport links. "
    "Perfect for those seeking a cosy yet sophisticated inner-city retreat. Don't miss this rare opportunity!",

    "Welcome to your dream {prop_type} in sought-after {suburb}! This {adj} home boasts {beds} spacious bedrooms, "
    "{baths} gorgeous bathrooms, and a {adj2} kitchen that will inspire your inner chef. "
    "Moments from world-class dining, boutique shopping, and effortless commuting options. "
    "Character-filled and full of potential — a savvy investor's delight.",

    "Perfectly positioned in the vibrant {suburb} precinct, this {adj} {prop_type} is a true entertainer's paradise. "
    "{beds} light-filled bedrooms, {baths} contemporary bathrooms, and a {adj2} alfresco entertaining area. "
    "Walking distance to bustling nightlife, artisan coffee, and seamless public transport. "
    "Stylish, functional, and absolutely stunning — inspect today!",

    "Rarely does a {prop_type} of this calibre come to market in {suburb}. {beds} oversized bedrooms, "
    "{baths} luxurious bathrooms, and {adj} finishes throughout. The {adj2} courtyard is perfect for relaxed weekend entertaining. "
    "Minutes from exceptional schools, lush parklands, and convenient shopping. An absolute must-see.",

    "This {adj} {prop_type} in {suburb} ticks every box. {beds} well-proportioned bedrooms, {baths} modern bathrooms, "
    "and a {adj2} open-plan layout designed for contemporary living. "
    "Surrounded by vibrant eateries, boutique retailers, and reliable transport options. "
    "Low maintenance, high appeal — ideal for busy professionals or savvy investors.",
]

# Honest / neutral templates (lower spin score in P2)
HONEST_TEMPLATES = [
    "{beds}-bedroom {prop_type} in {suburb}. Includes {baths} bathroom(s) and {parking} parking. "
    "Kitchen updated in 2021. Approximately {walk_time} min walk to nearest train station. "
    "Street parking available. Pet-friendly on application. Available from {avail_date}.",

    "Neat {beds}-bed {prop_type} located in {suburb}. {baths} bathroom, {parking} car space. "
    "Close to {suburb} shops and public transport. Small backyard. "
    "Some cosmetic work needed. No dishwasher. Bond: 4 weeks rent. Unfurnished.",

    "{beds} bedroom {prop_type} in {suburb}. Timber floors, good natural light. {baths} bathroom. "
    "On-street parking only. About {walk_time} minutes to the nearest tram/train stop on foot. "
    "Laundry in common area. No pets. Inspections by appointment.",

    "Well-maintained {beds}-bedroom {prop_type} in {suburb}. Updated bathroom ({baths} total), "
    "functional kitchen, and separate laundry. {parking} off-street parking. "
    "Near local schools and supermarket. Quiet street. Available {avail_date}.",

    "{beds} bed / {baths} bath {prop_type} in {suburb}. Built circa 1990s, maintained condition. "
    "Small courtyard, no garage. Walking distance to bus stop ({walk_time} min). "
    "Close to {suburb} primary school and local shops. Inspection times on request.",
]

# Euphemism-heavy red flag templates (high inflation score in P2)
REDFLAG_TEMPLATES = [
    "Charming and cosy {prop_type} in {suburb} — ideal for someone who appreciates character! "
    "{beds} bedrooms with plenty of natural light (east-facing). {baths} bathroom. "
    "The {adj2} kitchen has bags of potential for the creative cook. "
    "Easy-care garden. A short drive to amenities. Great bones — ready for your personal touch.",

    "Investor special or first home buyer's dream in {suburb}! This solid {prop_type} features "
    "{beds} comfortable bedrooms and {baths} functional bathroom. The {adj} interior offers "
    "a blank canvas for renovation. Priced to reflect current condition. "
    "Huge upside potential in a tightly-held pocket. Inspect with fresh eyes!",

    "Don't judge a book by its cover — this {suburb} {prop_type} has so much to offer! "
    "{beds} bedrooms, {baths} bathroom, and a {adj2} backyard perfect for kids or a veggie patch. "
    "Original features throughout. Some updating required but priced accordingly. "
    "Minutes from transport and local shops. Act fast — won't last at this price!",
]

ADJECTIVES = [
    "stunning", "gorgeous", "magnificent", "exceptional", "incredible",
    "beautiful", "charming", "delightful", "impressive", "outstanding",
    "spectacular", "wonderful", "superb", "sensational", "brilliant"
]

ADJECTIVES2 = [
    "light-filled", "sun-drenched", "spacious", "contemporary", "modern",
    "stylish", "elegant", "sleek", "open-plan", "entertainer's"
]


def make_description(suburb, prop_type, beds, baths, parking):
    """Generate a listing description with varied spin levels for P2 NLP."""
    # Weight: 40% spin, 40% honest, 20% red flag
    roll = random.random()
    if roll < 0.40:
        template = random.choice(SPIN_TEMPLATES)
    elif roll < 0.80:
        template = random.choice(HONEST_TEMPLATES)
    else:
        template = random.choice(REDFLAG_TEMPLATES)

    avail_date = (datetime.now() + timedelta(days=random.randint(7, 45))).strftime("%d %B %Y")
    walk_time = random.randint(3, 18)

    return template.format(
        suburb=suburb,
        prop_type=prop_type,
        beds=beds,
        baths=baths,
        parking=parking,
        adj=random.choice(ADJECTIVES),
        adj2=random.choice(ADJECTIVES2),
        avail_date=avail_date,
        walk_time=walk_time,
    )


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_suburb(conn, name):
    row = conn.execute(
        "SELECT id FROM suburbs WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    if row:
        return row['id']
    cursor = conn.execute("INSERT INTO suburbs (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid


def seed_listings(target=1200):
    conn = get_db()
    inserted = 0
    suburbs = list(SUBURB_CONFIG.items())

    # Distribute listings proportionally — inner suburbs get more
    # Roughly 12–20 listings per suburb across 68 suburbs = ~1200 total
    per_suburb = max(12, target // len(suburbs))

    logger.info(f"Seeding ~{per_suburb} listings per suburb across {len(suburbs)} suburbs...")

    for suburb, ((lat, lng), (price_min, price_max), mix) in suburbs:
        suburb_id = get_or_create_suburb(conn, suburb)
        count = per_suburb + random.randint(-3, 5)  # slight variance per suburb

        for _ in range(count):
            prop_type = random.choices(PROPERTY_TYPES, weights=mix, k=1)[0]

            # Bedroom/bathroom/parking logic by property type
            if prop_type == "house":
                beds    = random.choices([2, 3, 4, 5], weights=[0.15, 0.45, 0.30, 0.10])[0]
                baths   = random.choices([1, 2, 3],    weights=[0.25, 0.55, 0.20])[0]
                parking = random.choices([0, 1, 2],    weights=[0.10, 0.55, 0.35])[0]
            elif prop_type == "unit":
                beds    = random.choices([1, 2, 3],    weights=[0.30, 0.55, 0.15])[0]
                baths   = random.choices([1, 2],       weights=[0.65, 0.35])[0]
                parking = random.choices([0, 1],       weights=[0.35, 0.65])[0]
            else:  # apartment
                beds    = random.choices([1, 2, 3],    weights=[0.45, 0.45, 0.10])[0]
                baths   = random.choices([1, 2],       weights=[0.70, 0.30])[0]
                parking = random.choices([0, 1],       weights=[0.50, 0.50])[0]

            # Price: scale loosely with beds, jitter within suburb range
            base_price = random.randint(price_min, price_max)
            bed_premium = (beds - 2) * random.randint(50, 150)
            price = max(price_min, round((base_price + bed_premium) / 5) * 5)

            # Coordinates: small jitter around suburb centroid
            jitter_lat = lat + random.uniform(-0.012, 0.012)
            jitter_lng = lng + random.uniform(-0.012, 0.012)

            # Scraped timestamp: spread over last 90 days
            days_ago = random.randint(0, 90)
            scraped_at = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")

            bond = price * 4
            days_on_market = random.randint(1, 45)
            url = f"https://www.domain.com.au/rent/{suburb.lower().replace(' ', '-')}-vic-{random.randint(10000,99999)}"
            description = make_description(suburb, prop_type, beds, baths, parking)

            conn.execute("""
                INSERT INTO listings
                    (suburb_id, price_weekly, bedrooms, bathrooms,
                    property_type, address, description, listing_url, source, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                suburb_id, price, beds, baths,
                prop_type,
                f"{suburb}, VIC",
                description, url, 'seeded', scraped_at
            ))
            inserted += 1

        conn.commit()
        logger.info(f"  {suburb}: {count} listings")

    total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    conn.close()
    logger.info(f"Done — {total} total listings in DB ({inserted} inserted this run)")


if __name__ == '__main__':
    seed_listings(target=1200)