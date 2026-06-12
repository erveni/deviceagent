#!/usr/bin/env python3
"""Provider-agnostic SERP-API measurement source — the captcha-free alternative
to the on-phone Google path.

Why this exists: scraping Google on real phones through residential proxies hits
reCAPTCHA on a large share of the (shared, burned) IP pool — unfixable in code.
A SERP API runs the proxy rotation + captcha handling server-side and returns
structured JSON, so daily rank measurement just works. Keep the phone fleet for
the AI engines (ChatGPT/Gemini/Perplexity) that have no API.

One provider is wired now (Serper.dev — most generous free tier, cheapest paid),
behind a ``provider`` switch so Scrape.do / DataForSEO / Decodo SERP can be added
without touching callers. Output is mapped to the SAME SerpApi-shaped dict the
on-phone path produces, so ``serp_fleet_worker.serpapi_to_ingest`` and the whole
downstream report engine are unchanged.

Stdlib only.

  SERP_API_KEY=... python3 serp_api_source.py "bilingual childcare san francisco" \
      --location "San Francisco, California" --target maeschildcare.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_PROVIDER = os.environ.get("SERP_PROVIDER", "serper")


def _host(url: str) -> str:
    """Registrable-ish host: lowercase, strip scheme/www/path. '' if unparseable."""
    try:
        net = urlparse(url if "://" in url else "http://" + url).netloc.lower()
        return net[4:] if net.startswith("www.") else net
    except Exception:
        return ""


def _norm_location(location: str) -> str:
    """Serper wants a canonical Google location. Append country if the caller
    passed just 'City, State' (our client configs do)."""
    loc = (location or "").strip()
    if loc and "united states" not in loc.lower() and "usa" not in loc.lower():
        loc = f"{loc}, United States"
    return loc


# ── providers: each returns a RAW provider response dict ─────────────────────

def _fetch_serper(keyword: str, location: str, api_key: str,
                  *, gl: str = "us", hl: str = "en", num: int = 20,
                  timeout: int = 30) -> dict:
    body = json.dumps({
        "q": keyword,
        "location": _norm_location(location),
        "gl": gl, "hl": hl, "num": num,
    }).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/search", data=body,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


_PROVIDERS = {"serper": _fetch_serper}


# ── map RAW provider response -> SerpApi-shaped dict (pipeline contract) ──────

def _serper_to_serpapi(data: dict) -> dict:
    organic = []
    for o in data.get("organic", []) or []:
        link = o.get("link", "")
        organic.append({
            "position": o.get("position"),
            "title": o.get("title"),
            "link": link,
            "displayed_link": link,
            "domain": _host(link),       # so domain-match works in any downstream
            "snippet": o.get("snippet"),
        })
    places = []
    for i, p in enumerate(data.get("places", []) or [], start=1):
        places.append({
            "position": p.get("position", i),
            "title": p.get("title"),
            "rating": p.get("rating"),
            "reviews": p.get("ratingCount") or p.get("reviews"),
            "type": p.get("type") or p.get("category"),
            "address": p.get("address"),
            "sponsored": False,
        })
    return {"organic_results": organic, "local_results": {"places": places}}


_MAPPERS = {"serper": _serper_to_serpapi}


# ── public: one keyword -> SerpApi-shaped dict ───────────────────────────────

def fetch_serpapi(keyword: str, location: str, *, provider: str = DEFAULT_PROVIDER,
                  api_key: str | None = None, **kw) -> dict:
    """Fetch one keyword via ``provider`` and return a SerpApi-shaped result."""
    key = api_key or os.environ.get("SERP_API_KEY")
    if not key:
        raise RuntimeError("no SERP API key — set $SERP_API_KEY or pass api_key")
    if provider not in _PROVIDERS:
        raise RuntimeError(f"unknown SERP provider {provider!r}; have {list(_PROVIDERS)}")
    raw = _PROVIDERS[provider](keyword, location, key, **kw)
    serpapi = _MAPPERS[provider](raw)
    serpapi["_provider"] = provider
    serpapi["_credits"] = raw.get("credits")
    return serpapi


def make_dispatch_query(location: str, *, provider: str = DEFAULT_PROVIDER,
                        api_key: str | None = None):
    """Return a ``dispatch_query(keyword)`` compatible with
    ``serp_fleet_worker.process_run`` — same {serpapi,status,challenge,error}
    contract as the on-phone ``_dispatch_query_real``, so the orchestration loop
    is identical. A SERP API never returns a captcha, so challenge is always False;
    a transient API error becomes status='error' (process_run will retry)."""
    def dispatch_query(keyword: str) -> dict:
        try:
            serpapi = fetch_serpapi(keyword, location, provider=provider, api_key=api_key)
            return {"serpapi": serpapi, "status": "completed",
                    "challenge": False, "error": ""}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            return {"serpapi": {"organic_results": [], "local_results": {"places": []}},
                    "status": "error", "challenge": False,
                    "error": f"HTTP {e.code}: {detail}"}
        except Exception as e:
            return {"serpapi": {"organic_results": [], "local_results": {"places": []}},
                    "status": "error", "challenge": False,
                    "error": f"{type(e).__name__}: {e}"}
    return dispatch_query


def _rank(serpapi: dict, target: str) -> tuple[int | None, int | None]:
    """Organic + local rank of ``target`` (for CLI/manual use). Brand-token match
    on local names (Google shows the business name, not a domain)."""
    td = _host(target) or target.lower()
    brand = td.split(".")[0]
    org = next((o["position"] for o in serpapi["organic_results"]
                if td in (o.get("domain") or "") or (o.get("domain") or "") in td), None)
    loc = next((p["position"] for p in serpapi["local_results"]["places"]
                if brand and len(brand) >= 4
                and brand in (p.get("title") or "").replace(" ", "").lower()), None)
    return org, loc


def main() -> None:
    ap = argparse.ArgumentParser(description="One-off SERP-API rank check")
    ap.add_argument("keyword")
    ap.add_argument("--location", default="")
    ap.add_argument("--target", default=None, help="domain to rank (e.g. maeschildcare.com)")
    ap.add_argument("--provider", default=DEFAULT_PROVIDER)
    args = ap.parse_args()

    serpapi = fetch_serpapi(args.keyword, args.location, provider=args.provider)
    print(f"provider={serpapi.get('_provider')} credits={serpapi.get('_credits')} "
          f"organic={len(serpapi['organic_results'])} "
          f"local={len(serpapi['local_results']['places'])}")
    for o in serpapi["organic_results"][:10]:
        print(f"  #{o['position']}: {o.get('domain'):30} {o.get('title','')[:40]}")
    if args.target:
        org, loc = _rank(serpapi, args.target)
        print(f"\nTARGET {args.target}: organic={org or '—'}  local={loc or '—'}")


if __name__ == "__main__":
    main()
