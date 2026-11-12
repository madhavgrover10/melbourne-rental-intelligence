"""Write a short plain-English summary for each rent area using an LLM,
then check that the summary only uses numbers that are in the database.

Run after 02_load_data.py:
    export OPENAI_API_KEY="your-key"       # never put the key in the code
    python3 scripts/04_area_summaries.py --limit 3      # try a few first
    python3 scripts/04_area_summaries.py                # all areas
    python3 scripts/04_area_summaries.py --dry-run      # print prompts, no API call

Results go to the table area_summary_text and to data/processed/area_summaries.csv.
"""
import argparse, csv, os, re, sqlite3

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DB = os.path.join(ROOT, "data", "melbourne.db")
OUT = os.path.join(ROOT, "data", "processed", "area_summaries.csv")
MODEL = os.environ.get("SUMMARY_MODEL", "gpt-4o-mini")

# Numbers that may appear without being in the data (years and "1-year"/"5-year").
ALWAYS_OK = {"1", "5", "2021", "2025"}

# Areas where many residents are students, so household income looks low for reasons
# unrelated to rent stress (see README, Limits). They are never put in the priority group.
STUDENT_AREAS = {"Box Hill", "Carlton-Parkville", "CBD-St Kilda Rd", "Clayton"}

# Recommendation categories are decided by these rules, NOT by the model.
ACTIONS = {
    "Priority": "Look at this area first: both rent growth and rent-to-income are at or above average.",
    "Needs a different measure": "Do not act on the rent-to-income figure alone: many residents are students, so household income is low for other reasons.",
    "Watch: fast rent growth": "Keep watching: rents have risen faster than average, but rent-to-income is below average.",
    "Watch: high rent-to-income": "Keep watching: rent takes a larger share of income than average, but rent growth is below average.",
    "Lower pressure": "No action needed on this data: rent growth and rent-to-income are both below average.",
    "Not assessed": "Cannot be assessed: no household income figure is available for this area.",
}

SYSTEM = """You write a short summary (3 to 4 sentences) about a Melbourne rent area for a general reader, then one final sentence starting "Recommendation:".
Rules:
- Use ONLY the facts and numbers given. Copy numbers exactly as written. Do not round, convert or add new numbers.
- Do not add outside knowledge about the area (no landmarks, schools, reputation).
- Do not explain WHY rents changed. The data shows what happened, not why.
- Say that income is from the 2021 Census and rent is from Sep 2025, so rent-to-income is only a comparison between areas.
- If income is missing, say rent-to-income is not available for this area.
- The recommendation sentence must restate the "Recommended action" fact in your own words. Do not add any other advice.
- Plain text only, no bullet points."""


def fmt_money(x):   return f"${x:,.0f}"
def fmt_pct(x):     return f"{x:.1f}%"


def load_rows(conn):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute("SELECT * FROM area_summary ORDER BY area_name")]


def averages(rows):
    g = [r["rent_growth_5y_pct"] for r in rows if r["rent_growth_5y_pct"] is not None]
    t = [r["rent_to_income_pct"] for r in rows if r["rent_to_income_pct"] is not None]
    return round(sum(g) / len(g), 1), round(sum(t) / len(t), 1)


def category(r, avg_growth, avg_r2i):
    if r["rent_to_income_pct"] is None:
        return "Not assessed"
    high_g = r["rent_growth_5y_pct"] >= avg_growth
    high_t = r["rent_to_income_pct"] >= avg_r2i
    if r["area_name"] in STUDENT_AREAS and (high_t or high_g):
        return "Needs a different measure"
    if high_g and high_t:
        return "Priority"
    if high_g:
        return "Watch: fast rent growth"
    if high_t:
        return "Watch: high rent-to-income"
    return "Lower pressure"


def priority_ranks(rows, avg_growth, avg_r2i):
    """Rank of each Priority area by rent-to-income (1 = highest)."""
    pri = sorted([r for r in rows if category(r, avg_growth, avg_r2i) == "Priority"],
                 key=lambda r: -r["rent_to_income_pct"])
    return {r["area_id"]: i + 1 for i, r in enumerate(pri)}, len(pri)


def facts_for(r, avg_growth, avg_r2i, ranks=None, n_pri=0):
    """Pre-formatted facts. Whatever is in this dict is the only data the model sees."""
    f = {
        "Area": r["area_name"],
        "Region": r["region"],
        "Median weekly rent (Sep 2025)": fmt_money(r["median_rent"]),
        "Rent change over 1 year": fmt_pct(r["rent_growth_1y_pct"]),
        "Rent change over 5 years": fmt_pct(r["rent_growth_5y_pct"]),
        "Average 5-year rent change across all 110 areas": fmt_pct(avg_growth),
        "Train stations in the area": str(r["stations"]),
    }
    if r["stations"]:
        f["Annual train station entries (FY2024-25)"] = f"{r['station_entries']:,}"
    if r["hhd_income_weekly"] is not None and r["rent_to_income_pct"] is not None:
        f["Median household income per week (2021 Census)"] = fmt_money(r["hhd_income_weekly"])
        f["Rent as a share of household income"] = fmt_pct(r["rent_to_income_pct"])
        f["Average rent-to-income across all areas"] = fmt_pct(avg_r2i)
        squeezed = (r["rent_growth_5y_pct"] >= avg_growth and r["rent_to_income_pct"] >= avg_r2i)
        f["Squeezed? (5-year growth AND rent-to-income both at or above average)"] = "yes" if squeezed else "no"
    else:
        f["Household income"] = "not available"
    cat = category(r, avg_growth, avg_r2i)
    f["Category"] = cat
    f["Recommended action"] = ACTIONS[cat]
    if cat == "Priority" and ranks:
        f["Rank among Priority areas by rent-to-income"] = f"{ranks[r['area_id']]} of {n_pri}"
    return f


def numbers_in(text):
    """All numbers in a text, with commas removed: '$1,234.5' -> '1234.5'."""
    return {m.replace(",", "") for m in re.findall(r"\d[\d,]*\.?\d*", text)}


def check(summary, facts):
    """Return the numbers in the summary that are NOT in the facts (empty = pass)."""
    allowed = set(ALWAYS_OK)
    for k, v in facts.items():
        allowed |= numbers_in(str(k)) | numbers_in(str(v))
    return sorted(n.rstrip(".") for n in numbers_in(summary) if n.rstrip(".") not in allowed)


def prompt_for(facts):
    return "Facts:\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items())


def ask_llm(client, facts, note=""):
    resp = client.chat.completions.create(
        model=MODEL, max_completion_tokens=300,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": prompt_for(facts) + note}],
    )
    return resp.choices[0].message.content.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only do the first N areas")
    ap.add_argument("--dry-run", action="store_true", help="print prompts, no API call")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    rows = load_rows(conn)
    if args.limit:
        rows = rows[: args.limit]
    all_rows = load_rows(conn)
    avg_growth, avg_r2i = averages(all_rows)           # averages always over all areas
    ranks, n_pri = priority_ranks(all_rows, avg_growth, avg_r2i)

    if args.dry_run:
        for r in rows[:2]:
            print(SYSTEM, "\n\n", prompt_for(facts_for(r, avg_growth, avg_r2i, ranks, n_pri)), "\n" + "-" * 40)
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. See the instructions at the top of this file.")
    from openai import OpenAI
    client = OpenAI()

    conn.execute("DROP TABLE IF EXISTS area_summary_text")
    conn.execute("""CREATE TABLE area_summary_text (
        area_id INTEGER PRIMARY KEY, summary TEXT, model TEXT,
        passed_check INTEGER, unmatched_numbers TEXT, attempts INTEGER, category TEXT)""")

    results, first_try_pass = [], 0
    for r in rows:
        facts = facts_for(r, avg_growth, avg_r2i, ranks, n_pri)
        summary = ask_llm(client, facts)
        bad = check(summary, facts)
        attempts = 1
        if bad:   # one retry, telling the model what went wrong
            summary = ask_llm(client, facts, f"\n\nYour last draft used numbers that are not in the facts: {', '.join(bad)}. Rewrite using only the facts.")
            bad = check(summary, facts)
            attempts = 2
        else:
            first_try_pass += 1
        passed = int(not bad)
        conn.execute("INSERT OR REPLACE INTO area_summary_text VALUES (?,?,?,?,?,?,?)",
                     (r["area_id"], summary, MODEL, passed, ",".join(bad), attempts, facts["Category"]))
        conn.commit()
        results.append((r["area_name"], summary, MODEL, passed, ",".join(bad), attempts, facts["Category"]))
        print(f"{'PASS' if passed else 'FLAG'}  {r['area_name']}" + (f"  unmatched: {bad}" if bad else ""))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["area_name", "summary", "model", "passed_check", "unmatched_numbers", "attempts", "category"])
        w.writerows(results)

    n = len(results)
    final_pass = sum(r[3] for r in results)
    print(f"\n{n} summaries. Passed the number check on the first try: {first_try_pass}. "
          f"Passed after retry: {final_pass - first_try_pass}. Still flagged: {n - final_pass}.")


if __name__ == "__main__":
    main()
