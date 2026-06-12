#!/usr/bin/env python3
"""Geo-grid local rank — measure ONE keyword from a spread of points around the
client and render a heat map (where they rank top-3 vs fade). This is the
LocalFalcon-style grid: local rank is proximity-ranked, so a business wins near
its location and drops off with distance — the map shows exactly where.

v1 = neighborhood precision via the SERP API (captcha-free, works now). Each point
is a (label, Google-location-string, lat, lng); we measure the keyword from each
location string and place a colored cell at its lat/lng. Exact-GPS precision (phone
mock-location per point) is the planned v2 for the map-pack surface.

  SERP_API_KEY=... python3 geo_grid.py \
      --business "Mae's Childcare" --domain maeschildcare.com \
      --keyword "childcare near me" --grid sf

Writes geo_grid_results/<slug>_<kw>.json + .html (open the HTML = the heat map).
Stdlib only (+ serp_api_source).
"""
import argparse
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serp_api_source as sas

# Built-in San Francisco grid — (label, Google location string, lat, lng).
# Spread across the city so distance-decay is visible. Add cities as needed.
GRIDS = {
    "sf": [
        ("Marina",            "Marina District, San Francisco, California",   37.803, -122.436),
        ("Nob Hill",          "Nob Hill, San Francisco, California",          37.793, -122.415),
        ("Richmond",          "Richmond District, San Francisco, California", 37.780, -122.483),
        ("SoMa",              "South of Market, San Francisco, California",   37.778, -122.405),
        ("Sunset",            "Sunset District, San Francisco, California",   37.752, -122.494),
        ("Castro",            "Castro, San Francisco, California",            37.762, -122.435),
        ("Mission",           "Mission District, San Francisco, California",  37.760, -122.418),
        ("Glen Park",         "Glen Park, San Francisco, California",         37.733, -122.433),
        ("Bernal Heights",    "Bernal Heights, San Francisco, California",    37.739, -122.416),
        ("Bayview",           "Bayview, San Francisco, California",           37.730, -122.392),
    ],
}


def _slug(s):
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def measure_grid(business, domain, keyword, points, *, api_key=None):
    cells = []
    for label, loc, lat, lng in points:
        try:
            serpapi = sas.fetch_serpapi(keyword, loc, api_key=api_key)
            org, loc_rank = sas._rank(serpapi, domain)
        except Exception as e:
            org, loc_rank = None, None
            print(f"  [{label}] error: {type(e).__name__}: {e}", flush=True)
        best = loc_rank or org   # local pack wins for "near me"; else organic
        cells.append({"label": label, "location": loc, "lat": lat, "lng": lng,
                      "organic": org, "local": loc_rank, "rank": best})
        print(f"  {label:16} organic={org or '—':>3}  local={loc_rank or '—':>3}", flush=True)
    return cells


def _color(rank):
    if rank is None:      return "#e2e8f0", "#64748b", "21+"
    if rank <= 3:         return "#15803d", "#ffffff", str(rank)   # green: top 3
    if rank <= 10:        return "#2563eb", "#ffffff", str(rank)   # blue: page 1
    return "#b45309", "#ffffff", str(rank)                         # amber: 11-20


def render_html(business, domain, keyword, cells):
    lats = [c["lat"] for c in cells]; lngs = [c["lng"] for c in cells]
    la0, la1 = min(lats), max(lats); ln0, ln1 = min(lngs), max(lngs)
    span_la = (la1 - la0) or 1e-6; span_ln = (ln1 - ln0) or 1e-6
    dots = []
    for c in cells:
        x = 6 + (c["lng"] - ln0) / span_ln * 88          # west→east
        y = 6 + (la1 - c["lat"]) / span_la * 88          # north→south (screen y inverted)
        bg, fg, txt = _color(c["rank"])
        dots.append(
            f'<div style="position:absolute;left:{x:.1f}%;top:{y:.1f}%;transform:translate(-50%,-50%);'
            f'width:62px;height:62px;border-radius:50%;background:{bg};color:{fg};'
            f'display:flex;flex-direction:column;align-items:center;justify-content:center;'
            f'font-size:11px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.25);">'
            f'<div style="font-size:18px;font-weight:700;line-height:1">{txt}</div>'
            f'<div style="font-size:9px;opacity:.9;max-width:58px;overflow:hidden">{html.escape(c["label"])}</div></div>'
        )
    top3 = sum(1 for c in cells if c["rank"] and c["rank"] <= 3)
    pg1 = sum(1 for c in cells if c["rank"] and c["rank"] <= 10)
    avg = [c["rank"] for c in cells if c["rank"]]
    avg_txt = f"{sum(avg)/len(avg):.1f}" if avg else "—"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Geo-grid — {html.escape(business)} — {html.escape(keyword)}</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f4f6f8;margin:0;color:#1a2230}}
.wrap{{max-width:680px;margin:0 auto;padding:28px}}
h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#5a6a7e;font-size:13px;margin-bottom:16px}}
.stats{{display:flex;gap:10px;margin-bottom:16px}}
.stat{{background:#fff;border-radius:10px;padding:10px 14px;flex:1;text-align:center}}
.stat b{{font-size:22px;display:block}} .stat span{{font-size:12px;color:#5a6a7e}}
.map{{position:relative;width:100%;padding-top:75%;background:#fff;border-radius:14px;border:1px solid #e6eaf0}}
.legend{{display:flex;gap:14px;justify-content:center;margin-top:14px;font-size:12px;color:#5a6a7e}}
.lg{{display:inline-flex;align-items:center;gap:5px}} .sw{{width:13px;height:13px;border-radius:50%;display:inline-block}}</style></head>
<body><div class="wrap">
<h1>Geo-grid rank — {html.escape(business)}</h1>
<div class="sub">"{html.escape(keyword)}" · across {len(cells)} points · {html.escape(domain)}</div>
<div class="stats">
  <div class="stat"><b>{top3}/{len(cells)}</b><span>points in top 3</span></div>
  <div class="stat"><b>{pg1}/{len(cells)}</b><span>points on page 1</span></div>
  <div class="stat"><b>{avg_txt}</b><span>avg rank (ranked pts)</span></div>
</div>
<div class="map">{''.join(dots)}</div>
<div class="legend">
  <span class="lg"><span class="sw" style="background:#15803d"></span>top 3</span>
  <span class="lg"><span class="sw" style="background:#2563eb"></span>page 1 (4–10)</span>
  <span class="lg"><span class="sw" style="background:#b45309"></span>11–20</span>
  <span class="lg"><span class="sw" style="background:#e2e8f0"></span>not ranked</span>
</div></div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Geo-grid local rank heat map")
    ap.add_argument("--business", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--grid", default="sf", help=f"built-in grid: {list(GRIDS)}")
    ap.add_argument("--out", default="geo_grid_results")
    args = ap.parse_args()

    points = GRIDS.get(args.grid)
    if not points:
        ap.error(f"unknown grid {args.grid!r}; have {list(GRIDS)}")
    print(f"Geo-grid: '{args.keyword}' for {args.business} across {len(points)} points")
    cells = measure_grid(args.business, args.domain, args.keyword, points)

    os.makedirs(args.out, exist_ok=True)
    stem = f"{_slug(args.business)}_{_slug(args.keyword)}"
    json.dump({"business": args.business, "domain": args.domain, "keyword": args.keyword,
               "cells": cells}, open(os.path.join(args.out, stem + ".json"), "w"), indent=2)
    open(os.path.join(args.out, stem + ".html"), "w").write(
        render_html(args.business, args.domain, args.keyword, cells))
    top3 = sum(1 for c in cells if c["rank"] and c["rank"] <= 3)
    print(f"DONE — top3 at {top3}/{len(cells)} points → {args.out}/{stem}.html")


if __name__ == "__main__":
    main()
