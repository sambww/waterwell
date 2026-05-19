#!/usr/bin/env python3
"""Generate docs/index.html — the customer-facing search page.

Visitors type any Texas address; the page geocodes via the Google Maps JS API,
fetches the relevant pre-built well-data tiles from docs/data/, finds the 10
nearest water-supply wells, and renders a branded report inline. The URL
updates with query params so the report is shareable.

Run once after `build_index.py`. No CLI flags."""

from pathlib import Path
from generate_report import BRAND, BRAND_CSS, REPORTS_DIR, TWDB_REPORT_URL


GOOGLE_MAPS_PUBLIC_KEY = "AIzaSyDqiqCo6Qn-KPc8imgDqaWeRbVnlG_GKK4"


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{brand_name} &mdash; Water Well Depth Lookup</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    {brand_css}

    .hero {{
      background: linear-gradient(135deg, var(--navy) 0%, var(--navy-2) 100%);
      color:#fff; padding:64px 24px 88px; text-align:center;
    }}
    .hero h1 {{ margin:0 0 12px; font-size:34px; font-weight:600; line-height:1.2; }}
    .hero p.lead {{ margin:0 auto 30px; max-width:640px; font-size:17px; opacity:.92; line-height:1.55; }}

    .search-card {{
      max-width:680px; margin:0 auto; background:#fff; border-radius:14px;
      padding:22px 22px 18px; box-shadow:0 14px 40px rgba(0,0,0,.25); text-align:left;
    }}
    .search-card label {{
      display:block; font-size:12px; text-transform:uppercase; letter-spacing:.06em;
      color:var(--muted); font-weight:600; margin-bottom:8px;
    }}
    .search-row {{ display:flex; gap:10px; align-items:stretch; }}
    .address-wrap {{ flex:1; min-width:0; display:flex; position:relative; }}
    .search-row input {{
      flex:1; padding:14px 16px; font-size:16px; border:1px solid var(--border);
      border-radius:8px; color:var(--fg); background:#fff; min-width:0; width:100%;
    }}
    .search-row input:focus {{ outline:none; border-color:var(--blue); box-shadow:0 0 0 3px rgba(30,136,229,.15); }}
    /* Google Places Autocomplete web component */
    gmp-place-autocomplete {{
      flex:1; width:100%;
      --gmp-mat-color-primary:#1e88e5;
      --gmp-mat-color-on-surface:#1c1c1e;
    }}
    .search-row button {{
      padding:14px 22px; font-size:15px; font-weight:600; color:#fff;
      background:var(--green); border:0; border-radius:8px; cursor:pointer;
      transition:background .15s;
    }}
    .search-row button:hover {{ background:var(--green-dark); }}
    .search-row button:disabled {{ background:#9aa0a6; cursor:wait; }}
    .search-hint {{ margin:10px 0 0; font-size:12px; color:var(--muted); }}
    .search-error {{ margin:10px 0 0; font-size:13px; color:#b3261e; display:none; }}

    /* Report container */
    .report {{ display:none; }}
    .report.visible {{ display:block; }}

    .report-meta {{ background:#fff; padding:18px 24px 0; }}
    .report-meta .eyebrow {{
      font-size:11px; text-transform:uppercase; letter-spacing:.08em;
      color:var(--muted); font-weight:600;
    }}
    .report-meta h2 {{ margin:6px 0 0; font-size:22px; color:var(--navy); }}
    .report-meta .meta {{ font-size:13px; color:var(--muted); margin-top:4px; }}

    .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}

    .summary {{
      background:var(--card); border:1px solid var(--border); border-radius:14px;
      padding:18px; margin-bottom:24px; box-shadow:0 4px 16px rgba(28,63,110,.08);
      display:flex; flex-wrap:wrap; gap:14px;
    }}
    .stat {{ flex:1 1 220px; padding:14px 18px; border-radius:10px; background:#fafbfc; border:1px solid var(--border); }}
    .stat.primary {{ background:var(--green-soft); border-color:#cfe3c4; }}
    .stat.secondary {{ background:var(--accent-soft); border-color:#c8defa; }}
    .stat .label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.07em; font-weight:600; }}
    .stat .value {{ font-size:30px; font-weight:700; margin-top:4px; line-height:1.1; }}
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

    .table-wrap {{ background:var(--card); border:1px solid var(--border); border-radius:12px; overflow:hidden; margin-bottom:24px; }}
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
      color:#fff; padding:32px 28px; border-radius:14px; text-align:center;
    }}
    .cta h3 {{ margin:0 0 8px; font-size:22px; font-weight:600; }}
    .cta p {{ margin:0 0 18px; opacity:.95; max-width:560px; margin-left:auto; margin-right:auto; }}
    .cta-buttons {{ display:flex; flex-wrap:wrap; gap:12px; justify-content:center; }}
    .cta-btn {{
      background:#fff; color:var(--green-dark); padding:12px 22px;
      border-radius:8px; font-weight:600; text-decoration:none; display:inline-block;
      transition:transform .15s, box-shadow .15s;
    }}
    .cta-btn:hover {{ transform:translateY(-1px); box-shadow:0 4px 12px rgba(0,0,0,.15); text-decoration:none; }}
    .cta-btn.alt {{ background:rgba(255,255,255,.12); color:#fff; border:1px solid rgba(255,255,255,.35); }}

    .disclaimer {{
      max-width:1100px; margin:0 auto; padding:24px 24px 8px;
      color:var(--muted); font-size:12px; line-height:1.6;
    }}

    .loader {{ text-align:center; padding:40px 24px; color:var(--muted); }}
    .loader .spinner {{
      display:inline-block; width:36px; height:36px; border:3px solid #eef0f3;
      border-top-color:var(--navy); border-radius:50%; animation:spin .8s linear infinite;
      margin-bottom:12px;
    }}
    @keyframes spin {{ to {{ transform:rotate(360deg); }} }}

    /* How-it-works (only shown before search) */
    .howit {{ max-width:980px; margin:0 auto; padding:48px 24px; }}
    .howit h3.section {{ font-size:22px; color:var(--navy); margin:0 0 18px; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr)); gap:20px; }}
    .card {{ background:#fff; border:1px solid var(--border); border-radius:12px; padding:24px; }}
    .card h4 {{ margin:0 0 8px; color:var(--navy); font-size:17px; }}
    .card p {{ margin:0; color:#444; line-height:1.55; }}
    .badge {{
      display:inline-block; width:38px; height:38px; line-height:38px;
      text-align:center; background:var(--green-soft); color:var(--green-dark);
      border-radius:50%; font-weight:700; margin-bottom:12px;
    }}
  </style>
</head>
<body>
  <div class="brandbar">
    <div class="inner">
      <a href="{brand_website}" target="_blank" rel="noopener"><img src="logo.jpg" alt="{brand_name}"></a>
      <div class="company">
        <span class="name">{brand_name}</span>
        <span class="tag">{brand_tagline}</span>
      </div>
      <a href="tel:{brand_phone_tel}" class="phone">{brand_phone_display}</a>
    </div>
  </div>

  <section class="hero">
    <h1>How deep do I need to drill?</h1>
    <p class="lead">Enter your address to see the depth of the 10 nearest water wells in the Texas Water Development Board database &mdash; with a recommended target depth based on real local drilling history.</p>
    <form class="search-card" id="search-form" autocomplete="off">
      <label for="address">Your property address</label>
      <div class="search-row">
        <div class="address-wrap" id="address-wrap">
          <input id="address" name="address" type="text" placeholder="123 County Road, Magnolia, TX" required>
        </div>
        <button id="submit-btn" type="submit">Look up depth</button>
      </div>
      <p class="search-hint">Works for any Texas address. Your data is not stored.</p>
      <p class="search-error" id="search-error"></p>
    </form>
  </section>

  <!-- Loader -->
  <div class="loader" id="loader" style="display:none;">
    <div class="spinner"></div>
    <div>Finding the closest water wells&hellip;</div>
  </div>

  <!-- The report renders here -->
  <div class="report" id="report">
    <div class="report-meta">
      <div class="wrap" style="padding-top:24px; padding-bottom:0;">
        <div class="eyebrow">Water well depth estimate</div>
        <h2 id="r-address"></h2>
        <div class="meta" id="r-meta"></div>
      </div>
    </div>

    <div class="wrap">
      <section class="summary" id="r-summary"></section>
      <div class="rationale" id="r-rationale"></div>
      <div id="map"></div>
      <div class="table-wrap"><table>
        <thead><tr><th>#</th><th>Depth (ft)</th><th>Distance (mi)</th><th>Owner / Address</th><th>County</th><th>Drilled</th><th>Well Log</th></tr></thead>
        <tbody id="r-rows"></tbody>
      </table></div>

      <section class="cta">
        <h3>Ready for your full estimate?</h3>
        <p>The depth above is a starting point from public records. Let our team walk your property and put together a complete proposal.</p>
        <div class="cta-buttons">
          <a href="tel:{brand_phone_tel}" class="cta-btn">Call {brand_phone_display}</a>
          <a id="r-mailto" href="mailto:{brand_email}" class="cta-btn alt">Email {brand_email}</a>
          <a href="{brand_website}" class="cta-btn alt" target="_blank" rel="noopener">Visit our website</a>
        </div>
      </section>
    </div>

    <div class="disclaimer">
      Source: Texas Water Development Board Submitted Driller's Reports
      (<a href="https://www.twdb.texas.gov/groundwater/data/drillersdb.asp" target="_blank" rel="noopener">TWDB SDR</a>).
      Recommended depth is the deepest of the 10 nearest water-supply wells in the public database and is provided as an estimate based on historical drilling records in the area. Actual depth required for your site depends on soil conditions, water table, and aquifer characteristics observed during drilling. A final estimate will be provided after site assessment by a licensed driller.
    </div>
  </div>

  <!-- How-it-works (visible only when no search has been run yet) -->
  <div class="howit" id="howit">
    <h3 class="section">How this works</h3>
    <div class="cards">
      <div class="card">
        <div class="badge">1</div><h4>You enter your address</h4>
        <p>We locate your property and pull the ten closest registered water wells from the Texas Water Development Board database &mdash; over 700,000 wells statewide.</p>
      </div>
      <div class="card">
        <div class="badge">2</div><h4>We map and rank them</h4>
        <p>Each well is plotted on a live map with depth, distance, and a link to the official state log so you can verify the numbers yourself.</p>
      </div>
      <div class="card">
        <div class="badge">3</div><h4>You see a target depth</h4>
        <p>We recommend a target depth based on the deepest, most reliable nearby wells. Bookmark or share the result &mdash; the link works for anyone.</p>
      </div>
    </div>
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
    // ----------- Config / state -----------------------------------------------
    const TILE_SIZE = 0.25;
    const TWDB_URL = (tn) => `{twdb_url_template}`.replace('{{tn}}', encodeURIComponent(tn));

    const form = document.getElementById('search-form');
    let addressInput = document.getElementById('address');     // may be swapped for the autocomplete element
    const addressWrap = document.getElementById('address-wrap');
    let pickedPlace = null;                                    // {{lat, lon, label}} when picked via autocomplete
    const submitBtn = document.getElementById('submit-btn');
    const errorEl = document.getElementById('search-error');
    const loader = document.getElementById('loader');
    const reportEl = document.getElementById('report');
    const howit = document.getElementById('howit');

    let geocoder = null;        // set when Google Maps JS loads
    let map = null;             // Leaflet map instance (reused)
    let pendingSearch = null;   // queued search if Maps isn't ready yet

    // ----------- Google Maps loader ------------------------------------------
    window.initMaps = async function() {{
      geocoder = new google.maps.Geocoder();
      await setupAutocomplete();
      if (pendingSearch) {{
        const q = pendingSearch; pendingSearch = null;
        runSearch(q);
      }}
    }};

    async function setupAutocomplete() {{
      try {{
        const {{ PlaceAutocompleteElement }} = await google.maps.importLibrary('places');
        const ac = new PlaceAutocompleteElement({{
          includedRegionCodes: ['us'],
          includedPrimaryTypes: ['street_address', 'premise', 'subpremise'],
        }});
        ac.id = 'address';
        // Carry over any text the user already typed.
        const previousValue = addressInput.value || '';
        addressWrap.innerHTML = '';
        addressWrap.appendChild(ac);
        addressInput = ac;
        if (previousValue) {{
          // The web component exposes a `value` setter on the inner input.
          requestAnimationFrame(() => {{ try {{ ac.value = previousValue; }} catch (e) {{}} }});
        }}

        ac.addEventListener('gmp-select', async (event) => {{
          // The event can fire multiple times around a single selection;
          // ignore anything without a usable prediction.
          const prediction = event && event.placePrediction;
          if (!prediction) return;
          try {{
            const place = prediction.toPlace();
            await place.fetchFields({{ fields: ['displayName', 'formattedAddress', 'location'] }});
            const loc = place.location;
            if (!loc) return;
            pickedPlace = {{
              lat: typeof loc.lat === 'function' ? loc.lat() : loc.lat,
              lon: typeof loc.lng === 'function' ? loc.lng() : loc.lng,
              label: place.formattedAddress || place.displayName || '',
            }};
            runSearchWithCoords(pickedPlace.label, pickedPlace.lat, pickedPlace.lon);
          }} catch (err) {{
            // Silent — the Look-up-depth button still works as a fallback.
            console.warn('Place selection follow-up failed:', err);
          }}
        }});
      }} catch (e) {{
        console.warn('Place Autocomplete unavailable — falling back to plain input.', e);
      }}
    }}

    // ----------- Geo helpers --------------------------------------------------
    function tileId(lat, lon) {{
      return `${{Math.floor(lat / TILE_SIZE)}}_${{Math.floor(lon / TILE_SIZE)}}`;
    }}
    function nearbyTiles(lat, lon) {{
      const tlat = Math.floor(lat / TILE_SIZE);
      const tlon = Math.floor(lon / TILE_SIZE);
      const out = [];
      for (let dy = -1; dy <= 1; dy++)
        for (let dx = -1; dx <= 1; dx++)
          out.push(`${{tlat + dy}}_${{tlon + dx}}`);
      return out;
    }}
    function haversineMi(lat1, lon1, lat2, lon2) {{
      const R = 3958.7613;
      const p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
      const dp = (lat2 - lat1) * Math.PI / 180;
      const dl = (lon2 - lon1) * Math.PI / 180;
      const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
      return 2 * R * Math.asin(Math.sqrt(a));
    }}

    // ----------- Tile fetcher (with cache) -----------------------------------
    const tileCache = new Map();
    async function fetchTile(id) {{
      if (tileCache.has(id)) return tileCache.get(id);
      try {{
        const resp = await fetch(`data/${{id}}.json`);
        if (!resp.ok) {{ tileCache.set(id, []); return []; }}
        const data = await resp.json();
        tileCache.set(id, data);
        return data;
      }} catch (e) {{ tileCache.set(id, []); return []; }}
    }}

    async function nearestWells(lat, lon, k) {{
      // Try 3x3, then expand if we don't have enough wells.
      let radius = 1;
      while (radius <= 4) {{
        const tlat = Math.floor(lat / TILE_SIZE), tlon = Math.floor(lon / TILE_SIZE);
        const ids = [];
        for (let dy = -radius; dy <= radius; dy++)
          for (let dx = -radius; dx <= radius; dx++)
            ids.push(`${{tlat + dy}}_${{tlon + dx}}`);
        const tiles = await Promise.all(ids.map(fetchTile));
        const all = tiles.flat();
        if (all.length >= k * 3 || radius === 4) {{
          const ranked = all.map(w => {{
            const d = haversineMi(lat, lon, w[1], w[2]);
            return {{ d, w }};
          }}).sort((a, b) => a.d - b.d).slice(0, k);
          return ranked;
        }}
        radius++;
      }}
      return [];
    }}

    // ----------- Recommendation logic ----------------------------------------
    // Find clusters of 3+ wells where all members fall within a 50-ft band.
    // For each cluster, the recommended drill depth is the deepest well in
    // that cluster. Returns clusters sorted deepest-first.
    function recommend(wells) {{
      const depths = wells.map(x => x.w[3]).slice().sort((a, b) => a - b);
      const clusters = [];
      let i = 0;
      while (i < depths.length) {{
        let end = i;
        while (end + 1 < depths.length && depths[end + 1] - depths[i] <= 50) end++;
        const count = end - i + 1;
        if (count >= 3) {{
          clusters.push({{ min: depths[i], max: depths[end], count }});
          i = end + 1;
        }} else {{
          i++;
        }}
      }}
      clusters.sort((a, b) => b.max - a.max);

      if (clusters.length === 0) {{
        const deepest = depths[depths.length - 1];
        return {{
          mode: 'deepest',
          primary: {{ depth: deepest, count: 1, min: deepest, max: deepest }},
          alternatives: [],
        }};
      }}
      return {{
        mode: 'cluster',
        primary: {{ depth: clusters[0].max, count: clusters[0].count, min: clusters[0].min, max: clusters[0].max }},
        alternatives: clusters.slice(1).map(c => ({{ depth: c.max, count: c.count, min: c.min, max: c.max }})),
      }};
    }}

    // ----------- Render -------------------------------------------------------
    function renderReport(lat, lon, placeLabel, wells, rec) {{
      // Hide how-it-works, show report
      howit.style.display = 'none';
      reportEl.classList.add('visible');

      const minDepth = Math.min(...wells.map(x => x.w[3]));
      const maxDepth = Math.max(...wells.map(x => x.w[3]));
      const maxDist = Math.max(...wells.map(x => x.d));

      // Headers
      document.getElementById('r-address').textContent = placeLabel;
      document.getElementById('r-meta').textContent =
        `Based on ${{wells.length}} wells within ${{maxDist.toFixed(1)}} miles · prepared ${{new Date().toLocaleDateString('en-US', {{year:'numeric', month:'long', day:'numeric'}})}}`;

      // Mailto with prefilled subject
      document.getElementById('r-mailto').href =
        `mailto:{brand_email}?subject=${{encodeURIComponent('Estimate request for ' + placeLabel)}}`;

      // Summary cards: primary recommendation + each alternative cluster + range
      const fmtBand = (c) => `${{c.count}} well${{c.count !== 1 ? 's' : ''}} in ${{Math.round(c.min)}}–${{Math.round(c.max)}} ft`;
      const primaryLabel = rec.mode === 'cluster' ? 'Recommended Depth' : 'Recommended Depth';
      const primarySub = rec.mode === 'cluster' ? fmtBand(rec.primary) : 'deepest of 10 (no cluster of 3+)';
      let summary = `<div class="stat primary"><div class="label">${{primaryLabel}}</div><div class="value">${{Math.round(rec.primary.depth)}} ft<small>${{primarySub}}</small></div></div>`;
      rec.alternatives.forEach((alt, idx) => {{
        const lbl = rec.alternatives.length > 1 ? `Alternative #${{idx + 1}}` : 'Alternative Depth';
        summary += `<div class="stat secondary"><div class="label">${{lbl}}</div><div class="value">${{Math.round(alt.depth)}} ft<small>${{fmtBand(alt)}}</small></div></div>`;
      }});
      summary += `<div class="stat"><div class="label">Depth Range Observed</div><div class="value">${{Math.round(minDepth)}}–${{Math.round(maxDepth)}} ft<small>across ${{wells.length}} wells</small></div></div>`;
      document.getElementById('r-summary').innerHTML = summary;

      // Rationale
      let rationaleBits;
      if (rec.mode === 'cluster') {{
        rationaleBits = [
          `The strongest cluster of nearby wells: <b>${{rec.primary.count}} wells drilled between ${{Math.round(rec.primary.min)}} and ${{Math.round(rec.primary.max)}} ft</b> — recommended depth <b>${{Math.round(rec.primary.depth)}} ft</b>.`
        ];
        if (rec.alternatives.length > 0) {{
          const parts = rec.alternatives.map(a => `${{a.count}} wells at ${{Math.round(a.min)}}–${{Math.round(a.max)}} ft (alt. ${{Math.round(a.depth)}} ft)`);
          rationaleBits.push(`Other clusters: ${{parts.join('; ')}}.`);
        }}
      }} else {{
        rationaleBits = [
          `The 10 nearest wells are too scattered to form a depth cluster (no 3+ wells within 50 ft of each other). Recommending the deepest at <b>${{Math.round(rec.primary.depth)}} ft</b>.`
        ];
      }}
      document.getElementById('r-rationale').innerHTML = rationaleBits.join(' ');

      // Table rows — highlight wells that fall inside the primary cluster.
      const pMin = rec.primary.min, pMax = rec.primary.max;
      const rows = wells.map((x, i) => {{
        const w = x.w;
        const inCluster = w[3] >= pMin && w[3] <= pMax;
        const isExactRec = Math.abs(w[3] - rec.primary.depth) < 0.01;
        const ownerAddr = [w[5], w[6]].filter(Boolean).map(escapeHtml).join(' · ') || '—';
        const url = TWDB_URL(w[0]);
        const pill = isExactRec ? ' <span class="pill">recommended</span>' : '';
        return `<tr${{inCluster ? ' class="recommended"' : ''}}>
          <td>${{i + 1}}</td>
          <td>${{Math.round(w[3])}} ft${{pill}}</td>
          <td>${{x.d.toFixed(2)}}</td>
          <td>${{ownerAddr}}</td>
          <td>${{escapeHtml(w[4] || '—')}}</td>
          <td>${{escapeHtml(w[7] || '—')}}</td>
          <td><a href="${{url}}" target="_blank" rel="noopener">open log »</a></td>
        </tr>`;
      }}).join('');
      document.getElementById('r-rows').innerHTML = rows;

      // Map (rebuild if exists)
      if (map) {{ map.remove(); map = null; }}
      map = L.map('map').setView([lat, lon], 11);
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; OpenStreetMap', maxZoom: 19,
      }}).addTo(map);

      const subjectIcon = L.divIcon({{
        className: 'subject-icon',
        html: '<div style="background:#1c3f6e;border:3px solid #fff;border-radius:50%;width:18px;height:18px;box-shadow:0 0 0 3px rgba(28,63,110,.35);"></div>',
        iconSize:[18,18], iconAnchor:[9,9]
      }});
      L.marker([lat, lon], {{icon: subjectIcon}}).addTo(map).bindPopup('<b>Subject address</b><br>' + escapeHtml(placeLabel));

      const bounds = [[lat, lon]];
      wells.forEach((x, i) => {{
        const w = x.w;
        const inCluster = w[3] >= pMin && w[3] <= pMax;
        const color = inCluster ? '#4a8a3a' : '#1e88e5';
        const icon = L.divIcon({{
          className: 'well-icon',
          html: `<div style="background:${{color}};color:#fff;border:2px solid #fff;border-radius:50%;width:26px;height:26px;line-height:22px;text-align:center;font-size:12px;font-weight:700;box-shadow:0 2px 6px rgba(0,0,0,.3);">${{i + 1}}</div>`,
          iconSize:[26,26], iconAnchor:[13,13]
        }});
        L.marker([w[1], w[2]], {{icon}}).addTo(map).bindPopup(
          `<b>Well #${{i + 1}}${{inCluster ? ' · in recommended cluster' : ''}}</b><br>` +
          `Depth: <b>${{Math.round(w[3])}} ft</b><br>` +
          `Distance: ${{x.d.toFixed(2)}} mi<br>` +
          (w[5] ? `${{escapeHtml(w[5])}}<br>` : '') +
          (w[6] ? `${{escapeHtml(w[6])}}<br>` : '') +
          `<a href="${{TWDB_URL(w[0])}}" target="_blank" rel="noopener">Open TWDB well log »</a>`
        );
        bounds.push([w[1], w[2]]);
      }});
      map.fitBounds(bounds, {{padding:[40,40]}});

      // Scroll to the report
      reportEl.scrollIntoView({{behavior:'smooth', block:'start'}});
    }}

    function escapeHtml(s) {{
      return (s || '').replace(/[&<>"']/g, c => ({{
        '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
      }}[c]));
    }}

    // ----------- Search orchestration ----------------------------------------
    function showError(msg) {{
      errorEl.textContent = msg;
      errorEl.style.display = 'block';
    }}
    function clearError() {{ errorEl.style.display = 'none'; }}
    function setBusy(busy) {{
      submitBtn.disabled = busy;
      submitBtn.textContent = busy ? 'Looking up…' : 'Look up depth';
      loader.style.display = busy ? 'block' : 'none';
    }}

    async function runSearch(address) {{
      clearError();
      setBusy(true);
      try {{
        if (!geocoder) {{ pendingSearch = address; return; }}
        const {{lat, lon, place}} = await new Promise((resolve, reject) => {{
          geocoder.geocode({{ address }}, (results, status) => {{
            if (status !== 'OK' || !results || !results.length) {{
              reject(new Error(`We couldn't find that address (${{status}}). Try a more specific street + city.`));
              return;
            }}
            const r = results[0];
            resolve({{
              lat: r.geometry.location.lat(),
              lon: r.geometry.location.lng(),
              place: r.formatted_address,
            }});
          }});
        }});
        await runSearchWithCoords(place, lat, lon);
      }} catch (e) {{
        showError(e.message || 'Something went wrong. Please try again.');
        howit.style.display = '';
        reportEl.classList.remove('visible');
      }} finally {{
        setBusy(false);
      }}
    }}

    // Variant used when we already have lat/lng (from autocomplete pick or URL params).
    async function runSearchWithCoords(label, lat, lon) {{
      clearError();
      setBusy(true);
      try {{
        const wells = await nearestWells(lat, lon, 10);
        if (!wells.length) throw new Error('No water wells found near that location.');
        const rec = recommend(wells);
        renderReport(lat, lon, label, wells, rec);
        const params = new URLSearchParams({{
          address: label, lat: lat.toFixed(6), lng: lon.toFixed(6)
        }});
        history.replaceState(null, '', '?' + params.toString());
      }} catch (e) {{
        showError(e.message || 'Something went wrong. Please try again.');
        howit.style.display = '';
        reportEl.classList.remove('visible');
      }} finally {{
        setBusy(false);
      }}
    }}

    // ----------- Wire up form -------------------------------------------------
    form.addEventListener('submit', (e) => {{
      e.preventDefault();
      // If the user picked from autocomplete, just rerun with those coords.
      if (pickedPlace) {{
        runSearchWithCoords(pickedPlace.label, pickedPlace.lat, pickedPlace.lon);
        return;
      }}
      const addr = (addressInput.value || '').trim();
      if (!addr) return;
      runSearch(addr);
    }});

    // ----------- Auto-run if URL has params ----------------------------------
    (function() {{
      const params = new URLSearchParams(window.location.search);
      const lat = parseFloat(params.get('lat'));
      const lon = parseFloat(params.get('lng'));
      const place = params.get('address');
      if (place && !isNaN(lat) && !isNaN(lon)) {{
        addressInput.value = place;
        // Skip geocoding — use the lat/lng directly
        setBusy(true);
        nearestWells(lat, lon, 10).then(wells => {{
          if (!wells.length) {{
            showError('No water wells found near that location.');
            setBusy(false);
            return;
          }}
          renderReport(lat, lon, place, wells, recommend(wells));
          setBusy(false);
        }}).catch(e => {{
          showError(e.message || 'Could not load wells.');
          setBusy(false);
        }});
      }} else if (params.get('address')) {{
        addressInput.value = params.get('address');
        runSearch(params.get('address'));
      }}
    }})();
  </script>
  <script async defer src="https://maps.googleapis.com/maps/api/js?key={maps_key}&libraries=places&v=weekly&loading=async&callback=initMaps"></script>
</body>
</html>
"""


def main():
    html = INDEX_TEMPLATE.format(
        brand_css=BRAND_CSS,
        brand_name=BRAND["name"],
        brand_legal_name=BRAND["legal_name"],
        brand_tagline=BRAND["tagline"],
        brand_phone_display=BRAND["phone_display"],
        brand_phone_tel=BRAND["phone_tel"],
        brand_email=BRAND["email"],
        brand_website=BRAND["website"],
        brand_website_display=BRAND["website_display"],
        brand_license_blurb=BRAND["license_blurb"],
        brand_location_blurb=BRAND["location_blurb"],
        brand_service_area_blurb=BRAND["service_area_blurb"],
        twdb_url_template=TWDB_REPORT_URL,
        maps_key=GOOGLE_MAPS_PUBLIC_KEY,
    )
    out = REPORTS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
