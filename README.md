# well-reports

Generates a public URL with a map + list of the 10 nearest TWDB water wells
for any Texas address, with a recommended well depth.

## One-time setup

### 1. Google Maps geocoding API key

Get a key from <https://console.cloud.google.com/google/maps-apis/credentials>
(enable the "Geocoding API"), then add it to your shell profile so the script
can find it:

```sh
echo 'export GOOGLE_MAPS_API_KEY="YOUR_KEY_HERE"' >> ~/.zshrc
source ~/.zshrc
```

### 2. GitHub Pages

Repo: <https://github.com/sambww/waterwell>

1. In the GitHub repo go to **Settings → Pages**. Set:
   - Source: **Deploy from a branch**
   - Branch: **main** / folder: **/docs**
   - Save.
2. Wait ~1 minute. Your reports will live at
   `https://sambww.github.io/waterwell/<filename>.html`.

## Daily use

```sh
cd /Users/samuelballard/well-reports
python3 scripts/generate_report.py "1234 County Rd 100, Liberty Hill, TX"
./scripts/publish.sh        # commits + pushes the new report, prints the URL
```

Paste the printed URL into your email reply.

## What the script does

1. Geocodes the address via Google Maps.
2. Scans the preprocessed `data/wells.csv` for the 10 nearest **water-supply**
   wells (Domestic, Irrigation, Stock, Public Supply, Industrial, Rig Supply,
   Fracking Supply — environmental borings and monitor wells are filtered out).
3. Picks the deepest as the recommended depth; suggests an alternative if there
   is a meaningfully shallower second tier.
4. Writes a self-contained HTML page in `docs/` with a Leaflet map and a list,
   each with a link to the TWDB well log.

## Refreshing the well database

If TWDB releases a new SDR download, replace the folder at
`/Users/samuelballard/Downloads/SDRDownload/SDRDownload/`, then rerun:

```sh
python3 scripts/preprocess.py
```
