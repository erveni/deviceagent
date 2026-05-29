#!/usr/bin/env python3
"""SuperProxy-backed single-job dispatch (Decodo Mobile pivot).

Drop-in alternative to device_dispatch.dispatch_one_job that swaps the proxy
layer: instead of gost_start + socksdroid_connect (the old residential chain),
it brings the Decodo Mobile tunnel up via superproxy_proxy.setup() (the
SuperProxy app driven by the device-agent on :7070). The actual AI session is
unchanged — POST /session to the old com.deviceagent on :8765 and poll /status —
because SuperProxy's VPN carries that traffic system-wide.

Per-job lifecycle:
    acquire device -> superproxy_proxy.setup() (clean->save->start->verify tun0)
    -> POST /session to com.deviceagent:8765 -> poll /status
    -> superproxy_proxy.teardown() (pm clear) -> return CSV row

Status of the pivot (2026-05-28): proxy setup is validated end-to-end (US Verizon
mobile egress). The /session step depends on the phone being provisioned for the
AI workload (com.deviceagent accessibility ON + platform apps) — on an
unprovisioned phone it returns an error row at failure_step=session_*, which is
the expected, clean boundary.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import superproxy_proxy as sp
from run_with_proxy import DEVICES, extract_domain, http_post
from device_dispatch import POOL, CSV_FIELDS, append_row

# AI-session HTTP server on the OLD device-agent app (unchanged from gost path).
OLD_AGENT_BASE_PORT = 8765
STATUS_POLL_INTERVAL_S = 8
STATUS_POLL_MAX_TICKS = 50


def _old_agent_local_port(device_idx: int) -> int:
    # device_dispatch.POOL.setup_forwards() maps 8765+idx -> phone 8765.
    return OLD_AGENT_BASE_PORT + device_idx


def _run_session_sp(job: dict[str, Any], device_idx: int, device_id: str,
                    proxy_info: dict[str, Any], wave_index: int) -> dict[str, Any]:
    """POST /session to the old agent and poll. Proxy egress is the live
    SuperProxy tunnel, so no per-session proxy plumbing here."""
    port = _old_agent_local_port(device_idx)
    platform = (job.get("platform") or "chatgpt").lower()
    prompt = job.get("prompt", "")
    follow_up = job.get("follow_up") or None
    backlinks = job.get("backlinks") or []
    bk_domain = extract_domain(backlinks[0]["url"]) if backlinks else ""

    t0 = time.time()
    http_post(port, "/session", {
        "platform": platform, "prompt": prompt,
        "followUp": follow_up, "backlinkDomain": bk_domain,
    })
    r: dict[str, Any] = {"status": "running"}
    for _ in range(STATUS_POLL_MAX_TICKS):
        time.sleep(STATUS_POLL_INTERVAL_S)
        r = http_post(port, "/status")
        if r.get("status") in ("completed", "error"):
            break

    duration_s = round(time.time() - t0, 1)
    status = "success" if r.get("status") == "completed" and not r.get("error") else "error"
    bk_url = backlinks[0]["url"] if (r.get("backlink_clicked") and backlinks) else ""
    return _row(job, device_id, proxy_info, wave_index, status, duration_s,
                failure_step=r.get("error", ""), error=r.get("error", ""),
                backlink_found=bool(r.get("backlink_clicked")), backlink_url=bk_url)


def _row(job: dict[str, Any], device_id: str, proxy_info: dict[str, Any],
         wave_index: int, status: str, duration_s: float, *,
         failure_step: str = "", error: str = "",
         backlink_found: bool = False, backlink_url: str = "") -> dict[str, Any]:
    """CSV row matching device_dispatch.CSV_FIELDS. Proxy columns are repurposed
    for the SuperProxy chain: proxy_username = Decodo Mobile user, proxy_host =
    'superproxy', proxy_port = Decodo gate port, and the phone-side egress (tun0
    ip) rides in mocked-free fields via failure_step when needed."""
    backlinks = job.get("backlinks") or []
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": (str(job.get("targetDate") or "")[:10]) or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "wave_index": wave_index,
        "client_id": job.get("client_id", ""), "client_name": job.get("client_name", ""),
        "biz_name": job.get("biz_name", ""), "search_address": job.get("biz_address", ""),
        "campaign_id": job.get("campaign_id", ""), "campaign_name": job.get("campaign_name", ""),
        "keyword": job.get("keyword_text", ""), "keyword_variant": job.get("keyword_variant", ""),
        "variant_id": job.get("variant_id", ""),
        "prompt": job.get("prompt", ""), "follow_up": job.get("follow_up", "") or "",
        "has_follow_up": bool(job.get("follow_up", "")),
        "device_id": device_id, "platform": (job.get("platform") or "chatgpt").lower(),
        "status": status, "duration_s": duration_s,
        "proxy_status": "CONNECTED" if proxy_info.get("tun0_ip") else "FAILED",
        "proxy_username": proxy_info.get("username", ""),
        "proxy_host": "superproxy", "proxy_port": sp.SUPERPROXY_PORT,
        "base_latitude": job.get("biz_lat", 0) or 0, "base_longitude": job.get("biz_lng", 0) or 0,
        "mocked_latitude": 0, "mocked_longitude": 0, "mocked_timezone": job.get("biz_timezone", ""),
        "backlinks_expected": len(backlinks),
        "backlink_injected": job.get("backlink_injected", False),
        "backlink_found": backlink_found, "backlink_url": backlink_url,
        # tun0 ip captured in failure_step when there's no error, so the chain's
        # exit is recorded without adding a column the consumer doesn't know.
        "failure_step": failure_step or (f"tun0={proxy_info.get('tun0_ip')}" if proxy_info.get("tun0_ip") else ""),
        "error": error,
    }


def dispatch_one_job_superproxy(
    job: dict[str, Any], csv_path: str | None = None, wave_index: int = 0,
    device_idx: int | None = None, acquire_timeout: float | None = None,
) -> dict[str, Any]:
    """Run one job end-to-end over the SuperProxy chain; return the CSV row.

    `device_idx` pins a specific phone (used by the standalone test); otherwise a
    free device is acquired from device_dispatch.POOL."""
    POOL.setup_forwards()
    acquired = False
    if device_idx is None:
        device_idx = POOL.acquire(timeout=acquire_timeout)
        acquired = True
        if device_idx is None:
            row = _row(job, "device-?", {}, wave_index, "error", 0,
                       failure_step="device_pool_timeout", error="no idle device")
            if csv_path:
                append_row(csv_path, row)
            return row

    device_id, serial = DEVICES[device_idx]
    proxy_info: dict[str, Any] = {}
    try:
        ok, info = sp.setup(serial, device_idx)
        proxy_info = info
        if not ok:
            row = _row(job, device_id, info, wave_index, "error", 0,
                       failure_step="superproxy_setup_failed",
                       error=str(info.get("reason", "setup failed")))
        else:
            print(f"  [superproxy] {device_id} up: user={info.get('username')} "
                  f"tun0={info.get('tun0_ip')} attempts={info.get('attempts')}", flush=True)
            row = _run_session_sp(job, device_idx, device_id, info, wave_index)
    except Exception as e:
        row = _row(job, device_id, proxy_info, wave_index, "error", 0,
                   failure_step="dispatch_exception", error=f"{type(e).__name__}: {e}")
    finally:
        try:
            sp.teardown(serial)
        except Exception:
            pass
        if acquired:
            POOL.release(device_idx)

    if csv_path:
        append_row(csv_path, row)
    return row


# ── audit (RANKING) over SuperProxy ───────────────────────────────────────────
AUDIT_HTTP_TIMEOUT_S = 360  # the old agent's audit /session blocks until ranking is done
# Transient audit failures that recover on a fresh Decodo session (mirrors
# audit_dispatch_http.RETRY_TRIGGERS).
AUDIT_RETRY_TRIGGERS = ("generation timeout", "navigate", "input failed", "proxy_unreachable")


def _post_audit(local_port: int, body: dict) -> dict:
    """Blocking POST /session?type=audit — the old agent returns the full ranking
    result (not the async daily flow). Mirrors audit_dispatch_http._post_audit,
    incl. salvaging the JSON body from a 500 (status==error still carries detail)."""
    import urllib.error, urllib.request, json as _json
    req = urllib.request.Request(
        f"http://localhost:{local_port}/session",
        data=_json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AUDIT_HTTP_TIMEOUT_S) as r:
            return _json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return _json.loads(e.read().decode())
        except Exception:
            return {"status": "error", "error": f"HTTP {e.code} (no body)"}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


def _classify_audit(resp: dict, platform: str) -> tuple[str, str, str]:
    """(status, rank_position, rank_total). Mirrors audit_dispatch_http._classify."""
    plats = resp.get("platforms", {})
    pr = plats.get(platform.lower()) or plats.get(platform) or {}
    pos = pr.get("ranking_position") or resp.get("ranking_position") or 0
    total = pr.get("ranking_total") or resp.get("ranking_total") or ""
    st = pr.get("status") or resp.get("status", "")
    err = (pr.get("error") or resp.get("error") or "").lower()
    if st == "completed" and pos and int(pos) > 0:
        return ("success", str(pos), str(total))
    if st == "completed":
        return ("no_rank", "", "")
    if "generation timeout" in err or "wait_generation" in err:
        return ("flow_failed", "", "")
    return ("error", "", "")


def dispatch_audit_job_superproxy(
    job: dict[str, Any], platform: str, csv_path: str | None = None,
    device_idx: int | None = None, acquire_timeout: float | None = None,
) -> dict[str, Any]:
    """Run one RANKING audit over the SuperProxy chain on a phone; return CSV row."""
    POOL.setup_forwards()
    acquired = False
    if device_idx is None:
        device_idx = POOL.acquire(timeout=acquire_timeout)
        acquired = True
        if device_idx is None:
            return _row(job, "device-?", {}, 0, "error", 0,
                        failure_step="device_pool_timeout", error="no idle device")

    device_id, serial = DEVICES[device_idx]
    proxy_info: dict[str, Any] = {}
    try:
        ok, info = sp.setup(serial, device_idx)
        proxy_info = info
        if not ok:
            row = _row(job, device_id, info, 0, "error", 0,
                       failure_step="superproxy_setup_failed", error=str(info.get("reason", "")))
        else:
            print(f"  [superproxy] {device_id} up: user={info.get('username')} "
                  f"tun0={info.get('tun0_ip')} attempts={info.get('attempts')}", flush=True)
            port = _old_agent_local_port(device_idx)
            body = {
                "type": "audit", "platform": platform.lower(),
                "bizName": job.get("biz_name", ""), "bizUrl": job.get("biz_url", ""),
                "city": job.get("city", ""), "state": job.get("state", ""),
                "keyword": job.get("keyword_text", "") or job.get("keyword", ""),
            }
            t0 = time.time()
            resp = _post_audit(port, body)
            status, pos, total = _classify_audit(resp, platform)
            # Retry once on a fresh Decodo Mobile session for known-transient
            # failures (mirrors audit_dispatch_http RETRY_TRIGGERS). A new SuperProxy
            # session = teardown (pm clear) -> setup() again -> re-post. Most
            # generation-timeout / input-failed cases clear on a second IP.
            plat_err = ((resp.get("platforms") or {}).get(platform.lower(), {}).get("error") or "").lower()
            top_err = (resp.get("error") or "").lower()
            combined = f"{plat_err} {top_err}"
            if status != "success" and any(t in combined for t in AUDIT_RETRY_TRIGGERS):
                reason = next(t for t in AUDIT_RETRY_TRIGGERS if t in combined)
                print(f"  [retry] audit {reason!r} on {device_id} — rotating Decodo session", flush=True)
                sp.teardown(serial)
                time.sleep(2)
                ok2, info2 = sp.setup(serial, device_idx)
                if ok2:
                    proxy_info = info2
                    print(f"  [superproxy] {device_id} re-up: tun0={info2.get('tun0_ip')} "
                          f"attempts={info2.get('attempts')}", flush=True)
                    resp = _post_audit(port, body)
                    status, pos, total = _classify_audit(resp, platform)
                else:
                    print(f"  [retry] re-setup failed: {info2.get('reason')}", flush=True)
            dur = round(time.time() - t0, 1)
            info = proxy_info
            row = _row(job, device_id, info, 0,
                       "success" if status == "success" else "error", dur,
                       failure_step=(f"rank={pos}/{total}" if status == "success"
                                     else status) + f" tun0={info.get('tun0_ip')}",
                       error="" if status in ("success", "no_rank") else resp.get("error", status))
            row["keyword"] = body["keyword"]
            row["platform"] = platform.lower()
            print(f"  [audit] {device_id} {platform} -> {status} rank={pos}/{total} ({dur}s)", flush=True)
    except Exception as e:
        row = _row(job, device_id, proxy_info, 0, "error", 0,
                   failure_step="dispatch_exception", error=f"{type(e).__name__}: {e}")
    finally:
        try:
            sp.teardown(serial)
        except Exception:
            pass
        if acquired:
            POOL.release(device_idx)

    if csv_path:
        append_row(csv_path, row)
    return row


# ── standalone test harness ───────────────────────────────────────────────────
def _dummy_audit_job() -> dict[str, Any]:
    return {
        "keyword_text": "emergency child care", "keyword": "emergency child care",
        "biz_name": "Mae's Childcare", "biz_url": "https://maes.example.com",
        "city": "San Francisco", "state": "CA",
        "client_id": "dummy-mae", "client_name": "Mae's Childcare LLC",
        "campaign_id": "dummy-camp", "campaign_name": "Mae's Childcare",
        "backlinks": [], "biz_lat": 0, "biz_lng": 0, "biz_timezone": "",
        "targetDate": datetime.now(timezone.utc).isoformat(),
    }


def _dummy_daily_job() -> dict[str, Any]:
    return {
        "platform": "chatgpt",
        "prompt": "Friend mentioned Mae's Childcare over near 1234 Bilingual Way in "
                  "San Francisco — they actually any good when it comes to child care?",
        "keyword_text": "emergency child care", "keyword_variant": "emergency child care",
        "client_id": "dummy-mae", "client_name": "Mae's Childcare LLC",
        "biz_name": "Mae's Childcare", "biz_address": "1234 Bilingual Way, San Francisco, CA 94110, USA",
        "campaign_id": "dummy-camp", "campaign_name": "Mae's Childcare",
        "backlinks": [], "backlink_injected": False, "biz_lat": 0, "biz_lng": 0, "biz_timezone": "",
        "targetDate": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="Run one dummy DAILY or RANKING job over SuperProxy on a pinned phone.")
    ap.add_argument("--device-idx", type=int, default=5, help="index into run_with_proxy.DEVICES (default 5 = device-106)")
    ap.add_argument("--audit", action="store_true", help="run a RANKING audit instead of a DAILY session")
    ap.add_argument("--platform", default="chatgpt", choices=["chatgpt", "gemini", "perplexity"])
    ap.add_argument("--csv", default=None, help="optional CSV output path")
    args = ap.parse_args()
    if args.audit:
        row = dispatch_audit_job_superproxy(_dummy_audit_job(), args.platform,
                                            csv_path=args.csv, device_idx=args.device_idx)
    else:
        job = _dummy_daily_job(); job["platform"] = args.platform
        row = dispatch_one_job_superproxy(job, csv_path=args.csv, device_idx=args.device_idx)
    print(json.dumps(row, indent=2, default=str))
