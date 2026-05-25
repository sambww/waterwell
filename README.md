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

## Job Queue Dashboard

Public, customer-facing board showing the drilling queue per rig — auto-synced
from Workiz every 15 minutes.

- **Live URL:** <https://sambww.github.io/waterwell/queue.html>
- **Page:** `docs/queue.html` (static; fetches its data at load time)
- **Config:** `docs/data/rigs.json` — hand-edit to add/remove a rig or
  reassign a supervisor. The `workizMatch` array lists the strings the sync
  looks for in each Workiz job's Team / Assigned / Tags fields to route it
  to that rig.
- **Data:** `docs/data/queue.json` — overwritten by the sync; do not edit
  by hand.
- **Sync script:** `scripts/sync_workiz.py`
- **Cron:** `.github/workflows/sync-workiz.yml` (every 15 minutes, plus a
  manual `workflow_dispatch` trigger)

### One-time Workiz setup

1. In Workiz: Settings → Integrations → API → copy the API token.
2. In GitHub: Settings → Secrets and variables → Actions → add a secret
   named `WORKIZ_API_TOKEN` with that value.
3. Run the workflow once manually (Actions → "Sync Workiz job queue" → Run
   workflow) to confirm `docs/data/queue.json` gets updated and pushed.

### Manual sync from your laptop

```sh
WORKIZ_API_TOKEN=your_token_here python3 scripts/sync_workiz.py
```

This rewrites `docs/data/queue.json` in place. Commit + push to publish.

### Adding or removing a rig

Edit `docs/data/rigs.json`. To add a rig:

```json
{ "name": "NewRig", "supervisors": ["Newperson"], "workizMatch": ["Newperson", "NewRig"] }
```

To put a supervisor on the bench (no rig assigned today), add their name to
the `bench` array. The dashboard re-renders automatically on the next page
load — no code changes, no redeploy.

## Refreshing the well database

If TWDB releases a new SDR download, replace the folder at
`/Users/samuelballard/Downloads/SDRDownload/SDRDownload/`, then rerun:

```sh
python3 scripts/preprocess.py
```
