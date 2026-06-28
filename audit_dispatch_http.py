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
import re
import shlex
import subprocess
import sys
import threading
import time
import base64
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pathlib import Path

from run_with_proxy import (
    DEVICES, socksdroid_connect, socksdroid_disconnect, mock_location, set_timezone,
    USE_SNI_RELAY, _relay_start,
)
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
    # ID added 2026-05-26: Lapwai 83540 (Nez Perce Traditions Gift Shop) has zero
    # Decodo coverage (0/3 SOCKS5 'network unreachable'). Lewiston 83501 probes 3/3
    # with residential exits (96.19.x, 152.37.x, 74.118.x) and is ~30 mi from
    # Lapwai — close enough that MaxMind city-geo for the ID zip pool resolves to
    # the same regional cluster the LLM will see. Without this, ID businesses
    # fell through to the NYC fallback and got audited from a New York IP.
    "ID": "83501",
    # HI added 2026-05-26 PM: Learn Cpr Save Lives (Honolulu) just landed 12/19
    # rows in the main-19 ranking run, ALL routed HI/10001 (NYC) — same NYC
    # fallback bug class as ID. Honolulu 96813 probes 3/3 with local residential
    # exits (66.162.x Hawaiian Telcom, 72.235.x Spectrum, 141.239.x).
    "HI": "96813",
    "IL": "60601", "IN": "46202", "KY": "40422", "MD": "21701", "MS": "38103",
    "NC": "28303", "NJ": "08736", "NY": "10001", "OH": "34200", "PA": "19102",
    "RI": "02904", "TN": "37402", "TX": "76016", "UT": "84041", "VA": "24502",
    "WA": "98115",
    # Added 2026-06-12: city/state-only campaigns (no zip) in states absent from the
    # map were silently routing to the NYC fallback (Nutydes/SC, Mcguire/NV in the
    # Jun-12 initial-ranking run). Filled the remaining US states with a metro zip so
    # state-level geo lands in-region instead of New York.
    "AL": "35203", "AK": "99501", "AR": "72201", "CT": "06103", "DC": "20001",
    "DE": "19801", "IA": "50309", "KS": "67202", "LA": "70112", "MA": "02108",
    "ME": "04101", "MI": "48226", "MN": "55401", "MO": "63101", "MT": "59101",
    "ND": "58102", "NE": "68102", "NH": "03101", "NM": "87101", "NV": "89101",
    "OK": "73102", "OR": "97201", "SC": "29577", "SD": "57104", "VT": "05401",
    "WI": "53202", "WV": "25301", "WY": "82001",
}
_FALLBACK_GOOD_ZIP = "10001"  # used when state has no entry above

# State values arrive as either 2-letter codes ("AZ") or full names ("Arizona").
# _STATE_GOOD_ZIP is keyed by 2-letter codes, so normalize before lookups —
# otherwise "Arizona" misses and silently falls back to NY 10001 (wrong geo).
_US_STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def _norm_state(state: str) -> str:
    """Normalize a state value to its 2-letter USPS code. Accepts 'AZ' or 'Arizona'."""
    s = (state or "").strip()
    if len(s) == 2:
        return s.upper()
    return _US_STATE_ABBR.get(s.lower(), s.upper())

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
        good = _STATE_GOOD_ZIP.get(_norm_state(state), _FALLBACK_GOOD_ZIP)
        return good, f"empty_zip_to_{state}_known_good_{good}"

    if assigned_zip in _BROKEN_ZIP_OVERRIDE:
        good = _STATE_GOOD_ZIP.get(_norm_state(state), _FALLBACK_GOOD_ZIP)
        return good, f"override_{state}_to_{good}"

    info = _ZIP_CACHE.get(assigned_zip)
    if not info:
        return assigned_zip, "uncached"
    nearest = (info.get("nearest_supported_zip") or "").strip()
    if info.get("supported") is False:
        if nearest and nearest != assigned_zip:
            return nearest, f"fallback_to_{nearest}"
        good = _STATE_GOOD_ZIP.get(_norm_state(state), _FALLBACK_GOOD_ZIP)
        return good, f"unsupported_{state}_to_{good}"
    return assigned_zip, "cached_ok"


# city+state → representative zip, so a business with no zip of its own gets
# audited from its OWN city instead of the state's single default zip (which
# routed e.g. a Sacramento business through Beverly Hills 90210). Cached per run.
_CITY_ZIP_CACHE: dict[tuple[str, str], str] = {}


def _city_name_variants(city: str) -> list[str]:
    """Candidate spellings to try against zippopotam, in order. Covers common
    abbreviations (Ft.→Fort, St.→Saint, Mt.→Mount) and hyphenated names
    (zippopotam wants 'Opa Locka', not 'Opa-locka')."""
    base = city.strip()
    variants = [base]
    abbr = {"ft.": "Fort", "ft": "Fort", "st.": "Saint", "mt.": "Mount"}
    head, _, rest = base.partition(" ")
    if rest and head.lower() in abbr:
        variants.append(f"{abbr[head.lower()]} {rest}")
    if "-" in base:
        variants.append(base.replace("-", " "))
    # de-dup preserving order
    seen: set[str] = set()
    return [v for v in variants if not (v.lower() in seen or seen.add(v.lower()))]


def _city_to_zip(city: str, state: str) -> str:
    """Resolve a city+state to one of its zips via zippopotam. Prefers a zip
    Decodo is known to serve (per _ZIP_CACHE); else the first listed. Returns
    '' when the city can't be resolved, so the caller falls back to state-good."""
    code = _norm_state(state)
    if not city or not code:
        return ""
    key = (city.strip().lower(), code)
    if key in _CITY_ZIP_CACHE:
        return _CITY_ZIP_CACHE[key]
    result = ""
    for variant in _city_name_variants(city):
        try:
            url = (
                f"https://api.zippopotam.us/us/{urllib.parse.quote(code)}"
                f"/{urllib.parse.quote(variant)}"
            )
            with urllib.request.urlopen(url, timeout=4) as r:
                data = json.loads(r.read())
        except Exception:
            continue
        zips = [p.get("post code", "") for p in data.get("places", []) if p.get("post code")]
        if not zips:
            continue
        supported = [z for z in zips if (_ZIP_CACHE.get(z) or {}).get("supported")]
        result = (supported or zips)[0]
        break
    _CITY_ZIP_CACHE[key] = result
    return result


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


_PHONE_WIFI_IP: dict[str, str] = {}


def _phone_wifi_ip(serial: str) -> str | None:
    """Look up cached WiFi IP for a serial; on first miss hit /health via adb-forward.

    Phase 1 of the device-agent-native migration. Once the Mac-side roster comes
    from MQTT heartbeats (Phase 4) this cache is replaced by that subscriber.
    """
    if serial in _PHONE_WIFI_IP:
        return _PHONE_WIFI_IP[serial]
    # First-time lookup: use the existing adb-forward HTTP tunnel to learn the IP.
    local_port = _http_port_for_serial(serial)
    try:
        with urllib.request.urlopen(f"http://localhost:{local_port}/health", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ip = (data.get("wifiIp") or "").strip()
        if ip:
            _PHONE_WIFI_IP[serial] = ip
            return ip
    except Exception:
        pass
    return None


def _fetch_screenshot_via_wifi(serial: str, remote_path: str, local_path: str) -> bool:
    """HTTP GET /screenshot?path=<encoded> directly from the phone over WiFi.

    Replacement for `adb pull` when USE_DIRECT_WIFI=1. Falls through to caller's
    adb-pull retry on failure so the migration is reversible.
    """
    ip = _phone_wifi_ip(serial)
    if not ip:
        return False
    encoded = urllib.parse.quote(remote_path, safe="")
    url = f"http://{ip}:8765/screenshot?path={encoded}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            if resp.status != 200:
                return False
            with open(local_path, "wb") as f:
                f.write(resp.read())
        return os.path.exists(local_path) and os.path.getsize(local_path) > 0
    except Exception:
        return False


def _pull_screenshot(serial: str, remote_path: str, platform: str, keyword_id: int) -> str:
    """Fetch a phone-side screenshot to local audit_results/<Platform>/.

    Default path: `adb pull`. When USE_DIRECT_WIFI=1 in the env, first tries
    HTTP GET /screenshot via the phone's WiFi IP (Phase 1 of the device-agent-
    native migration), then falls back to adb on failure so the migration is
    safely reversible per-job.
    Returns the local path written, or empty string on failure."""
    if not remote_path:
        return ""
    plat_dir_map = {"chatgpt": "ChatGPT", "gemini": "Gemini", "perplexity": "Perplexity"}
    plat_dir = plat_dir_map.get(platform.lower(), platform)
    date_dir = datetime.now().strftime("%Y-%m-%d")
    local_dir = os.path.join(AUDIT_RESULTS_DIR, date_dir, plat_dir)
    os.makedirs(local_dir, exist_ok=True)
    fname = f"kw{keyword_id}_{platform.lower()}_{int(datetime.now(timezone.utc).timestamp())}.png"
    local_path = os.path.join(local_dir, fname)

    if os.environ.get("USE_DIRECT_WIFI") == "1":
        if _fetch_screenshot_via_wifi(serial, remote_path, local_path):
            return local_path
        # fall through to adb on miss — no log spam, just retry the proven path

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


_OCR_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "ocr_vision")
_OCR_WARNED = False
# Answer markers a properly-rendered ranking screenshot must show. The prompt asks
# for "[RANK: x/y]" + "Google Maps: yes/no" per business, so a real answer always
# carries one of these; a blank page / prompt-only / login-wall does not.
_ANSWER_RE = re.compile(r"rank:\s*\d+\s*/\s*\d+|\[rank|google maps|maps:\s*(yes|no)", re.I)
_WALL_RE = re.compile(r"verify you are human|not a robot|captcha|just a moment|press & hold", re.I)


def _screenshot_has_answer(path: str) -> bool:
    """OCR a ranking screenshot and decide whether it actually shows the answer.

    Returns True if the rendered image contains answer markers (RANK / Google Maps
    / numbered business list), False if it shows only the prompt, a blank page, or
    a login/captcha wall. Fail-open: if the OCR tool is missing or errors, returns
    True so a tooling gap never blocks the audit pipeline."""
    global _OCR_WARNED
    if os.environ.get("OCR_VALIDATE_SCREENSHOT", "1") != "1":
        return True
    if not path or not os.path.exists(path) or not os.path.exists(_OCR_BIN):
        if not os.path.exists(_OCR_BIN) and not _OCR_WARNED:
            print(f"  [ocr] tool not found at {_OCR_BIN} — screenshot validation disabled", flush=True)
            _OCR_WARNED = True
        return True
    try:
        txt = subprocess.run([_OCR_BIN, path], capture_output=True, text=True, timeout=40).stdout
    except Exception:
        return True
    if _WALL_RE.search(txt):
        return False
    if _ANSWER_RE.search(txt):
        return True
    # numbered list of >=2 items with prose is also a real answer
    if len(re.findall(r"(?m)^\s*\d+[\.\)]\s+\w", txt)) >= 2 and len(txt) > 350:
        return True
    return False


def _capture_has_answer(path: str, prompt: str) -> bool:
    """Capture-mode variant of _screenshot_has_answer. CitedLogic types a verbatim
    prompt, so a real answer carries no [RANK]/Google-Maps markers — the signal is
    simply that the engine rendered substantial prose BEYOND echoing the prompt.

    Returns False only for a login/captcha wall or a near-empty / prompt-only page.
    Fail-open if the OCR tool is missing or errors (never block the pipeline)."""
    if os.environ.get("OCR_VALIDATE_SCREENSHOT", "1") != "1":
        return True
    if not path or not os.path.exists(path) or not os.path.exists(_OCR_BIN):
        return True
    try:
        txt = subprocess.run([_OCR_BIN, path], capture_output=True, text=True, timeout=40).stdout
    except Exception:
        return True
    if _WALL_RE.search(txt):
        return False
    body = (txt or "").strip()
    # Substantially more rendered text than the prompt alone = a real answer block.
    return len(body) >= max(len(prompt or "") + 60, 120)

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
    """Poll for tun0 UP AND real internet through it. tun0-up alone is NOT enough:
    a dead Decodo exit gives a tunnel with no DNS (DNS_PROBE_FINISHED_NO_INTERNET
    on the phone), so the audit page never loads -> no input field (input_failed).
    Probe a HOSTNAME (forces DNS resolution through the tunnel); two hosts so one
    blocked domain doesn't false-fail. Caller rotates the Decodo session on False."""
    import time

    for _ in range(max_attempts):
        r = _adb(serial, "shell", "ifconfig", "tun0", timeout=5)
        if "UP" in r.stdout and "inet" in r.stdout:
            r2 = _adb(serial, "shell",
                      "(nc -w 4 www.google.com 443 </dev/null >/dev/null 2>&1 || "
                      "nc -w 4 chatgpt.com 443 </dev/null >/dev/null 2>&1) && echo OK",
                      timeout=12)
            if "OK" in r2.stdout:
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

AUDIT_HTTP_TIMEOUT_S = 420  # caps a single platform call (240s wait_gen [v0.9.23] + ~60s load + ~40s capture + buffer)
# Per-request generation-wait for ranking audits. The app default is 240s (good
# for the daily), but for high-throughput ranking across all phones that makes
# every flaky attempt hold its gost/Decodo session ~2x longer -> session
# contention + glacial throughput. 150s covers real generation without that.
AUDIT_GEN_TIMEOUT_SEC = int(os.environ.get("AUDIT_GEN_TIMEOUT_SEC", "150"))
# Skip the Mac-side preflight exit-IP curl (best-effort, only populates proxy_ip).
# Under fleet-wide ranking it adds a 2nd Decodo session + a 15s timeout per job,
# which is the main source of concurrent-session contention (preflight rc=28).
_SKIP_PREFLIGHT = os.environ.get("AEO_SKIP_PREFLIGHT") == "1"


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


def _classify(response: dict, platform: str) -> tuple[str, str, str, str, str, str]:
    """Map HTTP response → (status, rank_position, rank_total, rank_context, screenshot_path, screenshot_b64).

    Statuses align with audit.py's classifier:
      - success     — got rank_position > 0
      - no_rank     — completed but no rank line in response
      - flow_failed — generation timeout / popup miss
      - error       — exception during flow
    The b64 field is empty for pre-0.7.1 APKs; caller falls back to adb pull.
    """
    plats = response.get("platforms", {})
    pr = plats.get(platform.lower()) or plats.get(platform) or {}
    pos = pr.get("ranking_position") or response.get("ranking_position") or 0
    total = pr.get("ranking_total") or response.get("ranking_total") or ""
    pr_status = pr.get("status") or response.get("status", "")
    pr_err = pr.get("error") or response.get("error") or ""
    ss_path = pr.get("screenshot_path", "")
    ss_b64 = pr.get("screenshot_b64", "")

    if pr_status == "completed" and pos and int(pos) > 0:
        return ("success", str(pos), str(total), f"[RANK: {pos}/{total}]", ss_path, ss_b64)
    if pr_status == "completed":
        # Not ranked ([RANK: 0/Y]). If the answer reported a total Y, record LAST
        # place (Y+1 of Y+1) so the row carries a position everywhere — raw CSV and
        # deliverable — instead of a bare 0. Status stays no_rank so it's still
        # distinguishable from a genuine last-place rank. No Y (capture miss) →
        # leave blank for the retry/answer-gate to catch.
        if str(total).strip().isdigit() and int(total) >= 1:
            y = int(total)
            return ("no_rank", str(y + 1), str(y + 1),
                    f"[RANK: 0/{y} → last {y + 1}/{y + 1}]", ss_path, ss_b64)
        return ("no_rank", "", "", "", ss_path, ss_b64)
    if "generation timeout" in pr_err.lower() or "wait_generation" in pr_err.lower():
        return ("flow_failed", "", "", "", ss_path, ss_b64)
    return ("error", "", "", "", ss_path, ss_b64)


def _write_b64_screenshot(b64: str, platform: str, keyword_id: int) -> str:
    """Decode an inline base64 PNG into audit_results/<Platform>/kw{kid}_{platform}_{ts}.png.

    Returns the local path on success, empty string on any failure.
    """
    if not b64:
        return ""
    plat_dir_map = {"chatgpt": "ChatGPT", "gemini": "Gemini", "perplexity": "Perplexity"}
    plat_dir = plat_dir_map.get(platform.lower(), platform)
    date_dir = datetime.now().strftime("%Y-%m-%d")
    local_dir = os.path.join(AUDIT_RESULTS_DIR, date_dir, plat_dir)
    os.makedirs(local_dir, exist_ok=True)
    fname = f"kw{keyword_id}_{platform.lower()}_{int(datetime.now(timezone.utc).timestamp())}.png"
    local_path = os.path.join(local_dir, fname)
    try:
        with open(local_path, "wb") as f:
            f.write(base64.b64decode(b64))
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            return local_path
    except Exception:
        pass
    return ""


# Device chrome to crop off each frame before stitching (status+URL bar at top,
# nav/gesture bar at bottom). Tune per device via env; defaults for the 720x1600
# fleet phones. Only used in CitedLogic capture mode.
# Defaults tuned on the 720x1600 fleet phones: top = status bar + URL bar,
# bottom = the engine's input/search bar + gesture nav. Cropping these BEFORE
# stitching is essential — otherwise the fixed bars repeat in the output and
# create false overlap that collapses the stitch. Override per device via env.
_STITCH_TOP_CROP = int(os.environ.get("CL_STITCH_TOP_CROP", "150"))
_STITCH_BOTTOM_CROP = int(os.environ.get("CL_STITCH_BOTTOM_CROP", "140"))
# ChatGPT's "Ask anything" composer is taller than the search bars on the others;
# Google Maps has no bottom input bar (just the map edge / gesture nav).
_STITCH_BOTTOM_CROP_BY_PLAT = {"chatgpt": 215, "google-maps": 60}


def _write_stitched_screenshot(frames_b64: list, platform: str, keyword_id: int) -> str:
    """Decode the CitedLogic capture frames and stitch them into one tall PNG of
    the full answer. Returns the local path, or "" on failure (caller falls back
    to the single-frame screenshot)."""
    frames = [f for f in (frames_b64 or []) if f]
    if not frames:
        return ""
    plat_dir_map = {"chatgpt": "ChatGPT", "gemini": "Gemini", "perplexity": "Perplexity"}
    plat_dir = plat_dir_map.get(platform.lower(), platform)
    date_dir = datetime.now().strftime("%Y-%m-%d")
    local_dir = os.path.join(AUDIT_RESULTS_DIR, date_dir, plat_dir)
    os.makedirs(local_dir, exist_ok=True)
    ts = int(datetime.now(timezone.utc).timestamp())
    frame_paths = []
    try:
        for i, b64 in enumerate(frames):
            fp = os.path.join(local_dir, f"kw{keyword_id}_{platform.lower()}_{ts}_f{i}.png")
            with open(fp, "wb") as f:
                f.write(base64.b64decode(b64))
            frame_paths.append(fp)
        out_path = os.path.join(local_dir, f"kw{keyword_id}_{platform.lower()}_{ts}.png")
        from citedlogic_stitch import stitch_frames  # lazy: keeps PIL/numpy out of the ranking path
        bottom_crop = _STITCH_BOTTOM_CROP_BY_PLAT.get(platform.lower(), _STITCH_BOTTOM_CROP)
        stitched = stitch_frames(frame_paths, out_path,
                                 top_crop=_STITCH_TOP_CROP, bottom_crop=bottom_crop)
        return stitched or (frame_paths[0] if frame_paths else "")
    except Exception as e:
        print(f"  [stitch] failed kw{keyword_id} {platform}: {type(e).__name__}: {e}", flush=True)
        return frame_paths[0] if frame_paths else ""


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
        # New orchestrator (2026-05-24+) uses business.name; old shape used businessName.
        # solace_consumer.py:_handle_audit already does this fallback; mirroring here so the
        # synthesized entry doesn't ship empty bizName to the phone (→ phone returns 400).
        "campaign_name": business.get("businessName") or business.get("name") or "",
        "biz_name": business.get("businessName") or business.get("name") or "",
        "biz_url": biz_url,
        "city": address.get("city", ""),
        "state": address.get("stateCode") or address.get("state") or "",
        "zip": address.get("zipCode") or address.get("zip") or "",
        "keyword": keyword.get("name", ""),
        "mode": (job_record.get("type") or "RANKING").lower(),
        "targetDate": job_record.get("targetDate", ""),
    }


# ── Gemini ranking via CDP (wipe-proof) ──
# Logged-out Gemini deletes its answer ~3s after render, so the app's
# a11y/screenshot path loses the rank. CDP reads the full answer off the
# StreamGenerate network wire BEFORE the wipe (proven 2026-06-27). We reuse the
# whole audit dispatch (geo fix, Decodo proxy, GPS mock, parallelism, CSV) and
# only swap the platform query for Gemini. See memory gemini-logged-out-wipe.
GEMINI_RANK_PROMPT = (
    'List the top 10 businesses for "{kw}" in {city}, {state}. Numbered list, each '
    "with the business name and a one-line reason (only genuine results — do not pad; "
    "list fewer if fewer genuinely rank). Then DEEP-DIVE the COMPLETE ranking for this "
    "query — not just the 10 shown — and find where {biz} ({url}) genuinely falls, "
    "however deep. On its own line output [RANK: X/Y] where X is {biz}'s true position "
    "in the complete ranking (even if far beyond the top 10) and Y is the total number "
    "that rank. If {biz} does NOT genuinely rank anywhere, output [RANK: 0/Y] — never "
    "invent a position. Keep the whole response under 240 words."
)


def _gemini_cdp_rank(serial: str, device_idx: int, entry: dict, keyword_id: int) -> dict:
    """Rank one (keyword, business) on Gemini via CDP, returning a response in the
    _classify shape. Unique CDP port + result files per phone so concurrent fleet
    runs don't collide on local tcp:9222."""
    biz = entry.get("biz_name", "")
    url = entry.get("biz_url", "") or (re.sub(r"[^a-z0-9]", "", biz.lower())[:20] + ".com")
    prompt = GEMINI_RANK_PROMPT.format(
        kw=_keyword_text(entry, keyword_id), city=entry.get("city", ""),
        state=entry.get("state", ""), biz=biz, url=url)
    tag = re.sub(r"[^A-Za-z0-9]", "_", serial)[:24]
    ans_f, res_f = f"/tmp/gemini_answer_{tag}.txt", f"/tmp/gemini_result_{tag}.json"
    for f in (ans_f, res_f):
        try:
            os.remove(f)
        except OSError:
            pass
    env = {**os.environ, "GEMINI_ANSWER_FILE": ans_f, "GEMINI_RESULT_FILE": res_f,
           "CDP_PORT": str(9300 + device_idx)}
    try:
        subprocess.run(["python3", "gemini_cdp_capture.py", serial, prompt],
                       env=env, capture_output=True, timeout=AUDIT_GEN_TIMEOUT_SEC + 60)
    except subprocess.TimeoutExpired:
        return {"platforms": {"gemini": {"status": "error", "error": "generation timeout"}}}
    res = json.loads(Path(res_f).read_text()) if Path(res_f).exists() else {}
    if not res.get("captured"):
        return {"platforms": {"gemini": {"status": "error", "error": "cdp_no_capture"}}}
    pos = res.get("rank_position")
    return {"platforms": {"gemini": {
        "status": "completed",
        "ranking_position": pos if pos else 0,
        "ranking_total": res.get("rank_total") or "",
        # Archive the captured answer (carries the SWML geo string for verifying
        # the proxy landed in the right city).
        "response_text": (res.get("answer") or "")[:5000],
    }}}


# ── main dispatcher ──

ACQUIRE_TIMEOUT_S = 600


def dispatch_audit_job(
    job: dict,
    platform: str,
    csv_path: str | None = None,
    acquire_timeout: float | None = ACQUIRE_TIMEOUT_S,
    capture_prompt: str | None = None,
) -> dict:
    """Run one (job, platform) via HTTP to the device-agent app.

    Returns a CSV row dict (same schema as the subprocess dispatcher).

    When `capture_prompt` is set, runs in CitedLogic CAPTURE mode: the phone is
    sent `type=capture` and types the prompt VERBATIM (no audit template, no
    business required). All proxy / exact-GPS / retry / screenshot machinery is
    shared; only the prompt source and the OCR answer-gate differ.
    """
    # In capture mode the verbatim prompt produces free-form prose with no
    # [RANK]/Google-Maps markers, so the ranking-oriented OCR gate would wrongly
    # demote every good capture — use the capture-aware checker instead.
    _answer_ok = (
        (lambda p: _capture_has_answer(p, capture_prompt))
        if capture_prompt is not None
        else _screenshot_has_answer
    )
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
            # Use the JobRecord's parsed zip (from the business address) instead of
            # defaulting to NY 10001 — otherwise non-catalog businesses get audited
            # from the wrong geo and their ranks are meaningless. Empty zip still
            # falls back via _resolve_zip(state) below.
            "proxy": {"zip": job.get("zip", ""), "country": "us", "session_duration": 30},
        }

    # Start gost
    seq = next(_gost_seq)
    gost_key = f"audit-{seq}"
    gost_port = _acquire_gost_port()
    # Empty zip must stay empty so _resolve_zip maps it to the STATE's known-good
    # zip (city/state-only campaigns have no zip of their own). Defaulting to
    # "10001" here made _resolve_zip treat it as a valid NYC zip and skip the
    # state mapping → every zipless campaign got audited from New York. (2026-06-12)
    assigned_zip = (entry.get("proxy") or {}).get("zip") or ""
    state_code = entry.get("state", "")
    # Canadian businesses (province code, not US state) must target country-ca —
    # US zip resolution would map them to a NYC fallback IP and the rank would be
    # meaningless. Use country-only CA (no US zip).
    _CA_PROVINCES = {"ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE",
                     "NT", "YT", "NU"}
    if state_code.upper() in _CA_PROVINCES:
        country = "ca"
        biz_zip = ""
        print(f"  [geo] {state_code} is Canadian → country-ca (no US zip)", flush=True)
    else:
        country = "us"
        # Resolve zip: broken zips → state's known-good (distributes load, keeps
        # same-state geo). See _resolve_zip for full precedence.
        biz_zip, zip_note = _resolve_zip(assigned_zip, state_code)
        # If resolution collapsed to the state's single default zip (empty zip,
        # broken-zip override, or Decodo-unsupported with no nearby zip), the
        # business loses its city — a Sacramento business gets audited from
        # Beverly Hills 90210. Recover its OWN city instead: derive a city zip
        # and re-check it through the Decodo cache. Only adopt it if the city zip
        # doesn't ALSO collapse to the state default (else keep state-good).
        _STATE_DEFAULT_NOTES = ("empty_zip_to_", "override_", "unsupported_")
        if zip_note.startswith(_STATE_DEFAULT_NOTES):
            city = entry.get("city", "")
            city_zip = _city_to_zip(city, state_code)
            if city_zip:
                cz, cz_note = _resolve_zip(city_zip, state_code)
                if not cz_note.startswith(_STATE_DEFAULT_NOTES):
                    print(
                        f"  [geo] {city}, {state_code}: state-default {biz_zip} →"
                        f" city zip {cz} ({cz_note})",
                        flush=True,
                    )
                    biz_zip, zip_note = cz, f"city_{cz_note}"
        if biz_zip != assigned_zip:
            print(
                f"  [zip-cache] assigned={assigned_zip} → using={biz_zip or '(region-only)'}"
                f" ({zip_note})",
                flush=True,
            )
    gost = GostManager(
        [{
            "device_id": gost_key, "zip": biz_zip, "state": state_code,
            "country": country, "session_duration": 30,
        }],
        base_port=gost_port,
    )
    gost.start(wait_seconds=2.0)

    # SNI relay: the phone connects to the relay (gost_port+1), which recovers
    # the TLS SNI and re-dials gost BY HOSTNAME — required for mobile Decodo,
    # which rejects the phone's raw IP-CONNECT. gost stays on gost_port for the
    # Mac-side preflight curl. gost_port+1 is free (_GOST_PORTS steps by 2). The
    # relay forwards to the stable gost_port, so the retry's gost restart is
    # transparent — start once here, stop once in finally.
    relay_proc = None
    phone_port = gost_port
    if USE_SNI_RELAY:
        phone_port = gost_port + 1
        relay_proc = _relay_start(phone_port, gost_port)
        time.sleep(1)

    http_port = _http_port_for_serial(serial)
    started = datetime.now(timezone.utc)
    forward_set = False

    def _setup_and_post() -> dict:
        """Bring socksdroid + GPS + forwarding online then POST the audit.
        Returns the parsed HTTP response. Caller decides whether to retry."""
        socksdroid_connect(serial, phone_port)
        time.sleep(3)  # let VPN stabilise — matches rolling pre-tunnel pause
        if not _wait_tunnel(serial):
            # Dead tunnel (tun0 up but no DNS/internet). Return a proxy_unreachable
            # response instead of raising, so the existing rotate-Decodo-session +
            # retry path below kicks in (a fresh session usually has working DNS).
            return {"platforms": {platform.lower(): {"status": "error", "error": "proxy_unreachable"}},
                    "error": "proxy_unreachable"}
        # Capture resolved Decodo exit IP via Mac-side curl through the gost SOCKS5
        # listener. Lightweight (~1-2s); does NOT touch the phone/Chrome CDP path
        # so it can't trigger the parallel-CDP hang that AEO_SKIP_PREFLIGHT guards
        # against. Best-effort — failure here doesn't block the audit.
        # gost listener requires SOCKS5 auth (anon:anon by default in GostManager).
        # The original code omitted credentials, so every preflight silently
        # returned rc=97 "User was rejected by the SOCKS5 server" — that's why
        # proxy_ip was "none" on every row.
        if _SKIP_PREFLIGHT:
            _resolved_proxy_ip[serial] = "skipped"
        else:
            try:
                cp = subprocess.run(
                    # --socks5-hostname (remote DNS): mobile Decodo rejects the
                    # IP-CONNECT that plain --socks5 (local resolve) produces, so the
                    # preflight always returned rc=97. Matches run_with_proxy.resolve_proxy_ip.
                    ["curl", "-sS", "--max-time", "15", "--socks5-hostname",
                     f"anon:anon@127.0.0.1:{gost_port}", "https://ifconfig.me"],
                    capture_output=True, text=True, timeout=18,
                )
                resolved_ip = cp.stdout.strip()
                if resolved_ip and len(resolved_ip) < 64:
                    _resolved_proxy_ip[serial] = resolved_ip
                else:
                    print(f"  [preflight-ip] {serial} gost:{gost_port} rc={cp.returncode} "
                          f"stderr={cp.stderr.strip()[:120]!r} stdout={resolved_ip[:120]!r}", flush=True)
            except Exception as e:
                print(f"  [preflight-ip] {serial} gost:{gost_port} curl raised {type(e).__name__}: {e}", flush=True)
        # IP warmup — mimic wave's implicit settle time without curl probes.
        # Cold Decodo IPs benefit from a pure-sleep pause before HTTPS fires;
        # ports the rolling fix (run_rolling_test.py 2026-05-16) to audit. Zero
        # traffic during these 60s, so no router/ISP load spike.
        time.sleep(60)
        # Opt-in: a job may carry EXACT mock GPS (mock_lat/mock_lng) — used by the
        # CitedLogic capture path which puts the device at a precise lat/lng instead
        # of deriving it from the proxy zip. Falls back to zip-derived otherwise.
        _mlat, _mlng = job.get("mock_lat"), job.get("mock_lng")
        if _mlat is not None and _mlng is not None:
            try:
                mock_location(serial, float(_mlat), float(_mlng))
            except Exception:
                pass
        else:
            # Derive GPS from the RESOLVED zip (biz_zip), not the raw assigned
            # zip — otherwise a zip-less/overridden business mocks GPS from the
            # wrong place (or not at all) while the proxy exits elsewhere, and the
            # GPS/IP mismatch trips the platform's location check.
            ll = _zip_to_latlng(biz_zip)
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
        # Gemini: read the answer off the wire via CDP (wipe-proof) instead of the
        # app's a11y/screenshot path, which the ~3s logged-out wipe defeats. Reuses
        # the Decodo proxy + geo-fixed zip + GPS mock already set up above.
        if platform.lower() == "gemini" and capture_prompt is None:
            return _gemini_cdp_rank(serial, device_idx, entry, int(keyword_id))
        if capture_prompt is not None:
            body = {
                "type": "capture",
                "prompt": capture_prompt,
                "platform": platform.lower(),
            }
            # google-maps centers the map on these coords (/@lat,lng) so results
            # are metro-local regardless of device GPS.
            if job.get("mock_lat") is not None and job.get("mock_lng") is not None:
                body["lat"] = float(job["mock_lat"])
                body["lng"] = float(job["mock_lng"])
        else:
            body = {
                "type": "audit",
                "bizName": entry["biz_name"],
                "bizUrl": entry.get("biz_url", ""),
                "city": entry.get("city", ""),
                "state": entry.get("state", ""),
                "keyword": _keyword_text(entry, int(keyword_id)),
                "platform": platform.lower(),
                "genTimeoutSec": AUDIT_GEN_TIMEOUT_SEC,
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
            # On retry, rotate the Decodo session (fresh exit IP) but KEEP the
            # business's own city. Prefer a zip in the business's actual city
            # (a different same-city zip than the one that just failed) — only
            # fall back to the statewide default if the city can't be resolved.
            # Dropping straight to _STATE_GOOD_ZIP audited e.g. a Sacramento
            # business from Beverly Hills 90210 on every retry → false no_rank.
            _retry_city = entry.get("city", "")
            _retry_city_zip = _city_to_zip(_retry_city, state_code) if _retry_city else ""
            # Avoid re-using the exact zip that just failed; the session rotation
            # below still gives a fresh exit if the city has only one usable zip.
            if _retry_city_zip and _retry_city_zip != biz_zip:
                retry_zip = _retry_city_zip
            else:
                retry_zip = _STATE_GOOD_ZIP.get(_norm_state(state_code)) or biz_zip or _FALLBACK_GOOD_ZIP
            print(
                f"  [retry] {reason} — zip={biz_zip or '(none)'} → {retry_zip}"
                f" ({_retry_city or state_code}), rotating Decodo session",
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
            # Update biz_zip BEFORE re-setup so _setup_and_post mocks GPS from the
            # retry zip (keeps GPS/proxy in the same place); also reflects reality
            # in the CSV row.
            biz_zip = retry_zip
            response = _setup_and_post()

        # 4. Classify + build row
        duration_s = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
        status, rank_pos, rank_total, rank_ctx, ss_remote, ss_b64 = _classify(response, platform)
        # CitedLogic capture mode: stitch the multi-frame full-answer screenshot.
        # Falls back to the single frame, then adb pull. Audit mode is unchanged.
        ss_local = ""
        if capture_prompt is not None:
            _frames = (response.get("platforms") or {}).get(platform.lower(), {}).get("screenshot_frames") or []
            ss_local = _write_stitched_screenshot(_frames, platform, int(keyword_id))
        if not ss_local:
            # Prefer inline base64 (zero-adb data plane). Fall back to adb pull when
            # the phone's APK is older than 0.7.1-b64 or the b64 read failed on-device.
            ss_local = _write_b64_screenshot(ss_b64, platform, int(keyword_id))
        if not ss_local:
            ss_local = _pull_screenshot(serial, ss_remote, platform, int(keyword_id))
        # Persist full LLM response text to a .txt file alongside the screenshot
        # for archival, BUT the DB column gets the actual text blob (not the path).
        resp_text_blob = (response.get("platforms") or {}).get(platform.lower(), {}).get("response_text", "")
        response_text_path = _write_response_text(resp_text_blob, platform, int(keyword_id))

        # 4b. Inline screenshot validation. A 'success'/'no_rank' row MUST visibly
        # show the answer — OCR the screenshot, and if it's blank / prompt-only /
        # a login-captcha wall, rotate the Decodo session and re-capture ONCE. If
        # it still shows no answer, demote to a retryable status so a bad
        # screenshot is never recorded as a good result. (OCR_VALIDATE_SCREENSHOT=0
        # disables this; _screenshot_has_answer fails open if the OCR tool is gone.)
        # Gemini's logged-out chat WIPES the answer ~3s after it renders, so its
        # screenshot is expected to be blank/Deleted even when we captured the
        # ranking from the a11y tree. Success for Gemini = ranking captured, NOT a
        # valid screenshot — so skip OCR screenshot validation for it.
        if status in ("success", "no_rank") and ss_local and not _answer_ok(ss_local):
            print(f"  [ocr] no answer in screenshot kw{keyword_id} {platform} — rotating session, re-capturing", flush=True)
            try:
                socksdroid_disconnect(serial)
            except Exception:
                pass
            try:
                gost.stop()
            except Exception:
                pass
            ocr_zip = _STATE_GOOD_ZIP.get(_norm_state(state_code)) or biz_zip or _FALLBACK_GOOD_ZIP
            gost = GostManager(
                [{"device_id": gost_key, "zip": ocr_zip, "state": state_code,
                  "country": "us", "session_duration": 30}],
                base_port=gost_port,
            )
            gost.start(wait_seconds=2.0)
            response = _setup_and_post()
            status, rank_pos, rank_total, rank_ctx, ss_remote, ss_b64 = _classify(response, platform)
            ss_local = ""
            if capture_prompt is not None:
                _frames = (response.get("platforms") or {}).get(platform.lower(), {}).get("screenshot_frames") or []
                ss_local = _write_stitched_screenshot(_frames, platform, int(keyword_id))
            ss_local = ss_local or _write_b64_screenshot(ss_b64, platform, int(keyword_id)) \
                or _pull_screenshot(serial, ss_remote, platform, int(keyword_id))
            resp_text_blob = (response.get("platforms") or {}).get(platform.lower(), {}).get("response_text", "")
            response_text_path = _write_response_text(resp_text_blob, platform, int(keyword_id))
            duration_s = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
            if status in ("success", "no_rank") and (not ss_local or not _answer_ok(ss_local)):
                status = "ocr_no_answer"  # non-terminal -> outer retry loop re-runs it

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
        if relay_proc is not None and relay_proc.poll() is None:
            try:
                relay_proc.terminate(); relay_proc.wait(timeout=5)
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
    # Per-date split: insert <DATE> into the basename so each day lands in its
    # own CSV. Date comes from the row's timestamp (so retimed/historical
    # rows go to the right file) — falls back to today's local date.
    ts = (row.get("timestamp") or "")[:10]
    if not ts or len(ts) != 10:
        ts = datetime.now().strftime("%Y-%m-%d")
    dirname, basename = os.path.split(csv_path)
    name, ext = os.path.splitext(basename)
    dated_path = os.path.join(dirname, f"{name}_{ts}{ext}")

    write_header = not os.path.exists(dated_path)
    with _csv_lock:
        with open(dated_path, "a", newline="") as f:
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
