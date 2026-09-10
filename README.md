# Little Logan's Farm — CSA Delivery Zone Map

An interactive map showing the CSA delivery zone and pickup sites, ready to embed
on the farm website.

**The map is generated.** Edit the data files below and re-run the script — do not
edit `csa_delivery_zone_map.html` by hand, because it is overwritten on every run.

## Updating pickup sites

1. Open `pickup_locations.csv` in a spreadsheet program (Excel, Numbers, Google
   Sheets) or any text editor. One row per pickup site:

   | column | meaning |
   | --- | --- |
   | `name` | Site name shown on the map |
   | `address` | Street address shown in the popup |
   | `day` | e.g. `Tuesday` |
   | `start_time` / `end_time` | e.g. `4:00 PM` / `7:00 PM` |
   | `notes` | Optional extra line (parking, "members only", etc.) |
   | `latitude` / `longitude` | Map position — see below |

   The five `EXAMPLE —` rows are placeholders. Delete them and add the real sites.

2. Rebuild the map:

   ```
   python3 generate_map.py
   ```

3. Open `csa_delivery_zone_map.html` in a browser to check it, then commit.

### Getting latitude and longitude

Either let the script look them up from the address:

```
python3 generate_map.py --geocode
```

(leave `latitude` and `longitude` blank in the CSV; results are cached in
`.geocode_cache.json` so each address is only looked up once)

Or find them by hand: right-click a spot in Google Maps and click the numbers at
the top of the menu to copy them.

## Changing the farm location or delivery radius

Edit `csa_config.json` — farm name and address, map center, `delivery_radius_miles`,
zoom, colors, and the contact line shown in the legend. Then re-run `generate_map.py`.

## Checking your work

```
python3 generate_map.py --check   # validate the CSV without writing the map
python3 verify_map.py             # confirm the built HTML matches the CSV
```

`--check` warns about rows with missing or non-numeric coordinates, addresses it
could not find, and any pickup site that falls outside the delivery radius.

## Setup

Needs Python 3 and folium:

```
pip install folium
```

## Files

| file | what it is |
| --- | --- |
| `pickup_locations.csv` | **Edit this** — the pickup sites |
| `csa_config.json` | **Edit this** — farm location, radius, labels |
| `generate_map.py` | Builds the map from the two files above |
| `verify_map.py` | Checks the built map matches the data |
| `csa_delivery_zone_map.html` | **Generated output** — do not edit by hand |

## A note on the delivery zone

The green circle is a 20-mile straight-line radius from the farm, not a drive
time. In this part of the Hudson Valley the two differ a lot — the ridge and the
river mean some addresses inside the circle are a much longer drive than others
the same distance away. If you would rather show real drive-time boundaries or
delivery-by-ZIP areas, that is a change worth making.
