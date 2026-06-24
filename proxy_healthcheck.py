#!/usr/bin/env python3
"""Decodo residential proxy health + flagging preflight.

Answers four operational questions before (or during) a fleet run:
  1. LEAK     — does any session egress on our OWN home IP instead of the proxy?
  2. ROTATION — do distinct sessions get distinct exit IPs (not one sticky IP)?
  3. GEO      — do US-targeted sessions actually land in the US?
  4. FLAGGED  — is Google treating the Decodo exit IP as a bot (the real cause
                of logged-out Gemini "response disappeared" / chat-revert)?

stdlib only. Reads proxy creds the same way the runners do (env first, then the
hardcoded residential account in run_ranking_auto.sh). Run:

    python3 proxy_healthcheck.py            # 5 sessions
    SESSIONS=10 python3 proxy_healthcheck.py
"""
import json, os, ssl, subprocess, sys, urllib.request

HOST = os.environ.get("PROXY_HOST", "gate.decodo.com")
PORT = int(os.environ.get("PROXY_PORT_RES", "10001"))            # residential
USER = os.environ.get("PROXY_BASE_USER") or os.environ.get("PROXY_USER", "user-spmqebjuzf")
PASW = os.environ.get("PROXY_PASSWORD") or os.environ.get("PROXY_PASS", "")
TARGET = os.environ.get("PROXY_TARGET", "country-us")
N = int(os.environ.get("SESSIONS", "5"))
TIMEOUT = int(os.environ.get("PROBE_TIMEOUT", "25"))


def _session_user(sid):
    # exact production format from run_with_proxy.py:397
    return f"{USER}-session-{sid}-sessionduration-30-{TARGET}"


def _curl(proxy_user, url, want_headers=False):
    """One request through the proxy. Returns (rc, body/headers-text)."""
    args = ["curl", "-sS", "--max-time", str(TIMEOUT),
            "-x", f"http://{proxy_user}:{PASW}@{HOST}:{PORT}", url]
    if want_headers:
        args[1:1] = ["-D", "-", "-o", "/dev/null"]
    cp = subprocess.run(args, capture_output=True, text=True)
    return cp.returncode, (cp.stdout or cp.stderr).strip()


def home_ip():
    ctx = ssl.create_default_context()
    for url, key in (("https://ipinfo.io/json", "ip"),
                     ("https://api.ipify.org?format=json", "ip"),
                     ("https://ifconfig.me/all.json", "ip_addr")):
        try:
            with urllib.request.urlopen(url, timeout=12, context=ctx) as r:
                ip = json.load(r).get(key, "")
                if ip:
                    return ip
        except Exception:
            continue
    return None  # unknown → leak check is skipped, not falsely passed


def probe_session(sid, home):
    """Returns a dict describing this session's health."""
    out = {"sid": sid, "ip": None, "city": None, "country": None,
           "leak": False, "reachable": False, "flagged": None, "note": ""}
    rc, body = _curl(_session_user(sid), "https://ipinfo.io/json")
    if rc != 0:
        out["note"] = f"unreachable rc={rc} {body[:80]}"
        return out
    try:
        info = json.loads(body)
    except Exception:
        out["note"] = f"bad json: {body[:80]}"
        return out
    out["reachable"] = True
    out["ip"] = info.get("ip")
    out["city"] = info.get("city")
    out["country"] = info.get("country")
    out["leak"] = bool(home) and out["ip"] == home

    # Flagging probe: a flagged IP gets bounced to Google's /sorry/ captcha or 429.
    rc2, hdr = _curl(_session_user(sid), "https://www.google.com/search?q=dentist+near+me",
                     want_headers=True)
    blob = hdr.lower()
    if rc2 != 0:
        out["flagged"] = None
        out["note"] = f"google probe failed rc={rc2}"
    elif "/sorry/" in blob or "429" in blob.split("\n")[0] or "unusual traffic" in blob:
        out["flagged"] = True
    else:
        out["flagged"] = False
    return out


def main():
    if not PASW:
        print("FATAL: no proxy password (set PROXY_PASSWORD / PROXY_PASS)", file=sys.stderr)
        return 2
    home = home_ip()
    print(f"home/egress IP (leak baseline): {home or 'unknown — leak check skipped'}")
    print(f"proxy: {USER}@{HOST}:{PORT} target={TARGET}  sessions={N}\n")

    results = [probe_session(f"hc{i:03d}", home) for i in range(N)]

    ips = [r["ip"] for r in results if r["reachable"]]
    distinct = len(set(ips))
    leaks = [r for r in results if r["leak"]]
    non_us = [r for r in results if r["reachable"] and r["country"] not in ("US", None)]
    flagged = [r for r in results if r["flagged"] is True]
    unreachable = [r for r in results if not r["reachable"]]

    for r in results:
        flag = {True: "FLAGGED", False: "clean", None: "flag-probe-failed"}[r["flagged"]]
        loc = f"{r['city']},{r['country']}" if r["reachable"] else r["note"]
        leak = "  <-- LEAK!" if r["leak"] else ""
        print(f"  {r['sid']}: ip={r['ip'] or '-':<16} {loc:<22} google={flag}{leak}")

    print("\n=== VERDICT ===")
    print(f"  reachable : {len(ips)}/{N}" + ("  WARN unreachable" if unreachable else ""))
    print(f"  rotation  : {distinct} distinct IPs / {len(ips)} sessions" +
          ("  OK" if distinct == len(ips) and ips else "  WARN sticky/duplicate IPs"))
    if not home:
        leak_msg = "SKIPPED — home IP unknown (but no proxy IP matched PH home)"
    else:
        leak_msg = "FAIL — egressing on home IP!" if leaks else "OK — no home-IP leak"
    print(f"  leak      : {leak_msg}")
    print(f"  geo       : {'WARN non-US: ' + ','.join(r['country'] for r in non_us) if non_us else 'OK — all US'}")
    fl = sum(1 for r in results if r["flagged"] is True)
    fc = sum(1 for r in results if r["flagged"] is False)
    print(f"  flagging  : {fl} flagged / {fc} clean" +
          ("  <-- Decodo pool is flagged by Google → logged-out Gemini will revert" if fl else ""))

    # exit non-zero if anything is genuinely broken (leak or all-flagged or none reachable)
    return 1 if (leaks or not ips or (fl and not fc)) else 0


if __name__ == "__main__":
    sys.exit(main())
