"""Load real public datasets into SQLite (data/melbourne.db).

Sources (all in data/raw/):
  - DFFH Rental Report: moving annual median rent by suburb and town (Sep 2025 release)
  - ABS 2021 Census General Community Profile, Suburbs & Localities (G01 population, G02 income)
  - Transport Victoria: annual metropolitan train station entries FY2024-25
Run:  python scripts/02_load_data.py
"""
import csv, math, os, re, sqlite3
import openpyxl

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
DB = os.path.join(ROOT, "data", "melbourne.db")

RENT_XLSX = os.path.join(RAW, "dffh", "moving_annual_median_rent_by_suburb_sep2025.xlsx")
ABS_DIR = os.path.join(RAW, "abs")
STATIONS = os.path.join(RAW, "ptv", "annual_metropolitan_train_station_entries_fy_2024_2025.csv")

# DFFH area-name parts that differ from ABS suburb names (None = not a suburb, ignore)
PART_ALIAS = {
    "west st kilda": "St Kilda West", "east st kilda": "St Kilda East",
    "east hawthorn": "Hawthorn East", "east brunswick": "Brunswick East",
    "west brunswick": "Brunswick West", "mt eliza": "Mount Eliza", "mt martha": "Mount Martha",
    "cbd": "Melbourne", "st kilda rd": None,
}
# Stations that sit in an area but are not named after one of its suburbs
STATION_ALIAS = {
    "flinders street": "CBD-St Kilda Rd", "southern cross": "CBD-St Kilda Rd",
    "melbourne central": "CBD-St Kilda Rd", "parliament": "CBD-St Kilda Rd",
    "flagstaff": "CBD-St Kilda Rd",
}
NEAREST_KM = 2.5
SHEETS = ["1 bedroom flat", "2 bedroom flat", "3 bedroom flat",
          "2 bedroom house", "3 bedroom house", "4 bedroom house", "All properties"]
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def clean_suburb(n):
    return re.sub(r"\s*\((Vic\.|Vic)\)$", "", n).strip()


def to_int(v):
    return int(v) if isinstance(v, (int, float)) else None


def haversine(a, b):
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def load_rent(conn):
    wb = openpyxl.load_workbook(RENT_XLSX, read_only=True)
    area_ids, n_rent = {}, 0
    for sheet in SHEETS:
        rows = list(wb[sheet].iter_rows(values_only=True))
        hdr = rows[1]
        cols = []  # (col_index_of_count, period_end)
        for i, v in enumerate(hdr):
            if isinstance(v, str) and i + 1 < len(hdr) and re.match(r"^[A-Z][a-z]{2} \d{4}$", v):
                mon, yr = v.split()
                if rows[2][i] == "Count":
                    cols.append((i, f"{yr}-{MONTHS[mon]:02d}"))
        region = None
        for r in rows[3:]:
            if r[0]:
                region = r[0]
            area = r[1]
            if not area or not region or area == "Group Total":
                continue
            if not ("Melbourne" in region or region == "Mornington Peninsula"):
                continue  # Greater Melbourne only
            if area not in area_ids:
                cur = conn.execute("INSERT INTO rent_area(region, area_name) VALUES (?,?)", (region, area))
                area_ids[area] = cur.lastrowid
            for ci, period in cols:
                cnt, med = to_int(r[ci]), to_int(r[ci + 1])
                if cnt is None and med is None:
                    continue
                conn.execute("INSERT OR REPLACE INTO rent VALUES (?,?,?,?,?)",
                             (area_ids[area], sheet, period, cnt, med))
                n_rent += 1
    return area_ids, n_rent


def load_abs(conn, area_ids):
    wb = openpyxl.load_workbook(os.path.join(ABS_DIR, "2021Census_geog_desc_1st_2nd_3rd_release.xlsx"), read_only=True)
    names = {}
    for s in wb.sheetnames:
        for r in wb[s].iter_rows(values_only=True):
            if r and r[0] == "SAL":
                names[str(r[1])] = r[3]
    pop = {x["SAL_CODE_2021"]: int(x["Tot_P_P"]) for x in csv.DictReader(open(os.path.join(ABS_DIR, "2021Census_G01_VIC_SAL.csv")))}
    inc = {x["SAL_CODE_2021"]: int(x["Median_tot_hhd_inc_weekly"]) for x in csv.DictReader(open(os.path.join(ABS_DIR, "2021Census_G02_VIC_SAL.csv")))}
    by_name = {}
    for code, nm in names.items():
        if code in inc:
            by_name.setdefault(clean_suburb(nm).lower(), []).append(code)
    unmatched, n = [], 0
    for area, aid in area_ids.items():
        for part in [p.strip() for p in area.split("-")]:
            key, method = part.lower(), "exact"
            if key in PART_ALIAS:
                alias = PART_ALIAS[key]
                if alias is None:
                    continue
                key, method = alias.lower(), "alias"
            codes = by_name.get(key)
            if not codes:
                unmatched.append((area, part))
                continue
            code = max(codes, key=lambda c: pop.get(c, 0))
            income = inc[code] or None  # 0 = no data
            conn.execute("INSERT OR REPLACE INTO area_suburb VALUES (?,?,?,?,?,?)",
                         (aid, clean_suburb(names[code]), code, pop.get(code), income, method))
            n += 1
    return n, unmatched


def load_stations(conn, area_ids):
    suburb_to_area = {}
    for aid, nm in conn.execute("SELECT area_id, abs_name FROM area_suburb"):
        suburb_to_area.setdefault(nm.lower(), aid)
    rows = list(csv.DictReader(open(STATIONS, encoding="utf-8-sig")))
    placed = {}
    for r in rows:
        nm = r["Stop_name"].strip()
        key = nm.lower()
        aid, method = None, "unmatched"
        if key in STATION_ALIAS:
            aid, method = area_ids[STATION_ALIAS[key]], "alias"
        elif key in suburb_to_area:
            aid, method = suburb_to_area[key], "name"
        placed[r["Stop_ID"]] = [aid, method]
    coords = {r["Stop_ID"]: (float(r["Stop_lat"]), float(r["Stop_long"])) for r in rows}
    anchors = [(sid, coords[sid]) for sid, (aid, m) in placed.items() if aid]
    for sid, (aid, m) in list(placed.items()):
        if aid:
            continue
        best = min(((haversine(coords[sid], c), s) for s, c in anchors), default=None)
        if best and best[0] <= NEAREST_KM:
            placed[sid] = [placed[best[1]][0], "nearest"]
    for r in rows:
        aid, method = placed[r["Stop_ID"]]
        conn.execute("INSERT OR REPLACE INTO station VALUES (?,?,?,?,?,?,?,?)",
                     (int(r["Stop_ID"]), r["Stop_name"].strip(), float(r["Stop_lat"]), float(r["Stop_long"]),
                      int(r["Pax_annual"]), int(r["Pax_weekday"]), aid, method))
    return len(rows)


def main():
    if os.path.exists(DB):
        os.remove(DB)
    conn = sqlite3.connect(DB)
    conn.executescript(open(os.path.join(ROOT, "scripts", "01_create_schema.sql")).read())
    area_ids, n_rent = load_rent(conn)
    n_sub, unmatched = load_abs(conn, area_ids)
    n_st = load_stations(conn, area_ids)
    conn.commit()
    print(f"rent areas: {len(area_ids)} | rent rows: {n_rent} | area-suburb links: {n_sub} | stations: {n_st}")
    print("unmatched area parts:", unmatched)
    for m, c in conn.execute("SELECT match_method, COUNT(*) FROM station GROUP BY 1"):
        print("stations", m, c)
    conn.close()


if __name__ == "__main__":
    main()
