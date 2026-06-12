#!/usr/bin/env python3
"""Run one SEO (Google SERP) job on a single phone through the Decodo proxy
(gost + socksdroid), rotating exit IPs and pre-checking each for Google's
"unusual traffic" reCAPTCHA before committing to the (slow) full scrape.

Strategy per attempt:
    fresh Decodo session (new IP) -> gost_start -> socksdroid_connect -> wait_tunnel
    -> PRECHECK: pm clear Chrome, load a SERP via adb, ~12s, look for captcha
       - clean  -> run the full SEO /session flow, keep result, stop
       - blocked-> tear down, next IP
Reuses the proven proxy lifecycle from run_with_proxy.py. Dummy test data only.

Mobile gateway: set SEO_PROXY_GW=mobile (+ SUPERPROXY_PASS) to point gost at Decodo
Mobile (gate.decodo.com:7000, user spx491gvtx) instead of residential — mobile IPs
are far less likely to be challenged by Google.

Env (source .env.dev first):
    set -a; source .env.dev; set +a
Usage:
    python3 seo_proxy_run.py --device-idx 0 --keyword "best coffee shop austin" \
        --target epoch.coffee --attempts 4
"""
from __future__ import annotations

import argparse
import os
import random
import string
import subprocess
import sys
import time
from pathlib import Path

import run_with_proxy as rwp
import seo_dispatch as sd

GOST_PORT = 18765
RELAY_PORT = 18764          # SocksDroid -> sni_relay (this) -> gost (GOST_PORT) -> Decodo
LOCAL_HTTP_PORT = 8766
SESSION_DURATION = 30

# SNI-rewriting relay: SocksDroid can only IP-CONNECT, but mobile Decodo rejects
# IP-CONNECT (0x02 not allowed). The relay peeks the TLS SNI and re-dials gost by
# HOSTNAME, so DNS resolves at the Decodo US exit. See docs/MOBILE_PROXY_SETUP.md.
_HERE = os.path.dirname(os.path.abspath(__file__))
RELAY_SCRIPT = os.path.join(_HERE, "sni_relay.py")
_VENV_PY = os.path.join(_HERE, ".venv", "bin", "python")
RELAY_PY_EXE = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable  # needs PySocks


def _relay_start(listen_port: int, up_port: int, up_host: str | None = None,
                 up_user: str | None = None, up_pass: str | None = None) -> subprocess.Popen:
    """Start sni_relay.py (listen_port -> up_port). With up_host set, the relay
    forwards straight to that SOCKS5 (Decodo) instead of the default local gost —
    gost's chain to Decodo MOBILE is broken (0x03) but a direct hostname-CONNECT
    works. Raise if it dies on startup."""
    env = dict(os.environ)
    if up_host:
        env["SNI_UPSTREAM_HOST"] = up_host
        env["SNI_UPSTREAM_USER"] = up_user or ""
        env["SNI_UPSTREAM_PASS"] = up_pass or ""
    log = open(f"/tmp/sni_relay_{listen_port}.log", "w")
    proc = subprocess.Popen(
        [RELAY_PY_EXE, RELAY_SCRIPT, str(listen_port), str(up_port)],
        stdout=log, stderr=subprocess.STDOUT, env=env,
    )
    time.sleep(1.5)
    if proc.poll() is not None:
        raise RuntimeError(f"sni_relay died on start — see /tmp/sni_relay_{listen_port}.log")
    return proc


def _decodo_exit_ip(host: str, port: int, user: str, pw: str) -> str | None:
    """Resolve the exit IP via a direct hostname-CONNECT (same path the relay uses)."""
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", "20", "--socks5-hostname",
             f"{host}:{port}", "-U", f"{user}:{pw}", "https://ifconfig.me"],
            capture_output=True, text=True, timeout=25).stdout.strip()
        return out or None
    except Exception:
        return None


def _sid(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _adb(serial: str, *args: str, timeout: int = 20) -> str:
    return subprocess.run(["adb", "-s", serial, *args], capture_output=True, text=True, timeout=timeout).stdout


def _gateway(gw: str) -> tuple[str, str, str, str]:
    """Return (host, port, user_prefix, password) for the chosen Decodo gateway.
    user_prefix already includes the required 'user-' prefix."""
    # Port 10001 (sticky endpoint) is the one gost's sustained SOCKS5 chain works on for the
    # phone tunnel — port 7000 (rotating) loads pages unreliably through gost.
    if gw == "mobile":
        host = os.environ.get("SUPERPROXY_HOST", "gate.decodo.com")
        port = os.environ.get("SUPERPROXY_PORT", "10001")
        user = os.environ.get("SUPERPROXY_USER", "spx491gvtx")
        pw = os.environ.get("SUPERPROXY_PASS", "")
        return host, port, f"user-{user}", pw      # -> user-spx491gvtx (Verizon/T-Mobile cellular)
    return rwp.PROXY_HOST, "10001", rwp.PROXY_USER, rwp.PROXY_PASS


def _precheck_serp(serial: str, keyword: str, settle_s: int = 13) -> str:
    """Cheaply load a SERP via adb and classify: 'clean' | 'blocked' | 'unknown'."""
    q = keyword.replace(" ", "+")
    _adb(serial, "shell", "pm", "clear", "com.android.chrome", timeout=30)
    time.sleep(1)
    _adb(serial, "shell", "am", "start", "-a", "android.intent.action.VIEW",
         "-d", f"https://www.google.com/search?q={q}", "com.android.chrome", timeout=15)
    time.sleep(settle_s)
    _adb(serial, "shell", "uiautomator", "dump", "/sdcard/pre.xml", timeout=20)
    xml = _adb(serial, "shell", "cat", "/sdcard/pre.xml", timeout=15).lower()
    if "sorry/index" in xml or "not a robot" in xml or "unusual traffic" in xml:
        return "blocked"
    if "places" in xml or "web results" in xml or "sponsored results" in xml:
        return "clean"
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="SEO job through Decodo proxy with IP rotation + captcha precheck.")
    ap.add_argument("--device-idx", type=int, default=0)
    ap.add_argument("--keyword", default="best coffee shop austin")
    ap.add_argument("--target", default="epoch.coffee")
    ap.add_argument("--out", default="/tmp/seo_proxy")
    ap.add_argument("--country", default="us")
    ap.add_argument("--attempts", type=int, default=4, help="max fresh-IP attempts to find a clean one")
    ap.add_argument("--gateway", default=os.environ.get("SEO_PROXY_GW", "residential"),
                    choices=["residential", "mobile"])
    args = ap.parse_args()

    host, port, user_prefix, password = _gateway(args.gateway)
    if not user_prefix or not password:
        print(f"ERROR: {args.gateway} gateway creds missing — source .env.dev"
              + ("; set SUPERPROXY_PASS for mobile" if args.gateway == "mobile" else ""))
        return 2

    device_id, serial = rwp.DEVICES[args.device_idx]
    print(f"[seo-proxy] {device_id} gateway={args.gateway} ({host}:{port}) attempts={args.attempts}")

    for attempt in range(1, args.attempts + 1):
        sid = _sid()
        # Sticky session: holds ONE IP for the whole flow (verified mobile = stable T-Mobile/
        # Verizon cellular IP), so a single page load doesn't hop IPs mid-request. Each ATTEMPT
        # gets a fresh sticky IP.
        spec = {"port": GOST_PORT, "sid": sid,
                "upstream_user": f"{user_prefix}-country-{args.country}-session-{sid}-sessionduration-{SESSION_DURATION}"}
        # Point gost at the chosen gateway for this attempt.
        rwp.PROXY_HOST, rwp.PROXY_PORT, rwp.PROXY_PASS = host, int(port), password

        gost_proc = gost_cfg = relay_proc = None
        # Mobile Decodo rejects IP-CONNECT AND can't be chained via gost (0x03),
        # so route the phone through the SNI relay straight to Decodo (hostname-
        # CONNECT, the proven `curl --socks5-hostname` path). Residential keeps the
        # proven gost-direct path.
        direct_decodo = args.gateway == "mobile"
        try:
            if direct_decodo:
                session_user = spec["upstream_user"]
                relay_proc = _relay_start(RELAY_PORT, int(port), up_host=host,
                                          up_user=session_user, up_pass=password)
                exit_ip = _decodo_exit_ip(host, int(port), session_user, password)
                phone_port = RELAY_PORT
            else:
                gost_proc, gost_cfg = rwp.gost_start([spec])
                exit_ip = rwp.resolve_proxy_ip(GOST_PORT)
                phone_port = GOST_PORT
            rwp.socksdroid_connect(serial, phone_port)
            if not rwp.wait_tunnel(serial):
                print(f"[attempt {attempt}] tunnel never came up — next IP")
                continue
            status = _precheck_serp(serial, args.keyword)
            print(f"[attempt {attempt}] sid={sid} exit_ip={exit_ip or '?'} precheck={status}")
            # Only rotate on an EXPLICIT captcha. 'unknown' usually means the SERP is loading
            # behind Chrome's post-pm-clear dialog, not a bad IP — proceed and let the flow's
            # own resetChrome handle dialogs.
            if status == "blocked":
                continue

            print(f"[attempt {attempt}] IP not blocked (precheck={status}) — running full SEO scrape…")
            summary = sd.dispatch_one(serial, args.keyword, args.target, Path(args.out),
                                      local_port=LOCAL_HTTP_PORT, retries=0)
            summary["proxy_ip"] = exit_ip
            sd._print_summary(summary)
            # The precheck (quick /search load) can miss a captcha that only fires after
            # the full navigate→type→submit flow. Only a real SERP counts as a win; rotate
            # to a fresh IP on captcha, app error, OR an empty parse.
            blocked = summary.get("status") == "blocked" or summary.get("challenge")
            errored = summary.get("status") == "error"
            no_results = summary.get("organic_count", 0) == 0
            if blocked or errored or no_results:
                why = "captcha" if blocked else (summary.get("error") or "no organic results")
                print(f"[attempt {attempt}] not clean on {exit_ip or '?'} ({why}) — rotating to a fresh IP…")
                continue
            print(f"[seo-proxy] DONE — clean SERP scraped on IP {exit_ip}")
            return 0
        finally:
            try:
                rwp.socksdroid_disconnect(serial)
            except Exception:
                pass
            if relay_proc is not None:
                relay_proc.terminate()
                try:
                    relay_proc.wait(timeout=5)
                except Exception:
                    relay_proc.kill()
            if gost_proc is not None:
                rwp.gost_stop(gost_proc, gost_cfg)

    print(f"[seo-proxy] no clean IP found in {args.attempts} attempts — try --gateway mobile (needs SUPERPROXY_PASS)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
