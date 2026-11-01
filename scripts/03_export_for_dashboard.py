"""Export tidy CSVs from the database for Power BI / Tableau / Excel.
Run after 02_load_data.py:  python3 scripts/03_export_for_dashboard.py
"""
import csv, os, sqlite3

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DB = os.path.join(ROOT, "data", "melbourne.db")
OUT = os.path.join(ROOT, "data", "processed")
os.makedirs(OUT, exist_ok=True)

EXPORTS = {
    "area_summary.csv": "SELECT * FROM area_summary ORDER BY area_name",
    "rent_history.csv": """SELECT a.region, a.area_name, r.dwelling, r.period_end, r.median_rent, r.lease_count
                           FROM rent r JOIN rent_area a USING (area_id)
                           ORDER BY a.area_name, r.dwelling, r.period_end""",
    "stations.csv": """SELECT s.name AS station, s.lat, s.lon, s.pax_annual, s.pax_weekday,
                              a.area_name, s.match_method
                       FROM station s LEFT JOIN rent_area a USING (area_id) ORDER BY s.pax_annual DESC""",
}

conn = sqlite3.connect(DB)
for fname, sql in EXPORTS.items():
    cur = conn.execute(sql)
    with open(os.path.join(OUT, fname), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([d[0] for d in cur.description])
        n = 0
        for row in cur:
            w.writerow(row); n += 1
    print(f"wrote data/processed/{fname}: {n} rows")
conn.close()
