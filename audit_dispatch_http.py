"""HTTP-based audit dispatcher — talks directly to com.deviceagent (port 8765).

Replaces the audit.py subprocess path with a single HTTP POST to the phone's
device-agent app. Same code path as the daily flow, so reliability matches
daily (which has been hardened to near-100%).

Architecture:
  Solace job → solace_consumer → dispatch_audit_job (this file)
    → acquire phone from POOL
    → start per-job gost listener (Mac side)
    → configure socksdroid on phone via ADB (mirrors run_with_proxy.py)
    → adb forward tcp:<local> tcp:8765
    → POST http://localhost:<local>/session {type=audit, ...}
    → parse response → CSV row
    → cleanup (forward --remove, socksdroid disconnect, gost stop)

Why this exists:
  - audit.py subprocess + ADB/CDP path is flaky (Perplexity flow_failed ~20-30%)
  - device-agent app already has executeAuditSession with hardened
    dismissPlatformPopups + 120s wait_for_generation
  - One HTTP call replaces a 60-360s subprocess
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pathlib import Path

from run_with_proxy import DEVICES, socksdroid_connect, socksdroid_disconnect, mock_location, set_timezone
from device_dispatch import POOL

# Decodo zip-coverage cache — written by /tmp/probe_problem_zips.py and
# friends. We consult it before constructing the gost spec so that zips
# Decodo can't actually serve get rewritten to a nearby supported zip
# (or dropped entirely so gost falls back to region-only).
_ZIP_CACHE_PATH = Path("/tmp/decodo_zip_cache.json")
_ZIP_CACHE: dict[str, dict] = {}
if _ZIP_CACHE_PATH.exists():
    try:
        _ZIP_CACHE = json.loads(_ZIP_CACHE_PATH.read_text())
    except Exception:
        _ZIP_CACHE = {}


# State → known-good Decodo zip. Built from empirical probes 2026-05-14 evening.
# When a client's assigned zip fails (per cache) or is in _BROKEN_ZIP_OVERRIDE,
# the dispatcher swaps to the same-state known-good zip — same-state geo is far
# better than funneling everything to NYC, and distributes load so no single
# zip gets hammered.
_STATE_GOOD_ZIP: dict[str, str] = {
    "AZ": "85006", "CA": "90210", "CO": "80202", "FL": "33445", "GA": "30338",
    "IL": "60601", "IN": "46202", "KY": "40422", "MD": "21701", "MS": "38103",
    "NC": "28303", "NJ": "08736", "NY": "10001", "OH": "34200", "PA": "19102",
    "RI": "02904", "TN": "37402", "TX": "76016", "UT": "84041", "VA": "24502",
    "WA": "98115",
}
_FALLBACK_GOOD_ZIP = "10001"  # used when state has no entry above

# Client zips observed to fail end-to-end audits even when probe says supported.
# These get routed to their state's known-good zip via _resolve_zip below.
_BROKEN_ZIP_OVERRIDE: set[str] = {
    "45217",  # OH Cincinnati
    "38654",  # MS Olive Branch
    "92590",  # CA Temecula
    "95135",  # CA San Jose
    "27518",  # NC Cary
    "62260",  # IL Millstadt
    "46221",  # IN Indianapolis
    "85286",  # AZ Gilbert
    "19047",  # PA Langhorne
}


def _resolve_zip(assigned_zip: str, state: str = "") -> tuple[str, str]:
    """Map an assigned zip to the zip we'll actually send to Decodo.
    Returns (effective_zip, note). Routing precedence:
      1. broken-zip override → state's known-good zip (or NYC if state unmapped)
      2. cache says supported=False with a nearest_supported_zip → use that
      3. cache says supported=False with no nearest → state's known-good zip
      4. cache says supported (or no cache) → use as-is
    """
    if not assigned_zip:
        # Empty zip — go straight to state's known-good
        good = _STATE_GOOD_ZIP.get(state.upper(), _FALLBACK_GOOD_ZIP)
        return good, f"empty_zip_to_{state}_known_good_{good}"

    if assigned_zip in _BROKEN_ZIP_OVERRIDE:
        good = _STATE_GOOD_ZIP.get(state.upper(), _FALLBACK_GOOD_ZIP)
        return good, f"override_{state}_to_{good}"

    info = _ZIP_CACHE.get(assigned_zip)
    if not info:
        return assigned_zip, "uncached"
    nearest = (info.get("nearest_supported_zip") or "").strip()
    if info.get("supported") is False:
        if nearest and nearest != assigned_zip:
            return nearest, f"fallback_to_{nearest}"
        good = _STATE_GOOD_ZIP.get(state.upper(), _FALLBACK_GOOD_ZIP)
        return good, f"unsupported_{state}_to_{good}"
    return assigned_zip, "cached_ok"


# Cached zip → (lat, lng) lookup. Populated lazily via api.zippopotam.us.
# Phones use this to mock GPS so geolocation matches the Decodo proxy IP
# (daily flow does the same via job["biz_lat"]/["biz_lng"]; audit job has
# only zip, so we resolve it here once per zip).
_ZIP_LATLNG_CACHE: dict[str, tuple[float, float] | None] = {}


_STATE_TZ = {
    "CT": "America/New_York", "DE": "America/New_York", "DC": "America/New_York",
    "FL": "America/New_York", "GA": "America/New_York", "ME": "America/New_York",
    "MD": "America/New_York", "MA": "America/New_York", "MI": "America/New_York",
    "NH": "America/New_York", "NJ": "America/New_York", "NY": "America/New_York",
    "NC": "America/New_York", "OH": "America/New_York", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York", "VT": "America/New_York",
    "VA": "America/New_York", "WV": "America/New_York", "IN": "America/New_York",
    "AL": "America/Chicago", "AR": "America/Chicago", "IL": "America/Chicago",
    "IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/Chicago",
    "LA": "America/Chicago", "MN": "America/Chicago", "MS": "America/Chicago",
    "MO": "America/Chicago", "NE": "America/Chicago", "ND": "America/Chicago",
    "OK": "America/Chicago", "SD": "America/Chicago", "TN": "America/Chicago",
    "TX": "America/Chicago", "WI": "America/Chicago",
    "AZ": "America/Phoenix", "CO": "America/Denver", "ID": "America/Denver",
    "MT": "America/Denver", "NM": "America/Denver", "UT": "America/Denver",
    "WY": "America/Denver",
    "CA": "America/Los_Angeles", "NV": "America/Los_Angeles",
    "OR": "America/Los_Angeles", "WA": "America/Los_Angeles",
    "AK": "America/Anchorage", "HI": "Pacific/Honolulu",
}


def _zip_to_latlng(zip_code: str) -> tuple[float, float] | None:
    if not zip_code:
        return None
    if zip_code in _ZIP_LATLNG_CACHE:
        return _ZIP_LATLNG_CACHE[zip_code]
    try:
        with urllib.request.urlopen(
            f"https://api.zippopotam.us/us/{zip_code}", timeout=4
        ) as r:
            data = json.loads(r.read())
            place = data.get("places", [{}])[0]
            lat = float(place.get("latitude"))
            lng = float(place.get("longitude"))
            _ZIP_LATLNG_CACHE[zip_code] = (lat, lng)
            return (lat, lng)
    except Exception:
        _ZIP_LATLNG_CACHE[zip_code] = None
        return None

sys.path.insert(0, "/Users/seolocalph/projects/aeo-appium")
from gost_manager import GostManager  # noqa: E402

AUDIT_LOG = "/Users/seolocalph/projects/aeo-appium/audit_results/audit_log.csv"
AUDIT_RESULTS_DIR = "/Users/seolocalph/projects/aeo-appium/audit_results"
AUDIT_CLIENTS_JSON = os.environ.get(
    "AUDIT_CLIENTS_JSON_PATH",
    "/Users/seolocalph/projects/aeo-appium/clients_audit_targets.json",
)


def _write_response_text(text: str, platform: str, keyword_id: int) -> str:
    """Write the full LLM response text to audit_results/<Platform>/kw<KW>_<platform>_<TS>.txt
    Returns the local path written, or empty string on failure / empty input."""
    if not text:
        return ""
    plat_dir_map = {"chatgpt": "ChatGPT", "gemini": "Gemini", "perplexity": "Perplexity"}
    plat_dir = plat_dir_map.get(platform.lower(), platform)
    local_dir = os.path.join(AUDIT_RESULTS_DIR, plat_dir)
    os.makedirs(local_dir, exist_ok=True)
    fname = f"kw{keyword_id}_{platform.lower()}_{int(datetime.now(timezone.utc).timestamp())}.txt"
    local_path = os.path.join(local_dir, fname)
    try:
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(text)
        return local_path
    except Exception:
        return ""


def _pull_screenshot(serial: str, remote_path: str, platform: str, keyword_id: int) -> str:
    """ADB-pull a phone-side screenshot to local audit_results/<Platform>/.
    Returns the local path written, or empty string on failure."""
    if not remote_path:
        return ""
    plat_dir_map = {"chatgpt": "ChatGPT", "gemini": "Gemini", "perplexity": "Perplexity"}
    plat_dir = plat_dir_map.get(platform.lower(), platform)
    local_dir = os.path.join(AUDIT_RESULTS_DIR, plat_dir)
    os.makedirs(local_dir, exist_ok=True)
    fname = f"kw{keyword_id}_{platform.lower()}_{int(datetime.now(timezone.utc).timestamp())}.png"
    local_path = os.path.join(local_dir, fname)
    try:
        r = subprocess.run(
            ["adb", "-s", serial, "pull", remote_path, local_path],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and os.path.exists(local_path):
            return local_path
    except Exception:
        pass
    return ""

# Per-job gost listener port pool (50 slots, even ports).
_GOST_PORTS = list(range(16001, 16101, 2))
_gost_lock = threading.Lock()
_gost_avail = list(_GOST_PORTS)
_gost_seq = itertools.count(1)

# Resolved Decodo exit IP per serial (best-effort, written after tunnel up).
_resolved_proxy_ip: dict[str, str] = {}


def _acquire_gost_port() -> int:
    with _gost_lock:
        if not _gost_avail:
            raise RuntimeError("no free gost port — too many concurrent audits")
        return _gost_avail.pop(0)


def _release_gost_port(p: int) -> None:
    with _gost_lock:
        _gost_avail.append(p)


def _http_port_for_serial(serial: str) -> int:
    """Deterministic per-serial local port. Use the DEVICES index (0-9) for known
    phones — guarantees uniqueness. Hash fallback for any serial not in DEVICES."""
    for i, entry in enumerate(DEVICES):
        if entry[1] == serial:
            return 19000 + i
    return 19000 + int(hashlib.md5(serial.encode()).hexdigest(), 16) % 100


def _adb(serial: str, *args: str, timeout: float = 10) -> subprocess.CompletedProcess:
    """Run an adb command, quoting the serial properly."""
    cmd = ["adb", "-s", serial] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _wait_tunnel(serial: str, max_attempts: int = 15) -> bool:
    """Poll for tun0 UP — needed before HTTP traffic can route through proxy."""
    import time

    for _ in range(max_attempts):
        r = _adb(serial, "shell", "ifconfig", "tun0", timeout=5)
        if "UP" in r.stdout and "inet" in r.stdout:
            return True
        time.sleep(2)
    return False


# ── catalog lookup ──

def _find_catalog_entry(keyword_id: int) -> dict[str, Any] | None:
    try:
        with open(AUDIT_CLIENTS_JSON) as f:
            catalog = json.load(f)
    except Exception:
        return None
    for entry in catalog:
        for kw in entry.get("keywords", []):
            if isinstance(kw, dict) and kw.get("keyword_id") == keyword_id:
                return entry
    return None


def _keyword_text(entry: dict, keyword_id: int) -> str:
    for kw in entry.get("keywords", []):
        if kw.get("keyword_id") == keyword_id:
            return kw.get("keyword", "")
    return ""


# ── HTTP audit call ──

AUDIT_HTTP_TIMEOUT_S = 360  # caps a single platform call (120s wait_gen + buffer)


def _post_audit(local_port: int, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{local_port}/session",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AUDIT_HTTP_TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Phone returns 500 when result.status=="error" — body still has the JSON
        # with the actual error message + per-platform steps. Don't lose it.
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"status": "error", "error": f"HTTP {e.code} (no body)"}


def _classify(response: dict, platform: str) -> tuple[str, str, str, str, str]:
    """Map HTTP response → (status, rank_position, rank_total, rank_context, screenshot_path).

    Statuses align with audit.py's classifier:
      - success     — got rank_position > 0
      - no_rank     — completed but no rank line in response
      - flow_failed — generation timeout / popup miss
      - error       — exception during flow
    """
    plats = response.get("platforms", {})
    pr = plats.get(platform.lower()) or plats.get(platform) or {}
    pos = pr.get("ranking_position") or response.get("ranking_position") or 0
    total = pr.get("ranking_total") or response.get("ranking_total") or ""
    pr_status = pr.get("status") or response.get("status", "")
    pr_err = pr.get("error") or response.get("error") or ""
    ss_path = pr.get("screenshot_path", "")

    if pr_status == "completed" and pos and int(pos) > 0:
        return ("success", str(pos), str(total), f"[RANK: {pos}/{total}]", ss_path)
    if pr_status == "completed":
        return ("no_rank", "", "", "", ss_path)
    if "generation timeout" in pr_err.lower() or "wait_generation" in pr_err.lower():
        return ("flow_failed", "", "", "", ss_path)
    return ("error", "", "", "", ss_path)


# ── job spec ──

def build_audit_dispatch_job(job_record: dict) -> dict:
    """Project Solace JobRecord onto local dispatcher fields. Same shape as the
    subprocess dispatcher so the consumer doesn't change."""
    campaign = job_record.get("campaign") or {}
    business = campaign.get("business") or {}
    client = business.get("client") or {}
    address = campaign.get("address") or {}
    # Orchestrator nests keyword under detail.keyword; legacy publishers used top-level.
    keyword = job_record.get("keyword") or (job_record.get("detail") or {}).get("keyword") or {}
    # Orchestrator's BusinessRecord.gmb is UrlRecord{id, name, type}; legacy used flat gmbUrl/bizUrl.
    gmb_obj = business.get("gmb")
    biz_url = (
        (gmb_obj.get("name") if isinstance(gmb_obj, dict) else None)
        or business.get("gmbUrl")
        or business.get("bizUrl")
        or ""
    )
    return {
        "client_id": client.get("clientId", "") or client.get("id", ""),
        "keyword_id": keyword.get("id"),
        "campaign_id": campaign.get("id", ""),
        "campaign_name": business.get("businessName", ""),
        "biz_name": business.get("businessName", ""),
        "biz_url": biz_url,
        "city": address.get("city", ""),
        "state": address.get("stateCode") or address.get("state") or "",
        "keyword": keyword.get("name", ""),
        "mode": (job_record.get("type") or "RANKING").lower(),
    }


# ── main dispatcher ──

ACQUIRE_TIMEOUT_S = 600


def dispatch_audit_job(
    job: dict,
    platform: str,
    csv_path: str | None = None,
    acquire_timeout: float | None = ACQUIRE_TIMEOUT_S,
) -> dict:
    """Run one (job, platform) via HTTP to the device-agent app.

    Returns a CSV row dict (same schema as the subprocess dispatcher).
    """
    POOL.setup_forwards()
    device_idx = POOL.acquire(timeout=acquire_timeout)
    if device_idx is None:
        row = _err_row(job, platform, "device-?", "device_pool_timeout: no idle device")
        if csv_path:
            append_row(csv_path, row)
        return row

    device_label, serial = DEVICES[device_idx]
    keyword_id = job.get("keyword_id")
    if keyword_id is None:
        POOL.release(device_idx)
        row = _err_row(job, platform, device_label, "missing keyword_id in job spec")
        if csv_path:
            append_row(csv_path, row)
        return row

    entry = _find_catalog_entry(int(keyword_id))
    if entry is None:
        # Synthesize a catalog entry from the JobRecord-derived job. The
        # orchestrator's JobRecord already carries biz_name/biz_url/city/state
        # so the static clients_audit_targets.json snapshot isn't required.
        entry = {
            "client_id": job.get("client_id", ""),
            "biz_name": job.get("biz_name", ""),
            "biz_url": job.get("biz_url", ""),
            "city": job.get("city", ""),
            "state": job.get("state", ""),
            "keywords": [{"keyword_id": int(keyword_id), "keyword": job.get("keyword", "")}],
            "proxy": {"zip": "", "country": "us", "session_duration": 30},
        }

    # Start gost
    seq = next(_gost_seq)
    gost_key = f"audit-{seq}"
    gost_port = _acquire_gost_port()
    assigned_zip = (entry.get("proxy") or {}).get("zip") or "10001"
    state_code = entry.get("state", "")
    # Resolve zip: broken zips → state's known-good (distributes load, keeps
    # same-state geo). See _resolve_zip for full precedence.
    biz_zip, zip_note = _resolve_zip(assigned_zip, state_code)
    if biz_zip != assigned_zip:
        print(
            f"  [zip-cache] assigned={assigned_zip} → using={biz_zip or '(region-only)'}"
            f" ({zip_note})",
            flush=True,
        )
    gost = GostManager(
        [{
            "device_id": gost_key, "zip": biz_zip, "state": state_code,
            "country": "us", "session_duration": 30,
        }],
        base_port=gost_port,
    )
    gost.start(wait_seconds=2.0)

    http_port = _http_port_for_serial(serial)
    started = datetime.now(timezone.utc)
    forward_set = False

    def _setup_and_post() -> dict:
        """Bring socksdroid + GPS + forwarding online then POST the audit.
        Returns the parsed HTTP response. Caller decides whether to retry."""
        socksdroid_connect(serial, gost_port)
        time.sleep(3)  # let VPN stabilise — matches rolling pre-tunnel pause
        if not _wait_tunnel(serial):
            raise RuntimeError("socksdroid tun0 never came up")
        # Capture resolved Decodo exit IP via Mac-side curl through the gost SOCKS5
        # listener. Lightweight (~1-2s); does NOT touch the phone/Chrome CDP path
        # so it can't trigger the parallel-CDP hang that AEO_SKIP_PREFLIGHT guards
        # against. Best-effort — failure here doesn't block the audit.
        try:
            resolved_ip = subprocess.run(
                ["curl", "-s", "--max-time", "5", "--socks5", f"127.0.0.1:{gost_port}", "https://ifconfig.me"],
                capture_output=True, text=True, timeout=8,
            ).stdout.strip()
            if resolved_ip and len(resolved_ip) < 64:
                _resolved_proxy_ip[serial] = resolved_ip
        except Exception:
            pass
        # IP warmup — mimic wave's implicit settle time without curl probes.
        # Cold Decodo IPs benefit from a pure-sleep pause before HTTPS fires;
        # ports the rolling fix (run_rolling_test.py 2026-05-16) to audit. Zero
        # traffic during these 60s, so no router/ISP load spike.
        time.sleep(60)
        zc = (entry.get("proxy") or {}).get("zip", "") or ""
        ll = _zip_to_latlng(zc)
        if ll:
            try:
                mock_location(serial, ll[0], ll[1])
            except Exception:
                pass
        tzn = _STATE_TZ.get(entry.get("state", "").upper())
        if tzn:
            try:
                set_timezone(serial, tzn)
            except Exception:
                pass
        _adb(serial, "forward", f"tcp:{http_port}", "tcp:8765", timeout=5)
        body = {
            "type": "audit",
            "bizName": entry["biz_name"],
            "bizUrl": entry.get("biz_url", ""),
            "city": entry.get("city", ""),
            "state": entry.get("state", ""),
            "keyword": _keyword_text(entry, int(keyword_id)),
            "platform": platform.lower(),
        }
        return _post_audit(http_port, body)

    try:
        forward_set = True  # _setup_and_post installs the forward
        response = _setup_and_post()

        # Retry once with a fresh Decodo session if the proxy IP is the suspect.
        # Trigger cases (all empirically known to recover on second IP):
        # - 'proxy_unreachable' = preflight (ifconfig.me) failed → dead proxy
        # - 'navigate' in error = page didn't render input field after reload
        # - 'input failed' = page loaded but Kotlin couldn't find input element
        #                    (Cloudflare/popup intercepted — often clears on new IP)
        # - 'generation timeout' = AI took >120s (usually Perplexity; fresh IP
        #                          + different Decodo session_id often unblocks)
        plat_block_first = (response.get("platforms") or {}).get(platform.lower(), {})
        first_err = (plat_block_first.get("error") or "").lower()
        top_err_first = (response.get("error") or "").lower()
        combined = first_err + " " + top_err_first
        if (
            "navigate" in first_err
            or "proxy_unreachable" in combined
            or "input failed" in combined
            or "generation timeout" in combined
        ):
            if "proxy_unreachable" in combined: reason = "proxy_unreachable"
            elif "input failed" in combined: reason = "input_failed"
            elif "generation timeout" in combined: reason = "generation_timeout"
            else: reason = "navigate"
            # On retry, switch to the state's known-good zip (per probes). This
            # gives a different exit IP within the same metro area instead of
            # repeating the same broken zip or dropping to a too-broad state
            # pool. _STATE_GOOD_ZIP map is empirically validated.
            retry_zip = _STATE_GOOD_ZIP.get(state_code.upper(), _FALLBACK_GOOD_ZIP)
            print(
                f"  [retry] {reason} — dropping zip={biz_zip or '(none)'} → "
                f"state={state_code} only, rotating Decodo session",
                flush=True,
            )
            # Tear down current proxy
            try:
                socksdroid_disconnect(serial)
            except Exception:
                pass
            try:
                gost.stop()
            except Exception:
                pass
            # New gost with no zip (state-only fallback) and fresh session_id
            gost = GostManager(
                [{
                    "device_id": gost_key, "zip": retry_zip, "state": state_code,
                    "country": "us", "session_duration": 30,
                }],
                base_port=gost_port,
            )
            gost.start(wait_seconds=2.0)
            response = _setup_and_post()
            # Track what we actually used so the CSV row reflects reality
            biz_zip = retry_zip

        # 4. Classify + build row
        duration_s = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
        status, rank_pos, rank_total, rank_ctx, ss_remote = _classify(response, platform)
        ss_local = _pull_screenshot(serial, ss_remote, platform, int(keyword_id))
        # Persist full LLM response text to a .txt file alongside the screenshot
        # for archival, BUT the DB column gets the actual text blob (not the path).
        resp_text_blob = (response.get("platforms") or {}).get(platform.lower(), {}).get("response_text", "")
        response_text_path = _write_response_text(resp_text_blob, platform, int(keyword_id))

        # Capture per-platform error + last few steps for diagnostics. Top-level
        # response.error is often empty when a specific platform fails — the real
        # signal is in platforms[platform].error and the steps array.
        plat_block = (response.get("platforms") or {}).get(platform.lower(), {})
        plat_err = plat_block.get("error") or response.get("error") or ""
        # The steps array lives in response.step_log (response.steps is just a count).
        # Pull the last 3 lines tagged for our platform to expose which step failed.
        steps = response.get("step_log") or []
        plat_tag = f"[{platform.lower()}]"
        if isinstance(steps, list):
            plat_steps = [s for s in steps if isinstance(s, str) and s.startswith(plat_tag)]
        else:
            plat_steps = []
        step_tail = " | ".join(plat_steps[-3:]) if plat_steps else ""
        diag = (str(plat_err) + (" | " if plat_err and step_tail else "") + step_tail)[:200]

        # Resolve proxy_ip: prefer phone-reported (preflight), fall back to the
        # Mac-side curl capture from before tunnel warmup, then sentinel.
        raw_proxy_ip = (response.get("proxy_ip") or "").strip()
        if raw_proxy_ip:
            proxy_ip_val = raw_proxy_ip
        elif _resolved_proxy_ip.get(serial):
            proxy_ip_val = _resolved_proxy_ip[serial]
        elif "proxy_unreachable" in diag.lower():
            proxy_ip_val = "preflight_failed"
        else:
            proxy_ip_val = "none"

        row = {
            "timestamp": started.strftime("%Y-%m-%d %H:%M:%S"),
            "client_id": entry.get("client_id") or job.get("client_id", ""),
            "biz_name": entry["biz_name"],
            "campaign_id": job.get("campaign_id", ""),
            "campaign_name": entry["biz_name"],
            "keyword": _keyword_text(entry, int(keyword_id)),
            "platform": platform,
            "mode": "agent_http",
            "device": device_label,
            "status": status,
            "duration_s": duration_s,
            "rank_position": rank_pos,
            "rank_total": rank_total,
            "mentioned": "yes" if rank_pos else "",
            "rank_context": rank_ctx,
            "screenshot": ss_local,
            "response_text": resp_text_blob,
            "response_text_path": response_text_path,
            # Only populate error on non-success — on success the step trace
            # belongs in a separate diagnostics field, not in the user-visible
            # error column that AEOAdmin reads.
            "error": diag if status != "success" else "",
            "proxy_ip": proxy_ip_val,
            "proxy_city": entry.get("city", ""),
            "proxy_region": entry.get("state", ""),
            "proxy_zip": biz_zip or "(state-only)",
            "prompt": (response.get("prompt") or "")[:1000],
            "variant_id": "",
        }
        if csv_path:
            append_row(csv_path, row)
        return row
    except Exception as e:
        duration_s = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
        row = _err_row(
            job, platform, device_label,
            f"{type(e).__name__}: {e}",
        )
        row["duration_s"] = duration_s
        if csv_path:
            append_row(csv_path, row)
        return row
    finally:
        if forward_set:
            try:
                _adb(serial, "forward", "--remove", f"tcp:{http_port}", timeout=5)
            except Exception:
                pass
        try:
            socksdroid_disconnect(serial)
        except Exception:
            pass
        try:
            gost.stop()
        except Exception:
            pass
        _release_gost_port(gost_port)
        POOL.release(device_idx)


# ── CSV writer (shared with subprocess dispatcher) ──

CSV_FIELDS = [
    "timestamp", "client_id", "biz_name", "campaign_id", "campaign_name",
    "keyword", "platform", "mode", "device", "status", "duration_s",
    "rank_position", "rank_total", "mentioned", "rank_context",
    "screenshot", "response_text", "error",
    "proxy_ip", "proxy_city", "proxy_region", "proxy_zip",
    "prompt", "variant_id",
]
_csv_lock = threading.Lock()


def append_row(csv_path: str, row: dict) -> None:
    write_header = not os.path.exists(csv_path)
    with _csv_lock:
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            if write_header:
                w.writeheader()
            w.writerow(row)


def _err_row(job: dict, platform: str, device_label: str, msg: str) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "client_id": job.get("client_id", ""),
        "biz_name": job.get("biz_name", ""),
        "campaign_id": job.get("campaign_id", ""),
        "campaign_name": job.get("campaign_name", ""),
        "keyword": job.get("keyword", ""),
        "platform": platform,
        "mode": "agent_http",
        "device": device_label,
        "status": "error",
        "duration_s": 0,
        "rank_position": "",
        "rank_total": "",
        "mentioned": "",
        "rank_context": "",
        "screenshot": "",
        "response_text": "",
        "error": msg[:200],
        "proxy_ip": "",
        "proxy_city": "",
        "proxy_region": "",
        "proxy_zip": "",
        "prompt": "",
        "variant_id": "",
    }
