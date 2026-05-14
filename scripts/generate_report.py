#!/usr/bin/env python3
"""
Generate a well-depth report for an address.

  python3 generate_report.py "1234 County Rd 100, Liberty Hill, TX"

Output: reports/<slug>.html — a self-contained page with a Leaflet map and a
list of the 10 closest TWDB water wells, each linked to its TWDB report.

Requires the GOOGLE_MAPS_API_KEY environment variable for geocoding.
"""

import argparse
import csv
import html as html_lib
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WELLS_CSV = ROOT / "data" / "wells.csv"
REPORTS_DIR = ROOT / "docs"

TWDB_REPORT_URL = (
    "https://www3.twdb.texas.gov/apps/WaterDataInteractive/"
    "GetReports.aspx?Num={tn}&Type=ReportWellMain&Source=W"
)

# Restrict the nearest-neighbor search to wells that actually supply water,
# not environmental borings, monitor wells, geothermal loops, etc.
WATER_USES = {
    "Domestic", "Irrigation", "Stock", "Public Supply",
    "Industrial", "Rig Supply", "Fracking Supply",
}


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "report"


def geocode(address: str, api_key: str):
    """Return (lat, lon, formatted_address) for the address."""
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json?"
        + urllib.parse.urlencode({"address": address, "key": api_key})
    )
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.load(resp)
    if data.get("status") != "OK" or not data.get("results"):
        raise SystemExit(
            f"Geocoding failed: status={data.get('status')} "
            f"error={data.get('error_message', '')}"
        )
    top = data["results"][0]
    loc = top["geometry"]["location"]
    return loc["lat"], loc["lng"], top["formatted_address"]


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.7613  # Earth radius in miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_wells(lat, lon, k=10):
    """Scan the CSV and keep the k nearest wells. Pre-filter by a bounding box
    that grows until we have enough candidates."""
    candidates = []
    # ~1 degree latitude ~= 69 miles, longitude varies by cos(lat).
    # Start small (~0.25°, ~17 miles) and grow if we don't get enough.
    for box in (0.25, 0.75, 2.0, 5.0, 12.0):
        lat_min, lat_max = lat - box, lat + box
        lon_min, lon_max = lon - box, lon + box
        candidates = []
        with WELLS_CSV.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    wl = float(row["lat"])
                    wn = float(row["lon"])
                except ValueError:
                    continue
                if not (lat_min <= wl <= lat_max and lon_min <= wn <= lon_max):
                    continue
                if (row.get("proposed_use") or "").strip() not in WATER_USES:
                    continue
                d = haversine_miles(lat, lon, wl, wn)
                candidates.append((d, row))
        if len(candidates) >= k:
            break
    candidates.sort(key=lambda x: x[0])
    return candidates[:k]


def recommend_depth(wells):
    """Pick a recommended depth and (optionally) an alternative.

    Recommended = deepest well of the ten.
    Alternative = the next deepest *meaningfully different* depth (>=20 ft
    shallower than recommended), if one exists. If two or more wells cluster
    at or near the recommended depth, mention how many for confidence.
    """
    depths = [(float(r["depth_ft"]), r) for _, r in wells]
    depths.sort(key=lambda x: -x[0])
    recommended_depth, _ = depths[0]
    cluster_at_top = sum(1 for d, _ in depths if recommended_depth - d <= 10)

    alternative = None
    for d, _ in depths[1:]:
        if recommended_depth - d >= 20:
            alternative = d
            break

    return {
        "recommended_ft": recommended_depth,
        "cluster_at_top": cluster_at_top,
        "alternative_ft": alternative,
    }


# ---------- HTML rendering ---------------------------------------------------


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Water Well Depth Report — {address_html}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {{
      --fg:#1c1c1e; --muted:#666; --bg:#f7f7f8; --card:#fff;
      --accent:#0b6bcb; --accent-soft:#e8f1fb; --border:#e4e4e7;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,Inter,Helvetica,Arial,sans-serif;
      color:var(--fg); background:var(--bg);
    }}
    .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
    header h1 {{ margin:0 0 4px; font-size:22px; }}
    header .sub {{ color:var(--muted); margin-bottom:20px; }}
    .summary {{
      background:var(--card); border:1px solid var(--border); border-radius:10px;
      padding:18px 20px; margin-bottom:20px; display:flex; flex-wrap:wrap; gap:24px;
    }}
    .stat .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    .stat .value {{ font-size:22px; font-weight:600; }}
    .stat .value small {{ font-size:13px; font-weight:400; color:var(--muted); margin-left:4px; }}
    .rationale {{ flex:1 1 280px; color:var(--muted); font-size:14px; align-self:center; }}
    #map {{ height:480px; border:1px solid var(--border); border-radius:10px; margin-bottom:20px; }}
    table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--border); border-radius:10px; overflow:hidden; }}
    th, td {{ padding:10px 12px; text-align:left; font-size:14px; border-bottom:1px solid var(--border); }}
    th {{ background:#fafafa; color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    tr:last-child td {{ border-bottom:0; }}
    tr.recommended td {{ background:var(--accent-soft); }}
    a {{ color:var(--accent); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; background:var(--accent); color:#fff; font-size:11px; margin-left:6px; }}
    footer {{ margin-top:24px; font-size:12px; color:var(--muted); }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Water Well Depth Report</h1>
      <div class="sub">{address_html} &middot; generated {generated_at}</div>
    </header>

    <section class="summary">
      <div class="stat">
        <div class="label">Recommended depth</div>
        <div class="value">{rec_ft} ft<small>{rec_meta}</small></div>
      </div>
      {alt_block}
      <div class="stat">
        <div class="label">Wells analyzed</div>
        <div class="value">{n_wells}<small>within {max_dist} mi</small></div>
      </div>
      <div class="rationale">{rationale}</div>
    </section>

    <div id="map"></div>

    <table>
      <thead>
        <tr>
          <th>#</th><th>Depth (ft)</th><th>Distance (mi)</th>
          <th>Owner / Address</th><th>County</th><th>Drilled</th><th>Well Log</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>

    <footer>
      Source: Texas Water Development Board Submitted Driller's Reports
      (<a href="https://www.twdb.texas.gov/groundwater/data/drillersdb.asp" target="_blank" rel="noopener">TWDB SDR</a>).
      Recommended depth is the deepest of the 10 nearest wells; consult a licensed driller before committing.
    </footer>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const data = {data_json};
    const map = L.map('map').setView([data.center.lat, data.center.lon], 11);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; OpenStreetMap',
      maxZoom: 19,
    }}).addTo(map);

    const subjectIcon = L.divIcon({{
      className: 'subject-icon',
      html: '<div style="background:#d00;border:2px solid #fff;border-radius:50%;width:16px;height:16px;box-shadow:0 0 0 2px #d00;"></div>',
      iconSize: [16,16], iconAnchor: [8,8]
    }});
    L.marker([data.center.lat, data.center.lon], {{icon: subjectIcon}})
      .addTo(map)
      .bindPopup('<b>Subject address</b><br>' + data.center.address);

    const bounds = [[data.center.lat, data.center.lon]];
    data.wells.forEach((w, i) => {{
      const isRec = w.is_recommended;
      const color = isRec ? '#0b6bcb' : '#444';
      const icon = L.divIcon({{
        className: 'well-icon',
        html: `<div style="background:${{color}};color:#fff;border:2px solid #fff;border-radius:50%;width:24px;height:24px;line-height:20px;text-align:center;font-size:12px;font-weight:600;box-shadow:0 1px 4px rgba(0,0,0,.3);">${{i+1}}</div>`,
        iconSize: [24,24], iconAnchor: [12,12]
      }});
      L.marker([w.lat, w.lon], {{icon}})
        .addTo(map)
        .bindPopup(
          `<b>Well #${{i+1}}${{isRec ? ' &middot; recommended' : ''}}</b><br>` +
          `Depth: <b>${{w.depth_ft}} ft</b><br>` +
          `Distance: ${{w.distance_mi}} mi<br>` +
          (w.owner ? `${{w.owner}}<br>` : '') +
          (w.address ? `${{w.address}}<br>` : '') +
          `<a href="${{w.report_url}}" target="_blank" rel="noopener">Open TWDB well log &raquo;</a>`
        );
      bounds.push([w.lat, w.lon]);
    }});
    map.fitBounds(bounds, {{padding:[40,40]}});
  </script>
</body>
</html>
"""


def render(address, formatted_address, center_lat, center_lon, wells, rec):
    rec_ft = int(round(rec["recommended_ft"]))
    rec_meta = ""
    if rec["cluster_at_top"] > 1:
        rec_meta = f"({rec['cluster_at_top']} wells within 10 ft)"

    if rec["alternative_ft"] is not None:
        alt_block = (
            '<div class="stat">'
            '<div class="label">Alternative depth</div>'
            f'<div class="value">{int(round(rec["alternative_ft"]))} ft'
            '<small>next-deepest distinct</small></div>'
            '</div>'
        )
    else:
        alt_block = ""

    max_dist = max(d for d, _ in wells)
    rationale_bits = [
        f"Deepest of the 10 closest wells reaches <b>{rec_ft} ft</b>."
    ]
    if rec["cluster_at_top"] > 1:
        rationale_bits.append(
            f"{rec['cluster_at_top']} of the 10 are within 10 ft of that depth — high confidence."
        )
    if rec["alternative_ft"] is not None:
        rationale_bits.append(
            f"If you want a shallower option, the next distinct depth is "
            f"{int(round(rec['alternative_ft']))} ft."
        )
    rationale = " ".join(rationale_bits)

    rows = []
    wells_for_js = []
    for i, (dist, row) in enumerate(wells, start=1):
        tn = row["tracking_number"]
        depth = float(row["depth_ft"])
        is_rec = abs(depth - rec["recommended_ft"]) < 0.01
        report_url = TWDB_REPORT_URL.format(tn=urllib.parse.quote(tn))
        owner_addr = " &middot; ".join(
            html_lib.escape(x) for x in [row["owner"], row["address"]] if x
        ) or "&mdash;"
        rec_pill = '<span class="pill">recommended</span>' if is_rec else ""
        rows.append(
            "<tr{cls}><td>{i}</td><td>{depth} ft{pill}</td><td>{dist}</td>"
            "<td>{owner_addr}</td><td>{county}</td><td>{drill}</td>"
            "<td><a href='{url}' target='_blank' rel='noopener'>open log &raquo;</a></td></tr>".format(
                cls=" class='recommended'" if is_rec else "",
                i=i,
                depth=f"{depth:.0f}",
                pill=rec_pill,
                dist=f"{dist:.2f}",
                owner_addr=owner_addr,
                county=html_lib.escape(row["county"] or "—"),
                drill=html_lib.escape(row["drill_end"] or "—"),
                url=html_lib.escape(report_url, quote=True),
            )
        )
        wells_for_js.append({
            "tn": tn,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "depth_ft": f"{depth:.0f}",
            "distance_mi": f"{dist:.2f}",
            "owner": row["owner"],
            "address": row["address"],
            "report_url": report_url,
            "is_recommended": is_rec,
        })

    data_for_js = {
        "center": {
            "lat": center_lat,
            "lon": center_lon,
            "address": formatted_address,
        },
        "wells": wells_for_js,
    }

    return PAGE_TEMPLATE.format(
        address_html=html_lib.escape(formatted_address),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        rec_ft=rec_ft,
        rec_meta=(" " + rec_meta) if rec_meta else "",
        alt_block=alt_block,
        n_wells=len(wells),
        max_dist=f"{max_dist:.1f}",
        rationale=rationale,
        rows_html="\n        ".join(rows),
        data_json=json.dumps(data_for_js),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address", help="Street address to evaluate")
    ap.add_argument(
        "--out", help="Output HTML filename (default: derived from address)"
    )
    args = ap.parse_args()

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise SystemExit("Set GOOGLE_MAPS_API_KEY in your environment.")

    print(f"Geocoding: {args.address}", file=sys.stderr)
    lat, lon, formatted = geocode(args.address, api_key)
    print(f"  -> {formatted}  ({lat:.5f}, {lon:.5f})", file=sys.stderr)

    print("Finding nearest wells ...", file=sys.stderr)
    wells = nearest_wells(lat, lon, k=10)
    if not wells:
        raise SystemExit("No wells found within reasonable distance.")
    print(
        f"  -> {len(wells)} wells, depths "
        f"{min(float(r['depth_ft']) for _, r in wells):.0f}–"
        f"{max(float(r['depth_ft']) for _, r in wells):.0f} ft",
        file=sys.stderr,
    )

    rec = recommend_depth(wells)
    html = render(args.address, formatted, lat, lon, wells, rec)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_name = args.out or f"{datetime.now().strftime('%Y-%m-%d')}-{slugify(formatted)}.html"
    out_path = REPORTS_DIR / out_name
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(out_path)  # last stdout line = path, easy to capture


if __name__ == "__main__":
    main()
