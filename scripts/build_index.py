#!/usr/bin/env python3
"""
Build geo-bucketed JSON tiles of well data for the browser-side search.

Each tile covers a 0.25° × 0.25° square (~17 miles) and contains the wells in
that area. The browser fetches the few tiles surrounding a search location.

Output:
  docs/data/_index.json        (list of populated tiles + metadata)
  docs/data/<tlat>_<tlon>.json (one file per non-empty tile)

Compact per-well array format (small JSON, fast to parse):
  [tracking_number, lat, lon, depth_ft, county, owner, address, drill_year]
"""

import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WELLS_CSV = ROOT / "data" / "wells.csv"
OUT_DIR = ROOT / "docs" / "data"

TILE_SIZE = 0.25  # degrees; ~17 mi at Texas latitudes

WATER_USES = {
    "Domestic", "Irrigation", "Stock", "Public Supply",
    "Industrial", "Rig Supply", "Fracking Supply",
}


def tile_id(lat, lon):
    return f"{math.floor(lat / TILE_SIZE)}_{math.floor(lon / TILE_SIZE)}"


def main():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    tiles = defaultdict(list)

    with WELLS_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("proposed_use") or "").strip() not in WATER_USES:
                continue
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
                depth = float(row["depth_ft"])
            except (ValueError, KeyError):
                continue
            tid = tile_id(lat, lon)
            tiles[tid].append([
                row["tracking_number"],
                round(lat, 6),
                round(lon, 6),
                round(depth, 1),
                row.get("county", ""),
                row.get("owner", ""),
                row.get("address", ""),
                (row.get("drill_end") or "")[:4],
            ])

    total_wells = 0
    max_tile = ("", 0)
    for tid, wells in tiles.items():
        (OUT_DIR / f"{tid}.json").write_text(
            json.dumps(wells, separators=(",", ":")), encoding="utf-8"
        )
        total_wells += len(wells)
        if len(wells) > max_tile[1]:
            max_tile = (tid, len(wells))

    index = {
        "tile_size": TILE_SIZE,
        "tiles": sorted(tiles.keys()),
        "total_wells": total_wells,
        "tile_count": len(tiles),
    }
    (OUT_DIR / "_index.json").write_text(
        json.dumps(index, separators=(",", ":")), encoding="utf-8"
    )

    print(f"Wrote {len(tiles)} tiles, {total_wells:,} water-supply wells")
    print(f"  largest tile: {max_tile[0]} with {max_tile[1]:,} wells")
    out_size = sum(p.stat().st_size for p in OUT_DIR.iterdir())
    print(f"  total on disk: {out_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
