#!/usr/bin/env python3
"""Signal SEO — daily orchestrator (engagement).

Every morning, for each client, drive the fleet through the daily SEO flow:

  1. keyword set         — the locked keywords from setup (per client config)
  2. search on Google    — localized: phone egresses a US Decodo IP via the gost
                           tunnel, with the client's city as uule (--location)
  3. find the backlink   — the client's listing, organic or local pack
  4. click the listing   — the phone taps the result
  5. scroll & dwell      — human-like dwell on the destination page

This is ENGAGEMENT only. It does NOT measure rank, does NOT create a serp-run,
and records NOTHING back to the tracker. (Rank measurement is a separate path:
`serp_fleet_worker.py --base ... --run-id ...`.)

Cron this once a day. Clients live in a JSON file — the SEO shape or the AEO
catalog shape (aeo-appium/clients.json) both work:
  [
    {"business_name":"Ramos James Law","business_domain":"ramosjames.com",
     "location":"Austin, Texas","keywords":["personal injury lawyer","car accident attorney"],
     "device_idx":5}
  ]

  set -a; source .env.dev; set +a          # PROXY_* (gost auth)
  python3 signal_seo_daily.py clients.json
  DRY_RUN=1 python3 signal_seo_daily.py clients.json     # plan only, no calls
"""
import json
import os
import subprocess
import sys

DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
OUT = os.environ.get("SIGNAL_OUT", "/tmp/signal_seo")
DEFAULT_IDX = os.environ.get("SIGNAL_DEVICE_IDX", "5")   # device-106
PYBIN = os.environ.get("SIGNAL_PY", sys.executable)
HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "serp_fleet_worker.py")
# Phone egress path. 'gost' (DEFAULT) = on-phone socksdroid VPN -> Decodo US IP.
# 'superproxy' = Decodo Mobile tunnel. 'serper' is NOT valid here — the SERP API
# path cannot click a listing, and daily is engagement only.
SOURCE = os.environ.get("SIGNAL_SOURCE", "gost")
GATEWAY = os.environ.get("SIGNAL_GATEWAY", "residential")   # gost: residential|mobile
COUNTRY = os.environ.get("SIGNAL_COUNTRY", "us")
# query-retries doubles as the captcha-rotation budget (each retry rotates the
# exit IP). Decodo residential direct-nav has a non-trivial captcha rate.
QUERY_RETRIES = os.environ.get("SIGNAL_QUERY_RETRIES", "8")


def _normalize_client(c: dict) -> dict:
    """Accept BOTH the SEO config shape and the AEO catalog shape
    (aeo-appium/clients.json) so SEO and AEO run the SAME client list — no
    duplicate config. AEO uses biz_name/biz_url/city+state and keywords as
    [{keyword, backlinks}]; map those to the SEO fields. The AEO `backlinks`
    (AI-engine citation URLs) are ignored — daily clicks the SERP *listing* for
    business_domain, not those URLs."""
    from urllib.parse import urlparse
    name = c.get("business_name") or c.get("biz_name")
    domain = c.get("business_domain")
    if not domain and c.get("biz_url"):
        domain = urlparse(c["biz_url"]).netloc.lower().removeprefix("www.") or None
    location = c.get("location")
    if not location and c.get("city"):
        location = f"{c['city']}, {c.get('state', '')}".strip().rstrip(", ")
    keywords = [(k.get("keyword") if isinstance(k, dict) else k)
                for k in (c.get("keywords") or [])]
    keywords = [k for k in keywords if k]
    # Geo pin: AEO `proxy{zip, iproyal_city, iproyal_state, latitude, longitude}` →
    # pin the Decodo exit IP to the client's ZIP/city (so local keywords surface the
    # client) AND push street-level mock-GPS. Falls back to top-level fields.
    px = c.get("proxy") or {}
    geo = {
        "zip": str(c.get("zip") or px.get("zip") or "").strip(),
        "city": str(c.get("city_slug") or px.get("iproyal_city") or "").strip(),
        "state": str(c.get("state_slug") or px.get("iproyal_state") or "").strip(),
        "lat": c.get("lat") or px.get("latitude"),
        "lng": c.get("lng") or px.get("longitude"),
    }
    return {**c, "business_name": name, "business_domain": domain,
            "location": location or "", "keywords": keywords, "geo": geo}


def run_client(c: dict) -> dict:
    c = _normalize_client(c)
    name = c["business_name"]
    location = c.get("location", "")
    domain = c.get("business_domain")
    keywords = c["keywords"]
    idx = str(c.get("device_idx", DEFAULT_IDX))
    print(f"\n=== {name} — {location} ({len(keywords)} keywords) ===", flush=True)

    if SOURCE == "serper":
        raise RuntimeError("SIGNAL_SOURCE=serper cannot click listings; daily is "
                           "engagement only — use gost (default) or superproxy")
    if not domain:
        print("  [skip] no business_domain — nothing to find/click", flush=True)
        return {"client": name, "skipped": "no_domain"}
    if not keywords:
        print("  [skip] no keywords", flush=True)
        return {"client": name, "skipped": "no_keywords"}

    # Engagement-only bridge call: keywords sourced locally (--keyword), the phone
    # searches + clicks + dwells through the localized tunnel, nothing is recorded.
    cmd = [PYBIN, BRIDGE, "--proxy", SOURCE, "--engage",
           "--device-idx", idx, "--country", COUNTRY, "--gateway", GATEWAY,
           "--location", location, "--target-domain", domain, "--target-name", name,
           "--query-retries", QUERY_RETRIES, "--out", OUT]
    geo = c.get("geo") or {}
    if geo.get("zip"):    cmd += ["--zip", geo["zip"]]
    if geo.get("city"):   cmd += ["--city", geo["city"]]
    if geo.get("state"):  cmd += ["--geo-state", geo["state"]]
    if geo.get("lat") is not None and geo.get("lng") is not None:
        cmd += ["--lat", str(geo["lat"]), "--lng", str(geo["lng"])]
    for kw in keywords:
        cmd += ["--keyword", kw]
    if c.get("device_serial"):              # pin to a phone (robust to mDNS serial drift)
        cmd += ["--serial", c["device_serial"]]

    if DRY_RUN:
        print(f"  [dry] search+click+dwell {keywords} via {SOURCE} (device-idx {idx})")
        print(f"  [dry] {' '.join(cmd)}")
        return {"client": name, "dry": True}

    print(f"  engaging {len(keywords)} keyword(s) via fleet…", flush=True)
    subprocess.run(cmd, check=False)
    return {"client": name, "keywords": keywords}


def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "clients.json")
    clients = json.load(open(cfg))
    print(f"Signal SEO daily (engagement) — {len(clients)} client(s) | "
          f"source={SOURCE} | dry={DRY_RUN}", flush=True)
    results = [run_client(c) for c in clients]
    ok = sum(1 for r in results if not r.get("dry") and not r.get("skipped"))
    print(f"\nDONE — {ok} client(s) engaged", flush=True)


if __name__ == "__main__":
    main()
