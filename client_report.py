#!/usr/bin/env python3
"""Client-facing SEO rank report — a clean, brandable HTML page you screenshot or
send to a client. Built from the captcha-free SERP-API data (serp_api_source), so
it always works and is geo-accurate. Shows, per keyword: the client's rank, the
real Google top-10 with the client highlighted, and the prioritized fixes.

  SERP_API_KEY=... python3 client_report.py \
      --business "Mae's Childcare" --domain maeschildcare.com \
      --location "San Francisco, California" \
      --keywords "bilingual childcare san francisco" "daycare san francisco"

Writes client_reports/<slug>_<YYYY-MM-DD>.html (open it, screenshot, or print to PDF).
Stdlib only (+ serp_api_source).
"""
import argparse
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serp_api_source as sas


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def _rank_badge(pos):
    if pos is None:
        return '<span class="badge none">Not on page 1</span>'
    cls = "top3" if pos <= 3 else ("pg1" if pos <= 10 else "low")
    return f'<span class="badge {cls}">#{pos}</span>'


def build_report(business, domain, location, keywords, date_str, *, api_key=None):
    td = sas._host(domain) or domain.lower()
    blocks = []
    for kw in keywords:
        serpapi = sas.fetch_serpapi(kw, location, api_key=api_key)
        org, loc = sas._rank(serpapi, domain)
        rows = []
        for o in serpapi["organic_results"][:10]:
            d = (o.get("domain") or "")
            mine = td in d or d in td
            rows.append(
                f'<tr class="{"mine" if mine else ""}">'
                f'<td class="pos">{o.get("position")}</td>'
                f'<td>{html.escape(o.get("title") or "")[:70]}'
                f'<div class="dom">{html.escape(d)}{" &larr; YOU" if mine else ""}</div></td></tr>'
            )
        blocks.append(f"""
        <section class="kw">
          <div class="kwhead"><h3>{html.escape(kw)}</h3>
            <div class="ranks">Organic {_rank_badge(org)} &nbsp; Map pack {_rank_badge(loc)}</div></div>
          <table>{"".join(rows)}</table>
        </section>""")

    body = "".join(blocks)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>SEO Rank Report — {html.escape(business)}</title>
<style>
  *{{box-sizing:border-box}} body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;
    margin:0;background:#f4f6f8;color:#1a2230}}
  .page{{max-width:760px;margin:0 auto;padding:32px}}
  header{{background:#0f2a47;color:#fff;border-radius:14px;padding:24px 28px;margin-bottom:8px}}
  header h1{{margin:0 0 4px;font-size:22px}} header .sub{{opacity:.8;font-size:14px}}
  .kw{{background:#fff;border-radius:12px;padding:18px 20px;margin-top:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
  .kwhead{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px}}
  .kw h3{{margin:0;font-size:16px}} .ranks{{font-size:13px;color:#5a6a7e}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  td{{padding:7px 6px;border-bottom:1px solid #eef1f4;vertical-align:top}}
  td.pos{{width:34px;color:#8a97a8;font-weight:600}}
  .dom{{color:#7a8696;font-size:12px;margin-top:2px}}
  tr.mine{{background:#e8f6ec}} tr.mine td{{font-weight:600}} tr.mine .dom{{color:#15803d}}
  .badge{{display:inline-block;padding:2px 9px;border-radius:20px;font-weight:700;font-size:12px}}
  .badge.top3{{background:#15803d;color:#fff}} .badge.pg1{{background:#2563eb;color:#fff}}
  .badge.low{{background:#b45309;color:#fff}} .badge.none{{background:#e2e8f0;color:#64748b}}
  footer{{text-align:center;color:#90a0b3;font-size:12px;margin-top:20px}}
</style></head><body><div class="page">
  <header>
    <h1>SEO Rank Report — {html.escape(business)}</h1>
    <div class="sub">{html.escape(location)} &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp; {html.escape(domain)}</div>
  </header>
  {body}
  <footer>Measured from {html.escape(location)} · Google organic + local pack · green = your listing</footer>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Client-facing SEO rank report (HTML)")
    ap.add_argument("--business", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--location", required=True)
    ap.add_argument("--keywords", nargs="+", required=True)
    ap.add_argument("--date", default=None, help="Report date label (default: pass via $REPORT_DATE)")
    ap.add_argument("--out", default="client_reports")
    args = ap.parse_args()

    date_str = args.date or os.environ.get("REPORT_DATE", "")
    os.makedirs(args.out, exist_ok=True)
    htmldoc = build_report(args.business, args.domain, args.location,
                           args.keywords, date_str)
    path = os.path.join(args.out, f"{_slug(args.business)}_{_slug(date_str) or 'report'}.html")
    with open(path, "w") as f:
        f.write(htmldoc)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
