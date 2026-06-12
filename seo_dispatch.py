#!/usr/bin/env python3
"""SEO (Google SERP) dispatcher — talks directly to com.deviceagent (port 8765).

Runs a real, human-typed Google search on a fleet phone and pulls back SerpApi-like
structured data: ordered ORGANIC results (ads excluded), the LOCAL/Maps pack, an ad
count, and a proof screenshot — plus the target business's organic rank.

Flow per device:
    adb -s <serial> forward tcp:<local> tcp:8765
    POST http://localhost:<local>/session  {"type":"seo", "keyword":..., "targetDomain":...}
    → write <out>/<slug>.json  and  <out>/<slug>.png  (screenshot decoded from b64)

Usage:
    python3 seo_dispatch.py --keyword "personal injury lawyer austin" \
        --target ramosjames.com [--serial <adb-serial>] [--out seo_results]

    # or a batch file: JSON list of {"keyword":..., "target":...}
    python3 seo_dispatch.py --batch jobs.json --serial <adb-serial>

stdlib only — no requirements.
"""
import argparse
import base64
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

# One SEO session: reset+nav+type+SERP+scroll+parse (~95s direct). Through a residential
# proxy every page load is slower, so allow a longer ceiling (env-overridable).
HTTP_TIMEOUT_S = int(os.environ.get("SEO_HTTP_TIMEOUT_S", "200"))


def _adb(serial: str, *args: str, timeout: int = 15) -> str:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()


def _first_device() -> str:
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        if "\tdevice" in line:
            return line.split("\t")[0]
    sys.exit("No adb device found. Connect a phone or pass --serial.")


def _post_seo(local_port: int, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{local_port}/session",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"status": "error", "error": f"HTTP {e.code} (no body)"}
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        # App server dropped the connection mid-flow (RemoteDisconnected, reset, timeout).
        # Return an error result so the caller can rotate instead of crashing the run.
        return {"status": "error", "error": f"app connection error: {type(e).__name__}: {e}"}


def _slug(keyword: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
    return s[:60] or "query"


def _to_serpapi(*, keyword, target, serial, status, challenge, error, elapsed,
                serp, location_requested, local_png, organic_png, step_log):
    """Reshape the on-device parse into a SerpApi-compatible structure. Only fields obtainable
    from an on-device a11y scrape are populated; SerpApi-internal fields (place_id, lsig,
    gps_coordinates, thumbnail/favicon, redirect_link, raw_html_file, total_results) are omitted."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    location_used = serp.get("location") or location_requested or ""
    google_url = f"https://www.google.com/search?q={quote_plus(keyword)}&hl=en&gl=us"
    target_info = serp.get("target", {}) or {}

    def _rating(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    places = []
    for p in serp.get("local_pack", []):
        place = {
            "position": p.get("position"),
            "title": p.get("name"),
            "rating": _rating(p.get("rating")),
            "reviews": p.get("reviews"),
            "reviews_original": p.get("reviews_original") or None,
            "price": p.get("price") or None,
            "type": p.get("type") or None,
            "address": p.get("address") or None,
            "description": p.get("description") or None,
            "sponsored": bool(p.get("sponsored")),
        }
        places.append({k: v for k, v in place.items() if v not in (None, "")})

    organic = []
    for o in serp.get("organic", []):
        row = {
            "position": o.get("position"),
            "title": o.get("title"),
            "link": o.get("url"),
            "displayed_link": o.get("displayed_link") or o.get("domain"),
            "source": o.get("source") or o.get("domain"),
            "snippet": o.get("snippet") or None,
        }
        organic.append({k: v for k, v in row.items() if v not in (None, "")})

    return {
        "search_metadata": {
            "id": uuid.uuid4().hex,
            "status": "Success" if status == "completed" else (status or "Error"),
            "created_at": now,
            "processed_at": now,
            "google_url": google_url,
            "total_time_taken": elapsed,
            "engine_source": "device-agent on-device (Android Chrome via residential proxy)",
            "device_serial": serial,
        },
        "search_parameters": {
            "engine": "google",
            "q": keyword,
            "location_requested": location_requested or None,
            "location_used": location_used or None,
            "google_domain": "google.com",
            "device": "mobile",
            "target_domain": target or None,
        },
        "search_information": {
            "query_displayed": keyword,
            "results_for": location_used or None,
            "organic_results_state": "Results for exact spelling" if organic else "No results",
        },
        "local_results": {"places": places},
        "organic_results": organic,
        "target_ranking": {
            "domain": target_info.get("domain") or target,
            "organic_rank": target_info.get("organic_rank") or None,
            "local_rank": target_info.get("local_rank") or None,
        },
        "ads_excluded": serp.get("ads_excluded", 0),
        "local_ads_excluded": serp.get("local_ads_excluded", 0),
        "screenshots": {"local": local_png or None, "organic": organic_png or None},
        "challenge": bool(challenge),
        "error": error or "",
        "_step_log": step_log,
    }


def dispatch_one(serial: str, keyword: str, target: str | None, out_dir: Path,
                 local_port: int = 8765, retries: int = 2, retry_wait_s: int = 45,
                 location: str = "") -> dict:
    """Run one SEO session on a device; write JSON + PNG; return a compact summary.

    Auto-retries when the phone reports a bot/reCAPTCHA block (status "blocked" /
    challenge=true), so a single command rides out a transient "unusual traffic" block
    without manual intervention. A persistent block survives all retries and is flagged.
    """
    _adb(serial, "forward", f"tcp:{local_port}", "tcp:8765", timeout=10)
    body = {"type": "seo", "keyword": keyword}
    if target:
        body["targetDomain"] = target
    # Pass the location into the request body so the device pins it via the `uule`
    # URL param (city-accurate SERP on top of the Decodo US IP). Previously location
    # was used only as output metadata (location_requested) and never reached the
    # device — so the SERP was localized only by the proxy IP, not the target city.
    if location:
        body["location"] = location

    t0 = time.time()
    resp = _post_seo(local_port, body)
    attempt = 1
    while (resp.get("status") == "blocked" or resp.get("challenge")) and attempt <= retries:
        print(f"   ⚠ bot challenge — auto-retry {attempt}/{retries} in {retry_wait_s}s "
              f"(let the IP cool / rotate proxy)…")
        time.sleep(retry_wait_s)
        resp = _post_seo(local_port, body)
        attempt += 1
    elapsed = round(time.time() - t0, 1)

    serp = resp.get("serp", {}) or {}
    organic = serp.get("organic", [])
    local = serp.get("local_pack", [])
    target_info = serp.get("target", {}) or {}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{_slug(keyword)}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Decode the proof screenshots (b64 inlined in the response — no adb pull needed).
    # Two shots: one framed on the local/Maps pack, one on the organic results.
    def _save_b64(key: str, suffix: str) -> str:
        b = resp.pop(key, "")
        if not b:
            return ""
        p = str(out_dir / f"{stem}_{suffix}.png")
        with open(p, "wb") as f:
            f.write(base64.b64decode(b))
        return p

    local_png = _save_b64("screenshot_local_b64", "local")
    organic_png = _save_b64("screenshot_organic_b64", "organic")
    # legacy single screenshot (older APKs); also the back-compat field
    b64 = resp.pop("screenshot_b64", "")
    png_path = local_png or ""
    if b64 and not local_png:
        png_path = str(out_dir / f"{stem}.png")
        with open(png_path, "wb") as f:
            f.write(base64.b64decode(b64))

    # Persist the result in SerpApi-compatible shape (only on-device-obtainable fields).
    record = _to_serpapi(
        keyword=keyword, target=target, serial=serial,
        status=resp.get("status"), challenge=bool(resp.get("challenge")),
        error=resp.get("error", ""), elapsed=elapsed, serp=serp,
        location_requested=location, local_png=local_png, organic_png=organic_png,
        step_log=resp.get("step_log", []),
    )
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(record, indent=2))

    return {
        "keyword": keyword,
        "status": resp.get("status"),
        "challenge": bool(resp.get("challenge")),
        "error": resp.get("error", ""),
        "organic_count": len(organic),
        "ads_excluded": serp.get("ads_excluded", 0),
        "local_count": len(local),
        "organic_rank": target_info.get("organic_rank") or None,
        "local_rank": target_info.get("local_rank") or None,
        "elapsed_s": elapsed,
        "json": str(json_path),
        "png": png_path,
        "png_local": local_png,
        "png_organic": organic_png,
    }


def _print_summary(s: dict) -> None:
    if s["status"] == "blocked" or s["challenge"]:
        print(f"[BLOCKED] \"{s['keyword']}\" — {s['error']} · {s['elapsed_s']}s "
              f"(retries exhausted; rotate proxy IP)")
        if s["png"]:
            print(f"   evidence png: {s['png']}")
        return
    rank = s["organic_rank"]
    rank_str = f"#{rank}" if rank else "not found"
    lrank = s.get("local_rank")
    lrank_str = f"#{lrank}" if lrank else "not found"
    print(
        f"[{s['status']}] \"{s['keyword']}\" — {s['organic_count']} organic "
        f"({s['ads_excluded']} ads excluded), {s['local_count']} local · "
        f"organic {rank_str} · local {lrank_str} · {s['elapsed_s']}s"
    )
    print(f"   json: {s['json']}")
    if s.get("png_local"):
        print(f"   png (local):   {s['png_local']}")
    if s.get("png_organic"):
        print(f"   png (organic): {s['png_organic']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="On-device Google SERP rank + screenshot dispatcher")
    ap.add_argument("--keyword", help="Search query to run")
    ap.add_argument("--target", help="Target business domain to rank (e.g. ramosjames.com)")
    ap.add_argument("--batch", help="Path to a JSON list of {keyword, target} jobs")
    ap.add_argument("--serial", help="adb serial (default: first connected device)")
    ap.add_argument("--out", default="seo_results", help="Output directory (default: seo_results)")
    ap.add_argument("--local-port", type=int, default=8765, help="Local adb-forward port")
    ap.add_argument("--retries", type=int, default=2, help="Auto-retries on a bot/reCAPTCHA block (default: 2)")
    ap.add_argument("--retry-wait", type=int, default=45, help="Seconds between block retries (default: 45)")
    ap.add_argument("--location", default="", help="Geo we proxied to, for search_parameters.location_requested (e.g. 'Austin, Texas')")
    args = ap.parse_args()

    serial = args.serial or _first_device()
    out_dir = Path(args.out)

    if args.batch:
        jobs = json.loads(Path(args.batch).read_text())
    elif args.keyword:
        jobs = [{"keyword": args.keyword, "target": args.target}]
    else:
        ap.error("provide --keyword (with optional --target) or --batch")

    for job in jobs:
        summary = dispatch_one(serial, job["keyword"], job.get("target"), out_dir,
                               local_port=args.local_port, retries=args.retries,
                               retry_wait_s=args.retry_wait, location=args.location)
        _print_summary(summary)


if __name__ == "__main__":
    main()
