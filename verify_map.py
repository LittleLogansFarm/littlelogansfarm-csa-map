#!/usr/bin/env python3
"""Check that the generated HTML actually matches the CSV and config.

Run after generate_map.py:
    python3 generate_map.py && python3 verify_map.py

Exits non-zero if anything is missing, so it is safe to use in CI.
"""

import csv
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent


def main():
    config = json.loads((HERE / "csa_config.json").read_text(encoding="utf-8"))
    out = HERE / config["output_file"]
    if not out.exists():
        sys.exit(f"{out.name} does not exist — run generate_map.py first.")

    html = out.read_text(encoding="utf-8")
    with (HERE / "pickup_locations.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("name") or "").strip()]

    failures = []

    markers = re.findall(r"L\.marker\(\s*\[([-\d.]+),\s*([-\d.]+)\]", html)
    plotted = {(round(float(a), 4), round(float(b), 4)) for a, b in markers}

    for row in rows:
        try:
            point = (round(float(row["latitude"]), 4), round(float(row["longitude"]), 4))
        except (TypeError, ValueError):
            continue  # generate_map.py already warns about unusable coordinates
        if point not in plotted:
            failures.append(f"no marker plotted for '{row['name']}' at {point}")
        if row["name"] not in html:
            failures.append(f"'{row['name']}' does not appear in any popup or tooltip")

    farm = (round(config["farm_latitude"], 4), round(config["farm_longitude"], 4))
    if farm not in plotted:
        failures.append(f"farm marker missing at {farm}")

    circle = re.search(r'L\.circle\(\s*\[([-\d.]+),\s*([-\d.]+)\][\s\S]*?"radius":\s*([\d.]+)', html)
    if not circle:
        failures.append("delivery zone circle missing")
    else:
        expected = config["delivery_radius_miles"] * 1609.344
        actual = float(circle.group(3))
        if abs(actual - expected) > 1:
            failures.append(f"zone radius is {actual:.0f} m, expected {expected:.0f} m")

    if "<title>" not in html.split("</head>")[0]:
        failures.append("page <title> is not in <head>")

    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)

    if failures:
        sys.exit(f"{len(failures)} problem(s) found.")

    print(f"OK — {len(rows)} pickup site(s) + farm marker + {config['delivery_radius_miles']} mi zone all present.")


if __name__ == "__main__":
    main()
