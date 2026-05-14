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
    "https://www3.twdb.texas.gov/apps/waterdatainteractive/"
    "GetReports.aspx?Num={tn}&Type=SDR-Well"
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


# ---- Brand constants -------------------------------------------------------
BRAND = {
    "name": "Ballard Water Well Company",
    "legal_name": "Ballard Water Well Company LLC",
    "tagline": "Your local water well experts &middot; Since 1979",
    "phone_display": "(832) 479-3557",
    "phone_tel": "8324793557",
    "email": "info@texaswaterwell.com",
    "website": "https://www.texaswaterwell.com/",
    "website_display": "texaswaterwell.com",
    "logo_filename": "logo.jpg",
    "license_blurb": "Licensed TDLR Master Driller &amp; Pump Installer",
    "location_blurb": (
        "Premier water well drilling, pump installation, and water treatment "
        "in Willis, TX and the Greater Houston area."
    ),
    "service_area_blurb": (
        "100-mile service radius from Willis, Texas &mdash; including "
        "Houston, Conroe, The Woodlands, Magnolia, Tomball, Spring, "
        "Cypress, Katy, and surrounding areas."
    ),
}

# Reusable brand CSS (used by both report and index pages).
BRAND_CSS = """
:root {
  --navy:#1c3f6e; --navy-2:#2b568a;
  --blue:#1e88e5;
  --green:#4a8a3a; --green-dark:#3a6f2d; --green-soft:#ecf5e6;
  --fg:#1c1c1e; --muted:#6b7280;
  --bg:#f4f6f9; --card:#fff;
  --border:#e4e7eb; --accent-soft:#e8f1fb;
}
* { box-sizing:border-box; }
html, body { margin:0; }
body {
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Helvetica,Arial,sans-serif;
  color:var(--fg); background:var(--bg);
}
a { color:var(--blue); text-decoration:none; }
a:hover { text-decoration:underline; }

.brandbar { background:#fff; border-bottom:1px solid var(--border); padding:14px 0; }
.brandbar .inner {
  max-width:1100px; margin:0 auto; padding:0 24px;
  display:flex; align-items:center; gap:16px; flex-wrap:wrap;
}
.brandbar img { height:58px; width:auto; display:block; }
.brandbar .company { display:flex; flex-direction:column; }
.brandbar .name { font-weight:700; font-size:17px; color:var(--navy); }
.brandbar .tag { color:var(--muted); font-size:13px; }
.brandbar .phone {
  margin-left:auto; color:var(--navy); font-weight:700; font-size:17px;
  text-decoration:none; white-space:nowrap;
}
.brandbar .phone:hover { color:var(--blue); text-decoration:none; }

footer.brand { background:#fff; border-top:1px solid var(--border); margin-top:40px; }
footer.brand .inner {
  max-width:1100px; margin:0 auto; padding:28px 24px;
  display:grid; grid-template-columns:2fr 1fr 1fr; gap:28px;
}
@media (max-width:780px) { footer.brand .inner { grid-template-columns:1fr; } }
footer.brand h3 {
  font-size:12px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--muted); margin:0 0 10px; font-weight:600;
}
footer.brand p { margin:0 0 4px; font-size:14px; color:#444; }
"""


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Water Well Depth Estimate &mdash; {address_html} | {brand_name}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    {brand_css}
    .hero {{
      background: linear-gradient(135deg, var(--navy) 0%, var(--navy-2) 100%);
      color:#fff; padding:36px 0 84px;
    }}
    .hero .inner {{ max-width:1100px; margin:0 auto; padding:0 24px; }}
    .hero .eyebrow {{ font-size:12px; text-transform:uppercase; letter-spacing:.08em; opacity:.7; margin-bottom:6px; }}
    .hero h1 {{ margin:0 0 8px; font-size:26px; font-weight:600; line-height:1.25; }}
    .hero .address {{ font-size:19px; opacity:.95; }}
    .hero .meta {{ font-size:13px; opacity:.7; margin-top:6px; }}

    .wrap {{ max-width:1100px; margin:-60px auto 0; padding:0 24px 8px; position:relative; }}

    .summary {{
      background:var(--card); border:1px solid var(--border); border-radius:14px;
      padding:18px; margin-bottom:24px; box-shadow:0 8px 24px rgba(28,63,110,.10);
      display:flex; flex-wrap:wrap; gap:14px;
    }}
    .stat {{ flex:1 1 220px; padding:14px 18px; border-radius:10px; background:#fafbfc; border:1px solid var(--border); }}
    .stat.primary {{ background:var(--green-soft); border-color:#cfe3c4; }}
    .stat.secondary {{ background:var(--accent-soft); border-color:#c8defa; }}
    .stat .label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.07em; font-weight:600; }}
    .stat .value {{ font-size:30px; font-weight:700; color:var(--fg); margin-top:4px; line-height:1.1; }}
    .stat.primary .value {{ color:var(--green-dark); }}
    .stat.secondary .value {{ color:var(--navy); }}
    .stat .value small {{ font-size:13px; font-weight:400; color:var(--muted); margin-left:6px; }}

    .rationale {{
      background:var(--card); border:1px solid var(--border); border-radius:12px;
      padding:18px 22px; margin-bottom:24px; color:#3a3a3a; line-height:1.6;
    }}
    .rationale b {{ color:var(--navy); }}

    #map {{
      height:520px; border:1px solid var(--border); border-radius:12px;
      margin-bottom:24px; box-shadow:0 2px 8px rgba(0,0,0,.04);
    }}

    .table-wrap {{
      background:var(--card); border:1px solid var(--border); border-radius:12px;
      overflow:hidden; margin-bottom:24px;
    }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ padding:12px 14px; text-align:left; font-size:14px; border-bottom:1px solid var(--border); }}
    th {{ background:#f9fafb; color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.06em; }}
    tr:last-child td {{ border-bottom:0; }}
    tr.recommended td {{ background:var(--green-soft); }}
    tr.recommended td:first-child {{ box-shadow:inset 3px 0 0 var(--green); }}
    .pill {{
      display:inline-block; padding:2px 8px; border-radius:999px;
      background:var(--green); color:#fff; font-size:10px; margin-left:6px;
      font-weight:700; text-transform:uppercase; letter-spacing:.04em;
    }}

    .cta {{
      background: linear-gradient(135deg, var(--green) 0%, var(--green-dark) 100%);
      color:#fff; padding:32px 28px; border-radius:14px;
      text-align:center; margin-bottom:8px;
    }}
    .cta h2 {{ margin:0 0 8px; font-size:22px; font-weight:600; }}
    .cta p {{ margin:0 0 18px; opacity:.95; max-width:560px; margin-left:auto; margin-right:auto; }}
    .cta-buttons {{ display:flex; flex-wrap:wrap; gap:12px; justify-content:center; }}
    .cta-btn {{
      background:#fff; color:var(--green-dark); padding:12px 22px;
      border-radius:8px; font-weight:600; text-decoration:none;
      display:inline-block; transition:transform .15s, box-shadow .15s;
    }}
    .cta-btn:hover {{ transform:translateY(-1px); box-shadow:0 4px 12px rgba(0,0,0,.15); text-decoration:none; }}
    .cta-btn.alt {{ background:rgba(255,255,255,.12); color:#fff; border:1px solid rgba(255,255,255,.35); }}

    .disclaimer {{
      max-width:1100px; margin:0 auto; padding:24px 24px 8px;
      color:var(--muted); font-size:12px; line-height:1.6;
    }}
  </style>
</head>
<body>
  <div class="brandbar">
    <div class="inner">
      <a href="{brand_website}" target="_blank" rel="noopener"><img src="{brand_logo}" alt="{brand_name}"></a>
      <div class="company">
        <span class="name">{brand_name}</span>
        <span class="tag">{brand_tagline}</span>
      </div>
      <a href="tel:{brand_phone_tel}" class="phone">{brand_phone_display}</a>
    </div>
  </div>

  <section class="hero">
    <div class="inner">
      <div class="eyebrow">Water well depth estimate</div>
      <h1>Based on the 10 nearest TWDB well logs</h1>
      <div class="address">{address_html}</div>
      <div class="meta">Prepared {generated_at} &middot; {n_wells} wells analyzed within {max_dist} miles</div>
    </div>
  </section>

  <div class="wrap">
    <section class="summary">
      <div class="stat primary">
        <div class="label">Recommended Depth</div>
        <div class="value">{rec_ft} ft<small>{rec_meta}</small></div>
      </div>
      {alt_block}
      <div class="stat">
        <div class="label">Depth Range Observed</div>
        <div class="value">{min_ft}&ndash;{max_ft} ft<small>across {n_wells} wells</small></div>
      </div>
    </section>

    <div class="rationale">{rationale}</div>

    <div id="map"></div>

    <div class="table-wrap">
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
    </div>

    <section class="cta">
      <h2>Ready for your full estimate?</h2>
      <p>The depth above is a starting point from public records. Let our team walk your property and put together a complete proposal.</p>
      <div class="cta-buttons">
        <a href="tel:{brand_phone_tel}" class="cta-btn">Call {brand_phone_display}</a>
        <a href="mailto:{brand_email}?subject=Estimate%20request%20for%20{address_url}" class="cta-btn alt">Email {brand_email}</a>
        <a href="{brand_website}" class="cta-btn alt" target="_blank" rel="noopener">Visit our website</a>
      </div>
    </section>
  </div>

  <div class="disclaimer">
    Source: Texas Water Development Board Submitted Driller's Reports
    (<a href="https://www.twdb.texas.gov/groundwater/data/drillersdb.asp" target="_blank" rel="noopener">TWDB SDR</a>).
    Recommended depth is the deepest of the 10 nearest water-supply wells in the public database and is provided as an estimate based on historical drilling records in the area. Actual depth required for your site depends on soil conditions, water table, and aquifer characteristics observed during drilling. A final estimate will be provided after site assessment by a licensed driller.
  </div>

  <footer class="brand">
    <div class="inner">
      <div>
        <h3>{brand_legal_name}</h3>
        <p>{brand_location_blurb}</p>
        <p style="margin-top:10px;">{brand_license_blurb}</p>
      </div>
      <div>
        <h3>Contact</h3>
        <p><a href="tel:{brand_phone_tel}">{brand_phone_display}</a></p>
        <p><a href="mailto:{brand_email}">{brand_email}</a></p>
        <p><a href="{brand_website}" target="_blank" rel="noopener">{brand_website_display}</a></p>
      </div>
      <div>
        <h3>Service Area</h3>
        <p>{brand_service_area_blurb}</p>
      </div>
    </div>
  </footer>

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
      html: '<div style="background:#1c3f6e;border:3px solid #fff;border-radius:50%;width:18px;height:18px;box-shadow:0 0 0 3px rgba(28,63,110,.35);"></div>',
      iconSize:[18,18], iconAnchor:[9,9]
    }});
    L.marker([data.center.lat, data.center.lon], {{icon: subjectIcon}})
      .addTo(map)
      .bindPopup('<b>Subject address</b><br>' + data.center.address);

    const bounds = [[data.center.lat, data.center.lon]];
    data.wells.forEach((w, i) => {{
      const color = w.is_recommended ? '#4a8a3a' : '#1e88e5';
      const icon = L.divIcon({{
        className: 'well-icon',
        html: `<div style="background:${{color}};color:#fff;border:2px solid #fff;border-radius:50%;width:26px;height:26px;line-height:22px;text-align:center;font-size:12px;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,.3);">${{i+1}}</div>`,
        iconSize:[26,26], iconAnchor:[13,13]
      }});
      L.marker([w.lat, w.lon], {{icon}})
        .addTo(map)
        .bindPopup(
          `<b>Well #${{i+1}}${{w.is_recommended ? ' &middot; recommended' : ''}}</b><br>` +
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
            '<div class="stat secondary">'
            '<div class="label">Alternative Depth</div>'
            f'<div class="value">{int(round(rec["alternative_ft"]))} ft'
            '<small>next-deepest distinct</small></div>'
            '</div>'
        )
    else:
        alt_block = ""

    max_dist = max(d for d, _ in wells)
    all_depths = [float(r["depth_ft"]) for _, r in wells]
    min_ft = int(round(min(all_depths)))
    max_ft = int(round(max(all_depths)))
    rationale_bits = [
        f"The deepest of the 10 nearest wells reaches <b>{rec_ft} ft</b>."
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
        brand_css=BRAND_CSS,
        brand_name=BRAND["name"],
        brand_legal_name=BRAND["legal_name"],
        brand_tagline=BRAND["tagline"],
        brand_phone_display=BRAND["phone_display"],
        brand_phone_tel=BRAND["phone_tel"],
        brand_email=BRAND["email"],
        brand_website=BRAND["website"],
        brand_website_display=BRAND["website_display"],
        brand_logo=BRAND["logo_filename"],
        brand_license_blurb=BRAND["license_blurb"],
        brand_location_blurb=BRAND["location_blurb"],
        brand_service_area_blurb=BRAND["service_area_blurb"],
        address_html=html_lib.escape(formatted_address),
        address_url=urllib.parse.quote(formatted_address),
        generated_at=datetime.now().strftime("%B %-d, %Y"),
        rec_ft=rec_ft,
        rec_meta=(" " + rec_meta) if rec_meta else "",
        alt_block=alt_block,
        n_wells=len(wells),
        max_dist=f"{max_dist:.1f}",
        min_ft=min_ft,
        max_ft=max_ft,
        rationale=rationale,
        rows_html="\n          ".join(rows),
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
