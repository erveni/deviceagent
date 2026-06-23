"""Single-job dispatch for the Solace consumer path.

Per-job lifecycle: acquire a free device → start a 1-port gost → connect
socksdroid → mock location → POST /session to FlowEngine → poll /status →
tear down → return CSV row.

Helpers (gost, socksdroid, http_post, etc.) are shared with run_with_proxy.py.
"""
from __future__ import annotations

import csv
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

# Match ", XX 12345" or ", XX 12345-6789" near the end of a US address.
_STATE_RE = re.compile(r',\s*([A-Z]{2})\s+\d{5}(?:-\d{4})?')


def _parse_state(addr: str) -> str | None:
    """Extract 2-letter US state code from a biz_address like
    '1010 South Gilbert Road, Chandler, AZ 85286-5169, USA'. Returns None if
    the address lacks a parseable 'STATE ZIP' tail."""
    if not addr:
        return None
    m = _STATE_RE.search(addr)
    return m.group(1) if m else None

from run_with_proxy import (
    DEVICES,
    BASE_GOST,
    PROXY_USER,
    DURATION,
    MAC_IP,
    build_upstream_user,
    extract_domain,
    gost_start,
    gost_stop,
    http_post,
    mock_location,
    randomize_location,
    rsid,
    run,
    set_timezone,
    socksdroid_connect,
    socksdroid_disconnect,
    wait_tunnel,
)

# Canonical daily session CSV header — matches
# /Users/seolocalph/projects/aeo-appium/sessions_log.daily_*.csv
CSV_FIELDS = [
    "timestamp", "date", "wave_index",
    "client_id", "client_name", "biz_name", "search_address",
    "campaign_id", "campaign_name",
    "keyword", "keyword_variant", "variant_id",
    "prompt", "follow_up", "has_follow_up",
    "device_id", "platform", "status", "duration_s",
    "proxy_status", "proxy_username", "proxy_host", "proxy_port",
    "base_latitude", "base_longitude",
    "mocked_latitude", "mocked_longitude", "mocked_timezone",
    "backlinks_expected", "backlink_injected",
    "backlink_found", "backlink_url",
    "failure_step", "error",
]

STATUS_POLL_INTERVAL_S = 8
STATUS_POLL_MAX_TICKS = 50
TUNNEL_SETTLE_S = 3

# Retry-once-with-fresh-Decodo-session triggers — empirically known to recover
# on a second IP per audit_dispatch_http.py:591-598. Ported here because the
# daily path was missing the same recovery and was tripping the consumer's
# circuit breaker on input-failed bursts that a fresh Decodo session clears.
RETRY_TRIGGERS = ("input failed", "navigate", "proxy_unreachable", "generation timeout")


class DevicePool:
    """Thread-safe device pool — acquire an idle device index, run, release."""

    def __init__(self) -> None:
        self._busy = [False] * len(DEVICES)
        self._cond = threading.Condition()
        self._forwarded = False
        # Phones to never hand out (chronically flaky / physically offline).
        # Set DEVICE_EXCLUDE to a comma list of device labels or serial substrings,
        # e.g. DEVICE_EXCLUDE="device-105,device-107".
        self._excluded = set()
        _exc = os.environ.get("DEVICE_EXCLUDE", "")
        if _exc.strip():
            toks = [t.strip() for t in _exc.split(",") if t.strip()]
            for i, (label, ser) in enumerate(DEVICES):
                if any(t == label or t in ser for t in toks):
                    self._excluded.add(i)
            print(f"[pool] DEVICE_EXCLUDE -> skipping idx {sorted(self._excluded)}: "
                  f"{[DEVICES[i][0] for i in sorted(self._excluded)]}", flush=True)
        # Round-robin starting offset for acquire() — spreads load across all
        # phones instead of always picking the lowest idle index. Each
        # successful acquire advances this so subsequent calls start their
        # search from a different point.
        self._rr_offset = 0

    def setup_forwards(self) -> None:
        with self._cond:
            if self._forwarded:
                return
            run("adb forward --remove-all")
            for i, (_, ser) in enumerate(DEVICES):
                run(f'adb -s "{ser}" forward tcp:{8765 + i} tcp:8765')
            self._forwarded = True

    def acquire(self, timeout: float | None = None) -> int | None:
        """Acquire an idle device index, but only from phones that are
        currently adb-reachable. An offline phone is skipped — its slot
        won't be handed out until adb sees it again."""
        from run_with_proxy import get_online_serials
        n = len(DEVICES)
        with self._cond:
            deadline = time.time() + timeout if timeout else None
            while True:
                online = get_online_serials()
                # Round-robin: start scanning from _rr_offset so consecutive
                # acquires cycle through all phones (e.g. pick 0,1,2,3,...)
                # instead of repeatedly hitting phones 0,1,2 while 3-9 idle.
                for k in range(n):
                    i = (self._rr_offset + k) % n
                    if i in self._excluded:
                        continue
                    if not self._busy[i] and DEVICES[i][1] in online:
                        self._busy[i] = True
                        self._rr_offset = (i + 1) % n
                        return i
                if deadline is not None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    self._cond.wait(min(remaining, 5))  # re-check online state at most every 5s
                else:
                    self._cond.wait(5)  # re-check online state at most every 5s

    def release(self, idx: int) -> None:
        with self._cond:
            self._busy[idx] = False
            self._cond.notify()


POOL = DevicePool()
_csv_lock = threading.Lock()


def build_dispatch_job(job_record: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    """Combine raw orchestrator JobRecord + AEOAdmin build-session response.

    biz_lat/biz_lng/biz_timezone are not provided by build-session today —
    GPS spoofing falls back to skipped when 0/empty.
    """
    campaign = job_record.get("campaign") or {}
    business = campaign.get("business") or {}
    client = business.get("client") or {}

    backlinks: list[dict[str, Any]] = []
    if enriched.get("backlinkInjected") and enriched.get("backlinkUrl"):
        backlinks = [{
            "url": enriched["backlinkUrl"],
            "type": enriched.get("backlinkType"),
        }]

    follow_up = enriched.get("followUp", "") if enriched.get("hasFollowUp") else ""

    return {
        "keyword_id": enriched.get("keywordId"),
        "keyword_text": enriched.get("keywordText", ""),
        "keyword_variant": enriched.get("variantText", ""),
        "variant_id": enriched.get("variantId"),
        "platform": (enriched.get("platform") or "chatgpt").lower(),
        "prompt": enriched.get("prompt", ""),
        "follow_up": follow_up,
        "backlink_injected": bool(enriched.get("backlinkInjected")),
        "backlinks": backlinks,
        "client_id": enriched.get("clientId", ""),
        "client_name": client.get("clientName", ""),
        "biz_name": enriched.get("bizName", ""),
        "biz_address": enriched.get("searchAddress", ""),
        "biz_lat": 0,
        "biz_lng": 0,
        "biz_timezone": "",
        "campaign_id": enriched.get("campaignId", ""),
        "campaign_name": business.get("businessName", ""),
        "targetDate": job_record.get("targetDate", ""),
    }


def dispatch_one_job(
    job: dict[str, Any],
    csv_path: str | None = None,
    wave_index: int = 0,
    acquire_timeout: float | None = None,
) -> dict[str, Any]:
    """Run one enriched job end-to-end on a free device, return the CSV row."""
    POOL.setup_forwards()
    device_idx = POOL.acquire(timeout=acquire_timeout)
    if device_idx is None:
        row = _err_row(job, "device-?", _placeholder_spec(0), wave_index,
                       "device_pool_timeout", "no idle device within timeout")
        if csv_path:
            append_row(csv_path, row)
        return row

    device_id, serial = DEVICES[device_idx]
    sid = rsid()
    spec = {
        "port": BASE_GOST + device_idx,
        "upstream_user": build_upstream_user(sid),
        "sid": sid,
    }

    gost_proc = None
    gost_cfg = None
    row: dict[str, Any]
    try:
        gost_proc, gost_cfg = gost_start([spec])
        socksdroid_connect(serial, spec["port"])
        time.sleep(TUNNEL_SETTLE_S)

        if not wait_tunnel(serial):
            row = _err_row(job, device_id, spec, wave_index, "tunnel_failed", "tunnel failed")
        else:
            row = _run_session(job, device_idx, device_id, serial, spec, wave_index)
            # Retry once with a fresh Decodo session on known-transient errors.
            # Mirrors audit_dispatch_http.py:587-643. Same triggers, same recovery
            # path: tear down current gost+socksdroid, rotate session_id (rsid),
            # restart, re-run. Most input-failed bursts clear on second IP per
            # the audit author's empirical claim.
            #
            # Zip-aware: on retry, target the state's known-good Decodo zip
            # instead of repeating country-only US (which gave us the burned IP
            # in the first place). State parsed from biz_address; falls back to
            # _FALLBACK_GOOD_ZIP if address lacks a 'STATE ZIP' tail.
            err = (row.get("error") or "").lower()
            if row.get("status") == "error" and any(t in err for t in RETRY_TRIGGERS):
                reason = next(t for t in RETRY_TRIGGERS if t in err).replace(" ", "_")
                # Lazy import — audit_dispatch_http imports POOL from this
                # module, so a top-level import would be circular.
                from audit_dispatch_http import _STATE_GOOD_ZIP, _FALLBACK_GOOD_ZIP
                state = _parse_state(job.get("biz_address", ""))
                retry_zip = _STATE_GOOD_ZIP.get(state.upper(), _FALLBACK_GOOD_ZIP) if state else _FALLBACK_GOOD_ZIP
                print(
                    f"  [retry] {reason} on device={device_id} — "
                    f"rotating proxy session, state={state or '?'} zip={retry_zip}",
                    flush=True,
                )
                gost_stop(gost_proc, gost_cfg)
                gost_proc, gost_cfg = None, None
                try:
                    socksdroid_disconnect(serial)
                except Exception:
                    pass
                # Wait for OS to release the TCP port before rebinding. Without
                # this, the rebind races TIME_WAIT and gost dies with
                # "bind: address already in use" → dispatch_exception. The
                # audit dispatcher (GostManager.start(wait_seconds=2.0)) does
                # the same wait; cc78963 / b758d1b missed it.
                time.sleep(2)
                sid = rsid()
                upstream_user = build_upstream_user(sid, zip_=retry_zip, state=state)
                spec = {
                    "port": BASE_GOST + device_idx,
                    "upstream_user": upstream_user,
                    "sid": sid,
                }
                gost_proc, gost_cfg = gost_start([spec])
                socksdroid_connect(serial, spec["port"])
                time.sleep(TUNNEL_SETTLE_S)
                if not wait_tunnel(serial):
                    row = _err_row(job, device_id, spec, wave_index,
                                   "tunnel_failed_retry", "tunnel failed on retry")
                else:
                    row = _run_session(job, device_idx, device_id, serial, spec, wave_index)
    except Exception as e:
        row = _err_row(job, device_id, spec, wave_index, "dispatch_exception", f"{type(e).__name__}: {e}")
    finally:
        if gost_proc is not None and gost_cfg is not None:
            gost_stop(gost_proc, gost_cfg)
        try:
            socksdroid_disconnect(serial)
        except Exception:
            pass
        POOL.release(device_idx)

    if csv_path:
        append_row(csv_path, row)
    return row


def _run_session(
    job: dict[str, Any],
    device_idx: int,
    device_id: str,
    serial: str,
    spec: dict[str, Any],
    wave_index: int,
) -> dict[str, Any]:
    bl = job.get("biz_lat", 0) or 0
    bln = job.get("biz_lng", 0) or 0
    if bl and bln:
        ml, mln = randomize_location(bl, bln)
        mock_location(serial, ml, mln)
    else:
        ml, mln = 0, 0
    tz = job.get("biz_timezone", "")
    if tz:
        set_timezone(serial, tz)

    port = 8765 + device_idx
    platform = job.get("platform", "chatgpt").lower()
    prompt = job.get("prompt", "")
    follow_up = job.get("follow_up") or None
    backlinks = job.get("backlinks") or []
    bk_domain = extract_domain(backlinks[0]["url"]) if backlinks else ""

    t0 = time.time()
    http_post(port, "/session", {
        "platform": platform,
        "prompt": prompt,
        "followUp": follow_up,
        "backlinkDomain": bk_domain,
    })

    r: dict[str, Any] = {"status": "running"}
    for _ in range(STATUS_POLL_MAX_TICKS):
        time.sleep(STATUS_POLL_INTERVAL_S)
        r = http_post(port, "/status")
        if r.get("status") in ("completed", "error"):
            break

    duration_s = round(time.time() - t0, 1)
    bk_url = backlinks[0]["url"] if (r.get("backlink_clicked") and backlinks) else ""
    status = "success" if r.get("status") == "completed" and not r.get("error") else "error"

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": (str(job.get("targetDate") or "")[:10]) or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "wave_index": wave_index,
        "client_id": job.get("client_id", ""),
        "client_name": job.get("client_name", ""),
        "biz_name": job.get("biz_name", ""),
        "search_address": job.get("biz_address", ""),
        "campaign_id": job.get("campaign_id", ""),
        "campaign_name": job.get("campaign_name", ""),
        "keyword": job.get("keyword_text", ""),
        "keyword_variant": job.get("keyword_variant", "") or "",
        "variant_id": job.get("variant_id") if job.get("variant_id") is not None else "",
        "prompt": prompt,
        "follow_up": follow_up or "",
        "has_follow_up": bool(follow_up),
        "device_id": device_id,
        "platform": platform,
        "status": status,
        "duration_s": duration_s,
        "proxy_status": "CONNECTED",
        "proxy_username": spec["upstream_user"],
        "proxy_host": MAC_IP,
        "proxy_port": spec["port"],
        "base_latitude": bl,
        "base_longitude": bln,
        "mocked_latitude": ml,
        "mocked_longitude": mln,
        "mocked_timezone": tz,
        "backlinks_expected": len(backlinks),
        "backlink_injected": job.get("backlink_injected", False),
        "backlink_found": bool(r.get("backlink_clicked")),
        "backlink_url": bk_url,
        "failure_step": r.get("error", ""),
        "error": r.get("error", ""),
    }


def _placeholder_spec(idx: int) -> dict[str, Any]:
    return {"port": BASE_GOST + idx, "upstream_user": "", "sid": ""}


def _err_row(
    job: dict[str, Any],
    device_id: str,
    spec: dict[str, Any],
    wave_index: int,
    step: str,
    msg: str,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": (str(job.get("targetDate") or "")[:10]) or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "wave_index": wave_index,
        "client_id": job.get("client_id", ""),
        "client_name": job.get("client_name", ""),
        "biz_name": job.get("biz_name", ""),
        "search_address": job.get("biz_address", ""),
        "campaign_id": job.get("campaign_id", ""),
        "campaign_name": job.get("campaign_name", ""),
        "keyword": job.get("keyword_text", ""),
        "keyword_variant": job.get("keyword_variant", "") or "",
        "variant_id": job.get("variant_id") if job.get("variant_id") is not None else "",
        "prompt": job.get("prompt", ""),
        "follow_up": job.get("follow_up", "") or "",
        "has_follow_up": bool(job.get("follow_up", "")),
        "device_id": device_id,
        "platform": (job.get("platform") or "chatgpt").lower(),
        "status": "error",
        "duration_s": 0,
        "proxy_status": "FAILED",
        "proxy_username": spec.get("upstream_user", ""),
        "proxy_host": MAC_IP,
        "proxy_port": spec.get("port", 0),
        "base_latitude": job.get("biz_lat", 0) or 0,
        "base_longitude": job.get("biz_lng", 0) or 0,
        "mocked_latitude": 0,
        "mocked_longitude": 0,
        "mocked_timezone": job.get("biz_timezone", ""),
        "backlinks_expected": len(job.get("backlinks") or []),
        "backlink_injected": job.get("backlink_injected", False),
        "backlink_found": False,
        "backlink_url": "",
        "failure_step": step,
        "error": msg,
    }


def append_row(csv_path: str, row: dict[str, Any]) -> None:
    """Append one row to CSV. File is date-stamped from row's `date` field
    so a wave that crosses UTC midnight splits cleanly per day.
    e.g. solace_pilot_results.csv -> solace_pilot_results_2026-05-22.csv."""
    base, ext = os.path.splitext(csv_path)
    date = row.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated_path = f"{base}_{date}{ext}"
    write_header = not os.path.exists(dated_path)
    with _csv_lock:
        with open(dated_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if write_header:
                w.writeheader()
            w.writerow(row)
