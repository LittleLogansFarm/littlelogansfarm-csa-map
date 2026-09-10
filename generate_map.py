#!/usr/bin/env python3
"""Build the CSA delivery-zone map from csa_config.json and pickup_locations.csv.

Usage:
    python3 generate_map.py              # rebuild the map
    python3 generate_map.py --check      # validate the data, write nothing
    python3 generate_map.py --geocode    # look up any missing lat/lon by address

Edit pickup_locations.csv to change the map. Do not edit the generated HTML by
hand -- it is overwritten on every run.
"""

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import folium

HERE = Path(__file__).parent
CONFIG_FILE = HERE / "csa_config.json"
LOCATIONS_FILE = HERE / "pickup_locations.csv"
GEOCODE_CACHE = HERE / ".geocode_cache.json"

MILES_PER_METER = 1 / 1609.344
EARTH_RADIUS_MILES = 3958.7613


def miles_between(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def load_config():
    if not CONFIG_FILE.exists():
        sys.exit(f"Missing {CONFIG_FILE.name}. See README.md.")
    with CONFIG_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_locations():
    if not LOCATIONS_FILE.exists():
        sys.exit(f"Missing {LOCATIONS_FILE.name}. See README.md.")
    with LOCATIONS_FILE.open(encoding="utf-8-sig", newline="") as fh:
        rows = [row for row in csv.DictReader(fh) if any((v or "").strip() for v in row.values())]
    for i, row in enumerate(rows, start=2):  # start=2: row 1 is the header
        row["_line"] = i
        for key, value in list(row.items()):
            if isinstance(value, str):
                row[key] = value.strip()
    return rows


def geocode(address, cache, user_agent):
    """Resolve an address to (lat, lon) via OpenStreetMap Nominatim, cached on disk."""
    import urllib.parse
    import urllib.request

    if address in cache:
        return tuple(cache[address])

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": address, "format": "json", "limit": 1}
    )
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=20) as response:
        results = json.load(response)
    time.sleep(1)  # Nominatim asks for no more than one request per second

    if not results:
        return None
    point = (float(results[0]["lat"]), float(results[0]["lon"]))
    cache[address] = list(point)
    return point


def resolve_coordinates(rows, do_geocode, user_agent):
    """Fill in lat/lon for every row. Returns (good_rows, problems)."""
    cache = json.loads(GEOCODE_CACHE.read_text(encoding="utf-8")) if GEOCODE_CACHE.exists() else {}
    good, problems = [], []

    for row in rows:
        name = row.get("name") or f"(unnamed row {row['_line']})"
        lat, lon = row.get("latitude"), row.get("longitude")

        if lat and lon:
            try:
                row["latitude"], row["longitude"] = float(lat), float(lon)
            except ValueError:
                problems.append(f"row {row['_line']} ({name}): latitude/longitude are not numbers")
                continue
            good.append(row)
            continue

        address = row.get("address", "")
        if not do_geocode:
            problems.append(
                f"row {row['_line']} ({name}): no latitude/longitude. "
                f"Add them, or re-run with --geocode to look them up from the address."
            )
            continue
        if not address or address.upper().startswith("REPLACE"):
            problems.append(f"row {row['_line']} ({name}): no coordinates and no real address to geocode")
            continue

        try:
            point = geocode(address, cache, user_agent)
        except Exception as exc:  # network down, rate limited, bad response
            problems.append(f"row {row['_line']} ({name}): geocoding failed ({exc})")
            continue
        if point is None:
            problems.append(f"row {row['_line']} ({name}): address not found — '{address}'")
            continue

        row["latitude"], row["longitude"] = point
        print(f"  geocoded {name}: {point[0]:.5f}, {point[1]:.5f}")
        good.append(row)

    if do_geocode:
        GEOCODE_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")

    return good, problems


def escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def popup_html(row, config):
    parts = [f"<div style='font-family:sans-serif;min-width:190px'>"
             f"<div style='font-size:14px;font-weight:700;margin-bottom:4px'>{escape(row['name'])}</div>"]

    address = row.get("address", "")
    if address and not address.upper().startswith("REPLACE"):
        parts.append(f"<div style='margin-bottom:4px'>{escape(address)}</div>")

    day = row.get("day", "")
    window = " – ".join(t for t in (row.get("start_time", ""), row.get("end_time", "")) if t)
    when = " ".join(p for p in (day, window) if p)
    if when:
        parts.append(f"<div style='margin-bottom:4px'><b>{escape(when)}</b></div>")

    notes = row.get("notes", "")
    if notes and not notes.lower().startswith("delete this row"):
        parts.append(f"<div style='color:#555;font-size:12px'>{escape(notes)}</div>")

    parts.append("</div>")
    return "".join(parts)


def legend_html(config, count):
    radius = config["delivery_radius_miles"]
    return f"""
    <div style="position:fixed;bottom:22px;left:12px;z-index:9999;background:rgba(255,255,255,.94);
                border:1px solid #bbb;border-radius:6px;padding:10px 12px;font-family:sans-serif;
                font-size:12px;line-height:1.5;box-shadow:0 1px 4px rgba(0,0,0,.25);max-width:230px">
      <div style="font-size:13px;font-weight:700;margin-bottom:5px">{escape(config['map_title'])}</div>
      <div><span style="display:inline-block;width:11px;height:11px;background:{escape(config['zone_color'])};
           opacity:.45;border:1px solid {escape(config['zone_color'])};margin-right:6px"></span>
           Delivery zone (~{radius} mi)</div>
      <div><span style="color:#3a7d3a;margin-right:6px">&#9679;</span>Pickup sites ({count})</div>
      <div><span style="color:#1f4d1f;margin-right:6px">&#9733;</span>{escape(config['farm_name'])}</div>
      <div style="margin-top:6px;color:#666;font-size:11px">{escape(config['contact_line'])}</div>
    </div>
    """


def build_map(config, rows):
    center = [config["farm_latitude"], config["farm_longitude"]]
    fmap = folium.Map(location=center, zoom_start=config["map_zoom"], tiles="OpenStreetMap")
    fmap.get_root().header.add_child(folium.Element(f"<title>{escape(config['map_title'])}</title>"))

    folium.Circle(
        location=center,
        radius=config["delivery_radius_miles"] / MILES_PER_METER,
        color=config["zone_color"],
        weight=3,
        fill=True,
        fill_color=config["zone_color"],
        fill_opacity=0.3,
        popup=folium.Popup(escape(config["zone_label"]), max_width="100%"),
    ).add_to(fmap)

    pickups = folium.FeatureGroup(name="Pickup sites").add_to(fmap)
    for row in rows:
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup=folium.Popup(popup_html(row, config), max_width=300),
            tooltip=row["name"],
            icon=folium.Icon(color="green", icon="shopping-basket", prefix="fa"),
        ).add_to(pickups)

    folium.Marker(
        location=center,
        popup=folium.Popup(
            f"<div style='font-family:sans-serif'><b>{escape(config['farm_name'])}</b><br>"
            f"{escape(config['farm_address'])}</div>",
            max_width=300,
        ),
        tooltip=config["farm_name"],
        icon=folium.Icon(color="darkgreen", icon="home", prefix="fa"),
    ).add_to(fmap)

    fmap.get_root().html.add_child(folium.Element(legend_html(config, len(rows))))
    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="validate the data without writing the map")
    parser.add_argument("--geocode", action="store_true", help="look up missing coordinates from addresses")
    parser.add_argument("--output", help="override the output path from csa_config.json")
    args = parser.parse_args()

    config = load_config()
    rows = load_locations()
    user_agent = f"{config['farm_name']} CSA map generator (github.com/LittleLogansFarm/littlelogansfarm-csa-map)"

    rows, problems = resolve_coordinates(rows, args.geocode, user_agent)

    radius = config["delivery_radius_miles"]
    for row in rows:
        distance = miles_between(
            config["farm_latitude"], config["farm_longitude"], row["latitude"], row["longitude"]
        )
        row["_miles"] = distance
        if distance > radius:
            problems.append(
                f"row {row['_line']} ({row['name']}): {distance:.1f} mi from the farm, "
                f"outside the {radius} mi zone"
            )

    for problem in problems:
        print(f"WARNING: {problem}", file=sys.stderr)

    if not rows:
        sys.exit("No usable pickup locations. Fix the warnings above and try again.")

    print(f"{len(rows)} pickup location(s), farthest {max(r['_miles'] for r in rows):.1f} mi from the farm")

    if args.check:
        print("Check only — no files written.")
        return

    out_path = Path(args.output) if args.output else HERE / config["output_file"]
    build_map(config, rows).save(str(out_path))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
