import sqlite3
import os
import json
import logging
import pandas as pd
import folium
from folium.plugins import MarkerCluster

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'melbourne.db')
MAPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'maps')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MELBOURNE_CENTER = [-37.8136, 144.9631]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_data(conn):
    return pd.read_sql_query("""
        SELECT
            s.name                  AS suburb,
            s.latitude,
            s.longitude,
            s.liveability_score,
            s.affordability_score,
            s.transit_score,
            s.walkability_score,
            s.median_weekly_rent,
            s.rent_to_income_ratio,
            s.value_gap,
            s.classification,
            s.honesty_score,
            s.buzzword_inflation_score,
            s.high_spin_rate,
            s.avg_superlative_density,
            i.median_household_weekly   AS median_income,
            t.avg_on_time_pct,
            t.avg_delay_min,
            t.train_lines_count
        FROM suburbs s
        LEFT JOIN income i ON i.suburb_id = s.id
        LEFT JOIN (
            SELECT suburb_id,
                   AVG(on_time_pct)      AS avg_on_time_pct,
                   AVG(avg_delay_min)    AS avg_delay_min,
                   COUNT(DISTINCT line_name) AS train_lines_count
            FROM transit_performance
            WHERE on_time_pct > 0
            GROUP BY suburb_id
        ) t ON t.suburb_id = s.id
        WHERE s.latitude IS NOT NULL
          AND s.liveability_score IS NOT NULL
        ORDER BY s.name
    """, conn)


def color_for_value(value, low, high, palette):
    """Map a value to a hex color from a palette list (low→high)."""
    if pd.isna(value):
        return '#cccccc'
    norm = (value - low) / (high - low) if high != low else 0.5
    norm = max(0.0, min(1.0, norm))
    idx  = int(norm * (len(palette) - 1))
    return palette[idx]


def radius_scale(value, low, high, min_r=8, max_r=22):
    """Scale circle radius between min_r and max_r."""
    if pd.isna(value) or high == low:
        return (min_r + max_r) / 2
    norm = (value - low) / (high - low)
    return min_r + norm * (max_r - min_r)


# Color palettes (light → dark = low → high)
RENT_PALETTE = [
    '#edf8e9','#bae4b3','#74c476','#31a354','#006d2c',
    '#ffeda0','#feb24c','#f03b20','#bd0026','#800026'
]
LIVE_PALETTE = [
    '#f7fbff','#deebf7','#c6dbef','#9ecae1','#6baed6',
    '#4292c6','#2171b5','#08519c','#08306b','#041f4a'
]
GAP_PALETTE = [
    '#d73027','#f46d43','#fdae61','#fee08b','#ffffbf',
    '#d9ef8b','#a6d96a','#66bd63','#1a9850','#006837'
]


def make_rent_map(df):
    """Map 1: Median rent by suburb — warmer = more expensive."""
    m = folium.Map(
        location=MELBOURNE_CENTER, zoom_start=11,
        tiles='CartoDB positron'
    )

    rent_min = df['median_weekly_rent'].min()
    rent_max = df['median_weekly_rent'].max()

    for _, row in df.iterrows():
        if pd.isna(row['latitude']) or pd.isna(row['median_weekly_rent']):
            continue

        color  = color_for_value(row['median_weekly_rent'], rent_min, rent_max, RENT_PALETTE)
        radius = radius_scale(row['median_weekly_rent'], rent_min, rent_max)

        tooltip = f"""
        <b>{row['suburb']}</b><br>
        Median rent: <b>${row['median_weekly_rent']:.0f}/wk</b><br>
        Median income: ${row['median_income']:.0f}/wk<br>
        Rent-to-income: {row['rent_to_income_ratio']:.2f}x<br>
        Liveability: {row['liveability_score']:.1f}/10
        """

        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=1.5,
            tooltip=folium.Tooltip(tooltip, sticky=True),
        ).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:12px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:sans-serif;font-size:12px;">
        <b>Median weekly rent</b><br>
        <span style="color:#006d2c">●</span> Low (&lt;$900)<br>
        <span style="color:#feb24c">●</span> Medium ($1,400–$2,000)<br>
        <span style="color:#800026">●</span> High (&gt;$3,000)<br>
        <i style="color:#888;font-size:11px">Circle size = relative rent</i>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


def make_liveability_map(df):
    """Map 2: Liveability score by suburb — darker blue = more liveable."""
    m = folium.Map(
        location=MELBOURNE_CENTER, zoom_start=11,
        tiles='CartoDB positron'
    )

    live_min = df['liveability_score'].min()
    live_max = df['liveability_score'].max()

    for _, row in df.iterrows():
        if pd.isna(row['latitude']) or pd.isna(row['liveability_score']):
            continue

        color  = color_for_value(row['liveability_score'], live_min, live_max, LIVE_PALETTE)
        radius = radius_scale(row['liveability_score'], live_min, live_max)

        on_time  = f"{row['avg_on_time_pct']:.1f}%" if not pd.isna(row['avg_on_time_pct']) else 'N/A'
        delay    = f"{row['avg_delay_min']:.1f} min" if not pd.isna(row['avg_delay_min']) else 'N/A'
        honesty  = f"{row['honesty_score']:.2f}" if not pd.isna(row['honesty_score']) else 'N/A'

        tooltip = f"""
        <b>{row['suburb']}</b><br>
        Liveability: <b>{row['liveability_score']:.1f}/10</b><br>
        Affordability: {row['affordability_score']:.2f}<br>
        Walkability: {row['walkability_score']:.2f}<br>
        Transit on-time: {on_time}<br>
        Avg delay: {delay}<br>
        Honesty score: {honesty}
        """

        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.80,
            weight=1.5,
            tooltip=folium.Tooltip(tooltip, sticky=True),
        ).add_to(m)

    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:12px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:sans-serif;font-size:12px;">
        <b>Liveability score (0–10)</b><br>
        <span style="color:#deebf7">●</span> Low (&lt;4)<br>
        <span style="color:#4292c6">●</span> Medium (5–6)<br>
        <span style="color:#08306b">●</span> High (&gt;7)<br>
        <i style="color:#888;font-size:11px">Circle size = score magnitude</i>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


def make_value_gap_map(df):
    """
    Map 3: Value gap — liveability rank minus rent rank.
    Green = hidden gem (high liveability, low rent).
    Red = overpriced trap (low liveability, high rent).
    """
    m = folium.Map(
        location=MELBOURNE_CENTER, zoom_start=11,
        tiles='CartoDB positron'
    )

    gap_min = df['value_gap'].min()
    gap_max = df['value_gap'].max()

    classification_colors = {
        'hidden gem':        '#1a9850',
        'fair value':        '#ffffbf',
        'overpriced trap':   '#d73027',
        'insufficient data': '#cccccc',
    }

    for _, row in df.iterrows():
        if pd.isna(row['latitude']) or pd.isna(row['value_gap']):
            continue

        color       = classification_colors.get(row['classification'], '#cccccc')
        border_col  = color_for_value(row['value_gap'], gap_min, gap_max, GAP_PALETTE)
        radius      = radius_scale(abs(row['value_gap']), 0, max(abs(gap_min), abs(gap_max)))

        tooltip = f"""
        <b>{row['suburb']}</b><br>
        Classification: <b>{row['classification']}</b><br>
        Value gap: {row['value_gap']:+.2f}<br>
        Liveability: {row['liveability_score']:.1f}/10<br>
        Median rent: ${row['median_weekly_rent']:.0f}/wk<br>
        Honesty score: {row['honesty_score']:.2f}
        """

        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=radius,
            color=border_col,
            fill=True,
            fill_color=color,
            fill_opacity=0.80,
            weight=2,
            tooltip=folium.Tooltip(tooltip, sticky=True),
        ).add_to(m)

        # Label the most extreme gems and traps
        if abs(row['value_gap']) >= 0.70:
            folium.Marker(
                location=[row['latitude'], row['longitude']],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:10px;font-weight:600;'
                         f'color:{"#006837" if row["value_gap"]>0 else "#8b0000"};'
                         f'white-space:nowrap;text-shadow:0 0 3px white;">'
                         f'{row["suburb"]}</div>',
                    icon_size=(120, 20),
                    icon_anchor=(0, 0),
                )
            ).add_to(m)

    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:12px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.15);font-family:sans-serif;font-size:12px;">
        <b>Value gap (liveability vs rent)</b><br>
        <span style="color:#1a9850">●</span> Hidden gem<br>
        <span style="color:#b8b800">●</span> Fair value<br>
        <span style="color:#d73027">●</span> Overpriced trap<br>
        <i style="color:#888;font-size:11px">Circle size = gap magnitude</i>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m


def main():
    os.makedirs(MAPS_DIR, exist_ok=True)
    conn = get_db()
    df   = load_data(conn)
    conn.close()

    logger.info(f"Loaded {len(df)} suburbs for mapping")

    # Map 1 — Rent
    logger.info("Generating map 1: median rent...")
    m1 = make_rent_map(df)
    m1.save(os.path.join(MAPS_DIR, '01_rent_map.html'))
    logger.info("  Saved → data/maps/01_rent_map.html")

    # Map 2 — Liveability
    logger.info("Generating map 2: liveability score...")
    m2 = make_liveability_map(df)
    m2.save(os.path.join(MAPS_DIR, '02_liveability_map.html'))
    logger.info("  Saved → data/maps/02_liveability_map.html")

    # Map 3 — Value gap
    logger.info("Generating map 3: value gap...")
    m3 = make_value_gap_map(df)
    m3.save(os.path.join(MAPS_DIR, '03_value_gap_map.html'))
    logger.info("  Saved → data/maps/03_value_gap_map.html")

    logger.info("All 3 maps generated.")
    logger.info("Open in browser: open data/maps/01_rent_map.html")


if __name__ == '__main__':
    main()