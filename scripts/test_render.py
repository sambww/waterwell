#!/usr/bin/env python3
"""Quick end-to-end check that bypasses the Google Maps geocode call.

Usage: python3 test_render.py <lat> <lon> "<address label>"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_report import nearest_wells, recommend_depth, render, REPORTS_DIR, slugify  # noqa: E501
from datetime import datetime

lat = float(sys.argv[1])
lon = float(sys.argv[2])
label = sys.argv[3]

wells = nearest_wells(lat, lon, k=10)
rec = recommend_depth(wells)
html = render(label, label, lat, lon, wells, rec)

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
out = REPORTS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}-test-{slugify(label)}.html"
out.write_text(html, encoding="utf-8")
print(out)
for d, r in wells:
    print(f"  {d:5.2f} mi   {float(r['depth_ft']):4.0f} ft   {r['tracking_number']}  {r['city']}, {r['county']}")
