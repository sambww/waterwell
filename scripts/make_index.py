#!/usr/bin/env python3
"""Generate docs/index.html — the branded landing page shown at the bare
GitHub Pages URL (https://sambww.github.io/waterwell/).

Does NOT list customer reports — each report URL is shared individually."""

from pathlib import Path
from generate_report import BRAND, BRAND_CSS, REPORTS_DIR

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{brand_name} &mdash; Water Well Depth Lookup</title>
  <style>
    {brand_css}
    .hero {{
      background: linear-gradient(135deg, var(--navy) 0%, var(--navy-2) 100%);
      color:#fff; padding:80px 24px 100px; text-align:center;
    }}
    .hero h1 {{ margin:0 0 14px; font-size:36px; font-weight:600; line-height:1.2; }}
    .hero p {{ margin:0 auto 28px; max-width:640px; font-size:17px; opacity:.92; line-height:1.55; }}
    .hero-cta {{ display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }}
    .btn {{
      display:inline-block; padding:14px 26px; border-radius:8px;
      font-weight:600; text-decoration:none; transition:transform .15s, box-shadow .15s;
    }}
    .btn:hover {{ transform:translateY(-1px); box-shadow:0 4px 14px rgba(0,0,0,.18); text-decoration:none; }}
    .btn-primary {{ background:var(--green); color:#fff; }}
    .btn-primary:hover {{ background:var(--green-dark); }}
    .btn-secondary {{ background:rgba(255,255,255,.12); color:#fff; border:1px solid rgba(255,255,255,.35); }}
    .wrap {{ max-width:980px; margin:0 auto; padding:48px 24px; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr)); gap:20px; margin-top:8px; }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:24px; }}
    .card h3 {{ margin:0 0 8px; color:var(--navy); font-size:17px; }}
    .card p {{ margin:0; color:#444; line-height:1.55; }}
    .badge {{
      display:inline-block; width:38px; height:38px; line-height:38px;
      text-align:center; background:var(--green-soft); color:var(--green-dark);
      border-radius:50%; font-weight:700; margin-bottom:12px;
    }}
    h2.section {{ font-size:22px; color:var(--navy); margin:0 0 18px; }}
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
    <h1>Water Well Depth Lookup</h1>
    <p>For every estimate request, we generate a custom report showing the ten nearest historical water wells from the Texas Water Development Board, with recommended drilling depths based on real local data.</p>
    <div class="hero-cta">
      <a href="tel:{brand_phone_tel}" class="btn btn-primary">Call {brand_phone_display}</a>
      <a href="{brand_website}" target="_blank" rel="noopener" class="btn btn-secondary">Visit our website</a>
    </div>
  </section>

  <div class="wrap">
    <h2 class="section">How it works</h2>
    <div class="cards">
      <div class="card">
        <div class="badge">1</div>
        <h3>You request an estimate</h3>
        <p>Call us or fill out the form on our website with your property address. We confirm the request and build your report the same day.</p>
      </div>
      <div class="card">
        <div class="badge">2</div>
        <h3>We pull the nearest wells</h3>
        <p>Your custom report locates the ten closest registered water wells from the Texas Water Development Board database, plotted on a live map.</p>
      </div>
      <div class="card">
        <div class="badge">3</div>
        <h3>You get a recommended depth</h3>
        <p>We recommend a target depth based on the deepest, most reliable nearby wells &mdash; with links to every well's official log so you can verify the numbers.</p>
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
        brand_logo=BRAND["logo_filename"],
        brand_license_blurb=BRAND["license_blurb"],
        brand_location_blurb=BRAND["location_blurb"],
        brand_service_area_blurb=BRAND["service_area_blurb"],
    )
    out = REPORTS_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
