#!/usr/bin/env python3
"""SuperProxy proxy lifecycle — replaces gost+socksdroid for the Decodo Mobile pivot.

The old chain was: Mac gost listener -> socksdroid VPN on phone -> Decodo residential.
The new chain is: the SuperProxy Android app (com.scheler.superproxy) runs a system
VPN that dials Decodo Mobile directly, and the device-agent app
(com.farm.device.android.device.agent, HTTP :7070) drives SuperProxy's UI over
Accessibility via three endpoints: POST /superproxy (save profile),
/superproxy/start, /superproxy/stop.

Why this module exists / what it does differently from the app's own endpoints:

  * /superproxy/stop is a NO-OP on the fleet — it calls DevicePolicyManager
    .clearApplicationUserData(), which needs device-owner privilege the phones
    don't have. So "stop" here is `adb shell pm clear com.scheler.superproxy`
    (adb has the privilege the app lacks). Verified 2026-05-28.
  * SuperProxy is ad-supported. The interstitial fires on the FIRST /start after
    a fresh app state and is NOT handled by the device-agent's accessibility
    scenario. AdMob frequency-caps it, so the recovery is: clear -> save -> start,
    retried — it lands ad-free within a couple of tries.
  * The first /start per phone pops Android's VPN-consent dialog
    (com.android.vpndialogs). Subsequent starts are silent.

Public surface:
    setup(serial, device_idx, ...)  -> (ok: bool, info: dict)
    teardown(serial)
    egress_ip(serial)               -> str (best-effort; currently "")

Reuses `run` from run_with_proxy so adb invocation + serial-quoting stay identical.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Any

from run_with_proxy import run, rsid

# ── Config (env-overridable; defaults match the 2026-05-28 single-phone test) ──
SUPERPROXY_HOST = os.environ.get("SUPERPROXY_HOST", "gate.decodo.com")
SUPERPROXY_PORT = int(os.environ.get("SUPERPROXY_PORT", "7000"))
# Base sub-user WITHOUT the user- prefix or geo suffix; build_username() composes it.
SUPERPROXY_USER = os.environ.get("SUPERPROXY_USER", "spx491gvtx")
SUPERPROXY_PASS = os.environ.get("SUPERPROXY_PASS", "")
SUPERPROXY_COUNTRY = os.environ.get("SUPERPROXY_COUNTRY", "us")
# Mobile session-stickiness params are UNVERIFIED for the mobile tier; off by default.
SUPERPROXY_STICKY = os.environ.get("SUPERPROXY_STICKY", "0") == "1"
SUPERPROXY_DURATION = int(os.environ.get("SUPERPROXY_DURATION", "30"))

SUPERPROXY_PKG = "com.scheler.superproxy"
AGENT_PKG = "com.farm.device.android.device.agent"
AGENT_REMOTE_PORT = 7070               # device-agent Ktor server (gradle.properties: deviceAgent.serverPort)
AGENT_LOCAL_BASE = 17070               # local adb-forward base; +device_idx. Distinct from old agent's 8765.

# How long the SuperProxy fill scenario + tunnel bring-up may take.
SAVE_TIMEOUT_S = 30
START_SETTLE_S = 5
TUN_WAIT_TICKS = 12
TUN_WAIT_INTERVAL_S = 2
MAX_AD_RETRIES = int(os.environ.get("SUPERPROXY_MAX_AD_RETRIES", "4"))


def agent_local_port(device_idx: int) -> int:
    return AGENT_LOCAL_BASE + device_idx


def build_username(country: str | None = None, session_id: str | None = None) -> str:
    """Compose the Decodo Mobile username typed verbatim into SuperProxy.

    Validated forms (2026-05-28):
        raw 'spx491gvtx'                  -> random geo (landed in Sri Lanka)
        'user-spx491gvtx-country-us'      -> US (Verizon, incl. AS6167 cellular)
    Sticky-session suffix is appended only when SUPERPROXY_STICKY=1 (mobile-tier
    support for it is unverified).
    """
    country = (country or SUPERPROXY_COUNTRY or "").lower()
    parts = [f"user-{SUPERPROXY_USER}"]
    if country:
        parts.append(f"country-{country}")
    if SUPERPROXY_STICKY:
        sid = session_id or rsid()
        parts.append(f"session-{sid}")
        parts.append(f"sessionduration-{SUPERPROXY_DURATION}")
    return "-".join(parts)


# ── adb / agent HTTP primitives ───────────────────────────────────────────────
def _adb(serial: str, shell_cmd: str, timeout: int = 15):
    return run(f'adb -s "{serial}" shell {shell_cmd}', timeout)


def _ensure_forward(serial: str, local_port: int) -> None:
    run(f'adb -s "{serial}" forward tcp:{local_port} tcp:{AGENT_REMOTE_PORT}', 10)


def _agent_request(local_port: int, path: str, body: dict | None = None,
                   timeout: int = SAVE_TIMEOUT_S) -> tuple[int, dict]:
    """POST (or GET when body is None) to the device-agent. Returns (http_code, json|{}).

    Unlike run_with_proxy.http_post, this surfaces the HTTP status code and never
    masks failures as a fake {"status":"error"} — the caller needs the real code
    (202 vs 503) and the real DTO (status:true/false)."""
    url = f"http://localhost:{local_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, (json.loads(raw) if raw else {})
            except json.JSONDecodeError:
                return r.status, {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"_error": f"{type(e).__name__}: {e}"}


def _foreground(serial: str) -> str:
    r = _adb(serial, "dumpsys activity activities", 8)
    for ln in r.stdout.splitlines():
        if "topResumedActivity" in ln:
            return ln.strip()
    return ""


def _is_ad(fg: str) -> bool:
    return "AdActivity" in fg or "com.google.android.gms.ads" in fg


def _is_vpn_dialog(fg: str) -> bool:
    return "com.android.vpndialogs" in fg


def _tun0_ip(serial: str) -> str:
    r = _adb(serial, "ip -4 addr show tun0", 6)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
    return m.group(1) if m else ""


def _wake(serial: str) -> None:
    _adb(serial, "input keyevent KEYCODE_WAKEUP", 5)
    _adb(serial, "wm dismiss-keyguard", 5)


def _tap_label(serial: str, labels: tuple[str, ...]) -> bool:
    """uiautomator-locate a clickable node whose text matches one of `labels` and
    tap it. Returns False if the dump is empty (ad webviews often expose nothing)."""
    dump = _adb(serial, "uiautomator dump /sdcard/sp_ui.xml", 8)
    if "dumped" not in dump.stdout.lower():
        return False
    xml = _adb(serial, "cat /sdcard/sp_ui.xml", 6).stdout
    want = {l.upper() for l in labels}
    for m in re.finditer(r'text="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        if m.group(1).strip().upper() in want:
            x = (int(m.group(2)) + int(m.group(4))) // 2
            y = (int(m.group(3)) + int(m.group(5))) // 2
            _adb(serial, f"input tap {x} {y}", 5)
            return True
    return False


def _dismiss_ad(serial: str) -> bool:
    """Dismiss a SuperProxy AdMob interstitial/video so the underlying Start flow
    can proceed. AdMob interstitials are webviews/SurfaceViews that uiautomator
    usually can't introspect, so the reliable lever is: wait out the countdown,
    then BACK. Guards against the video ad's click-through opening the Play Store.
    Returns True once the foreground is no longer an ad."""
    time.sleep(6)  # let the close/skip countdown elapse before acting
    for _ in range(6):
        fg = _foreground(serial)
        if "com.android.vending" in fg:          # click-through opened Play Store
            _adb(serial, "input keyevent KEYCODE_BACK", 5)
            time.sleep(1.5)
            continue
        if not _is_ad(fg):
            return True
        # Prefer an explicit skip/close control; fall back to BACK.
        if not _tap_label(serial, ("Close", "Skip", "Skip Ad", "Continue", "No thanks", "Dismiss")):
            _adb(serial, "input keyevent KEYCODE_BACK", 5)
        time.sleep(2)
    return not _is_ad(_foreground(serial))


def _accept_vpn_dialog(serial: str) -> bool:
    """Tap OK on com.android.vpndialogs.ConfirmDialog. Tries to locate the button
    via uiautomator (resolution-independent); falls back to a proportional tap."""
    dump = _adb(serial, "uiautomator dump /sdcard/sp_ui.xml", 8)
    xml = _adb(serial, "cat /sdcard/sp_ui.xml", 6).stdout if "dumped" in dump.stdout.lower() else ""
    if xml:
        # Find a clickable node whose text is OK/ALLOW and tap its bounds center.
        for m in re.finditer(r'text="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            label = m.group(1).strip().upper()
            if label in ("OK", "ALLOW", "CONNECT", "ACCEPT"):
                x = (int(m.group(2)) + int(m.group(4))) // 2
                y = (int(m.group(3)) + int(m.group(5))) // 2
                _adb(serial, f"input tap {x} {y}", 5)
                return True
    # Fallback: OK sits bottom-right of the system dialog (~0.83w, 0.64h).
    sz = _adb(serial, "wm size", 5).stdout
    m = re.search(r"(\d+)x(\d+)", sz)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        _adb(serial, f"input tap {int(w * 0.83)} {int(h * 0.64)}", 5)
        return True
    return False


# ── agent readiness ───────────────────────────────────────────────────────────
ACCESSIBILITY_SERVICE = f"{AGENT_PKG}/{AGENT_PKG}.automation.presentation.service.AutomatorAccessibilityService"


def rebind_accessibility(serial: str, device_idx: int) -> bool:
    """Force a fresh onServiceConnected by toggling the agent's accessibility
    service off/on. Recovers the command executor when it goes inert — observed
    2026-05-28: after sustained use (many pm clears) /superproxy/start returns 202
    but the async Start click stops firing, even though /health still reports
    executorConnected:true. A rebind restores it. Returns True if healthy after.

    Preserves any OTHER enabled accessibility services (e.g. the old
    com.deviceagent agent that runs the AI session) — only ensures THIS agent's
    service stays present across the toggle."""
    cur = _adb(serial, "settings get secure enabled_accessibility_services", 5).stdout.strip()
    services = [s for s in cur.split(":") if s and s != "null"]
    if ACCESSIBILITY_SERVICE not in services:
        services.append(ACCESSIBILITY_SERVICE)
    restore = ":".join(services)
    _adb(serial, 'settings put secure enabled_accessibility_services ""', 5)
    _adb(serial, "settings put secure accessibility_enabled 0", 5)
    time.sleep(2)
    _adb(serial, f'settings put secure enabled_accessibility_services "{restore}"', 5)
    _adb(serial, "settings put secure accessibility_enabled 1", 5)
    time.sleep(3)
    _adb(serial, f"am start -n {AGENT_PKG}/.MainActivity", 8)
    time.sleep(3)
    local = agent_local_port(device_idx)
    code, body = _agent_request(local, "/health", timeout=8)
    return code == 200 and bool(body.get("serverRunning")) and bool(body.get("executorConnected"))


def ensure_agent_up(serial: str, device_idx: int) -> tuple[bool, str]:
    """Forward the agent port and confirm the Ktor server + accessibility executor
    are live. Launches MainActivity (which starts ServerForegroundService) if /health
    is unreachable. Returns (ok, detail)."""
    local = agent_local_port(device_idx)
    _ensure_forward(serial, local)
    code, body = _agent_request(local, "/health", timeout=8)
    if code == 200 and body.get("serverRunning"):
        if not body.get("executorConnected"):
            return False, "server up but accessibility executor NOT connected " \
                          f"(enable {AGENT_PKG} accessibility service)"
        return True, "healthy"
    # Try to start it.
    _adb(serial, f"am start -n {AGENT_PKG}/.MainActivity", 8)
    time.sleep(4)
    code, body = _agent_request(local, "/health", timeout=8)
    if code == 200 and body.get("serverRunning") and body.get("executorConnected"):
        return True, "healthy after launch"
    return False, f"agent unhealthy (code={code} body={body})"


# ── core lifecycle ──────────────────────────────────────────────────────────--
def stop(serial: str) -> None:
    """The real 'stop' — pm clear resets SuperProxy to a clean state AND drops the
    VPN. (The app's /superproxy/stop can't do this without device-owner.)"""
    run(f'adb -s "{serial}" shell pm clear {SUPERPROXY_PKG}', 30)


teardown = stop  # alias — teardown after a job is the same clean-clear


def setup(serial: str, device_idx: int, *, country: str | None = None,
          session_id: str | None = None, max_ad_retries: int = MAX_AD_RETRIES,
          _rebound: bool = False) -> tuple[bool, dict[str, Any]]:
    """Bring up the Decodo Mobile tunnel on `serial` via SuperProxy.

    Implements the validated loop, retrying the whole save->start on an ad:
        pm clear -> POST /superproxy -> POST /superproxy/start
        -> if AdActivity: retry  -> if VPN dialog: tap OK  -> verify tun0 up

    Returns (ok, info) where info carries username, tun0 ip, attempts, and the
    last failure reason on failure."""
    if not SUPERPROXY_PASS:
        return False, {"reason": "SUPERPROXY_PASS not set"}

    local = agent_local_port(device_idx)
    up, detail = ensure_agent_up(serial, device_idx)
    if not up:
        return False, {"reason": f"agent_not_ready: {detail}"}

    username = build_username(country, session_id)
    profile = {
        "host": SUPERPROXY_HOST, "port": SUPERPROXY_PORT,
        "username": username, "password": SUPERPROXY_PASS, "status": True,
    }

    last = ""
    for attempt in range(1, max_ad_retries + 1):
        stop(serial)                       # clean state so the fill scenario sees a fresh form
        _wake(serial)
        time.sleep(1)

        code, dto = _agent_request(local, "/superproxy", profile)
        if code != 200 or not dto.get("status"):
            last = f"save_failed attempt={attempt} code={code} dto={dto}"
            continue

        code, _ = _agent_request(local, "/superproxy/start", {}, timeout=15)
        if code not in (200, 202):
            last = f"start_rejected attempt={attempt} code={code}"
            continue

        # Poll the post-start UI as a state machine: the async Start tap can land
        # on an ad (dismiss it), the VPN-consent dialog (accept it), or connect.
        # Re-tap Start once if an ad dismissal drops us back to the saved form.
        ads_seen = 0
        restarts = 0
        time.sleep(START_SETTLE_S)
        deadline_ticks = 20  # ~ up to 20*2s + dismissal time
        for _ in range(deadline_ticks):
            ip = _tun0_ip(serial)
            if ip:
                return True, {
                    "username": username, "tun0_ip": ip, "attempts": attempt,
                    "ads_dismissed": ads_seen, "egress_ip": egress_ip(serial),
                }
            fg = _foreground(serial)
            if _is_vpn_dialog(fg):
                _accept_vpn_dialog(serial)
                time.sleep(3)
                continue
            if _is_ad(fg):
                ads_seen += 1
                _dismiss_ad(serial)
                time.sleep(1)
                continue
            # Back on SuperProxy's own screen with no tunnel — the Start tap may
            # have been eaten by the ad. Re-tap Start once before giving up.
            if AGENT_PKG not in fg and SUPERPROXY_PKG in fg and restarts == 0:
                _agent_request(local, "/superproxy/start", {}, timeout=15)
                restarts += 1
            time.sleep(TUN_WAIT_INTERVAL_S)
        last = f"no_tun0 attempt={attempt} ads_seen={ads_seen}"

    # Self-heal: an all-attempts failure with the inert-click signature (no tun0,
    # no ad/dialog ever seen) means the executor wedged — rebind once and retry.
    if not _rebound:
        if rebind_accessibility(serial, device_idx):
            return setup(serial, device_idx, country=country, session_id=session_id,
                         max_ad_retries=max_ad_retries, _rebound=True)
        return False, {"reason": f"{last}; rebind failed", "username": username}

    return False, {"reason": last or "exhausted retries", "username": username}


def egress_ip(serial: str) -> str:
    """Best-effort external IP as seen THROUGH the proxy.

    TODO(superproxy): the old Mac-side `resolve_proxy_ip` (gost SOCKS curl) is
    gone — there's no Mac-side listener anymore. The phones ship no curl/wget, so
    we can't shell out an IP echo. Options to implement later:
      * drive the device-agent's /search (Chrome) to an IP-echo page and scrape, or
      * add a tiny /egress endpoint to the device-agent that does the lookup on-device.
    Returning "" for now; the daily/audit CSV records tun0_ip instead.
    """
    return ""
