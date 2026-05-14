#!/usr/bin/env python3
"""
One-time preprocessing: collapse the TWDB SDR dump into a single compact CSV
that the report generator can scan quickly.

Output: data/wells.csv with columns:
  tracking_number, lat, lon, depth_ft, proposed_use,
  owner, address, city, county, drill_end
"""

import csv
import os
import sys
from pathlib import Path

SDR_DIR = Path("/Users/samuelballard/Downloads/SDRDownload/SDRDownload")
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "wells.csv"

# Texas bounding box (generous) — drop wells with obviously bogus coordinates.
TX_LAT_MIN, TX_LAT_MAX = 25.0, 37.0
TX_LON_MIN, TX_LON_MAX = -107.0, -93.0

csv.field_size_limit(sys.maxsize)


def parse_float(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_depths():
    """Max BottomDepth per tracking number."""
    path = SDR_DIR / "WellBoreHole.txt"
    depths = {}
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            tn = (row.get("WellReportTrackingNumber") or "").strip()
            if not tn:
                continue
            d = parse_float(row.get("BottomDepth"))
            if d is None or d <= 0:
                continue
            if d > depths.get(tn, 0):
                depths[tn] = d
    return depths


def main():
    print(f"Reading depths from {SDR_DIR / 'WellBoreHole.txt'} ...", flush=True)
    depths = load_depths()
    print(f"  {len(depths):,} wells with a recorded depth", flush=True)

    src = SDR_DIR / "WellData.txt"
    print(f"Streaming wells from {src} ...", flush=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    skipped_coords = 0
    skipped_no_depth = 0

    with src.open("r", encoding="utf-8", errors="replace", newline="") as fin, \
         OUT_PATH.open("w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin, delimiter="|")
        writer = csv.writer(fout)
        writer.writerow([
            "tracking_number", "lat", "lon", "depth_ft", "proposed_use",
            "owner", "address", "city", "county", "drill_end",
        ])
        for row in reader:
            tn = (row.get("WellReportTrackingNumber") or "").strip()
            if not tn:
                continue
            lat = parse_float(row.get("CoordDDLat"))
            lon = parse_float(row.get("CoordDDLong"))
            if lat is None or lon is None:
                skipped_coords += 1
                continue
            if not (TX_LAT_MIN <= lat <= TX_LAT_MAX and TX_LON_MIN <= lon <= TX_LON_MAX):
                skipped_coords += 1
                continue
            depth = depths.get(tn)
            if depth is None:
                skipped_no_depth += 1
                continue
            writer.writerow([
                tn,
                f"{lat:.6f}",
                f"{lon:.6f}",
                f"{depth:.1f}",
                (row.get("ProposedUse") or "").strip(),
                (row.get("OwnerName") or "").strip(),
                (row.get("WellAddress1") or "").strip(),
                (row.get("WellCity") or "").strip(),
                (row.get("County") or "").strip(),
                (row.get("DrillingEndDate") or "").strip(),
            ])
            kept += 1

    print(f"Wrote {kept:,} wells to {OUT_PATH}")
    print(f"  skipped (bad/missing coords): {skipped_coords:,}")
    print(f"  skipped (no depth):           {skipped_no_depth:,}")


if __name__ == "__main__":
    main()
