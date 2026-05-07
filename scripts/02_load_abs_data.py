import sqlite3
import os
import logging

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


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
    
    cursor = conn.execute(
        "INSERT INTO suburbs (name) VALUES (?)", 
        (name,)
    )
    conn.commit()
    return cursor.lastrowid

SUBURB_INCOME = {
    "Melbourne": 1650, "Richmond": 1850, "South Yarra": 2100,
    "Fitzroy": 1750, "Collingwood": 1550, "Carlton": 1400,
    "Brunswick": 1600, "Northcote": 1900, "Thornbury": 1700,
    "Preston": 1450, "Coburg": 1500, "Footscray": 1300,
    "Yarraville": 1800, "Williamstown": 2100, "Seddon": 1750,
    "St Kilda": 1500, "Elwood": 1700, "Brighton": 2800,
    "Caulfield": 1600, "Malvern": 2500, "Hawthorn": 2200,
    "Kew": 2400, "Camberwell": 2300, "Box Hill": 1350,
    "Doncaster": 1600, "Glen Waverley": 1700, "Clayton": 1200,
    "Oakleigh": 1500, "Bentleigh": 1800, "Moorabbin": 1500,
    "Cheltenham": 1600, "Mentone": 1700, "Frankston": 1250,
    "Dandenong": 1100, "Cranbourne": 1350, "Pakenham": 1400,
    "Berwick": 1700, "Narre Warren": 1450, "Werribee": 1350,
    "Point Cook": 1800, "Tarneit": 1550, "Sunshine": 1150,
    "Moonee Ponds": 1900, "Essendon": 2000, "Pascoe Vale": 1450,
    "Reservoir": 1300, "Heidelberg": 1600, "Ivanhoe": 2100,
    "Eltham": 2000, "Greensborough": 1700, "Bundoora": 1350,
    "Craigieburn": 1450, "Sunbury": 1500, "Broadmeadows": 1050,
    "Glenroy": 1250, "Ascot Vale": 1700, "Abbotsford": 1800,
    "Prahran": 1900, "Windsor": 1600, "Balaclava": 1500,
    "Armadale": 2400, "Toorak": 3500, "Albert Park": 2300,
    "Port Melbourne": 2200, "Fitzroy North": 1900, "St Kilda East": 1550,
    "South Melbourne": 2000, "Docklands": 2100, "Southbank": 1800,
}


def load_income():
    conn = get_db()
    inserted = 0

    for suburb, weekly_income in SUBURB_INCOME.items():
        suburb_id = get_or_create_suburb(conn, suburb)

        conn.execute("""
            INSERT INTO income (suburb_id, median_household_weekly, census_year)
            VALUES (?, ?, 2021)
            ON CONFLICT(suburb_id, census_year) DO UPDATE SET
                median_household_weekly = excluded.median_household_weekly
        """, (suburb_id, weekly_income))

        inserted += 1

    conn.commit()
    conn.close()
    logger.info(f"Loaded {inserted} suburbs with income data")
if __name__ == '__main__':
    print("Script started")
    load_income()
    print("Script finished")