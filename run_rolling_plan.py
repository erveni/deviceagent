#!/usr/bin/env python3
"""Rolling-dispatch plan runner — standalone (no broker).

Reads a JSON plan file with `waves` of jobs and dispatches them rolling-style:
each free phone immediately pulls the next job from the queue. Built-in retry
on transient errors with a fresh Decodo session.

Unlike `run_with_proxy.py` (wave-based), this runner has no wave synchronization
— a phone that finishes early doesn't wait for the rest. Unlike
`device_dispatch.py` (hardcoded `country-us`), this runner honors the
`PROXY_TARGET` env var so mobile ASN targeting (`asn-21928`) works.

Env vars:
  MAX_PARALLEL          max concurrent phones (default 3)
  PROXY_TARGET          Decodo targeting (default "country-us", e.g. "asn-21928")
  PROXY_DURATION        sticky session minutes (default 60)
  SLEEP_BETWEEN_JOBS_S  per-worker breather between jobs (default 3)
  ROLLING_RETRY         set to "0" to disable retry (default on)
"""
from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime, timezone

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

from device_dispatch import (
    DEVICES, BASE_GOST, PROXY_USER, TUNNEL_SETTLE_S, RETRY_TRIGGERS,
    POOL, _run_session, _err_row, append_row,
)
from run_with_proxy import (
    gost_start, gost_stop, socksdroid_connect, socksdroid_disconnect,
    wait_tunnel, rsid,
)

MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", "3"))
PROXY_TARGET = os.environ.get("PROXY_TARGET", "country-us")
DURATION = int(os.environ.get("PROXY_DURATION", "60"))
SLEEP_BETWEEN_JOBS_S = float(os.environ.get("SLEEP_BETWEEN_JOBS_S", "3"))
ROLLING_RETRY = os.environ.get("ROLLING_RETRY", "1") == "1"
# NOTE: DEVICE_EXCLUDE is honored by POOL.acquire() (device_dispatch.DevicePool),
# which skips excluded/offline indices and returns indices into the full DEVICES
# list. Do NOT filter DEVICES here — that desyncs the index space and IndexErrors.


def normalize_plan_job(j: dict) -> dict:
    """Plan-file job → dispatch job format."""
    return {
        "keyword_text": j.get("keyword_text") or j.get("keyword") or "",
        "keyword_variant": j.get("keyword_variant") or j.get("keyword_text") or "",
        "variant_id": j.get("variant_id"),
        "platform": (j.get("platform") or "chatgpt").lower(),
        "prompt": j.get("prompt", ""),
        "follow_up": j.get("follow_up", "") or "",
        "backlink_injected": bool(j.get("backlink_injected")),
        "backlinks": j.get("backlinks", []),
        "client_id": j.get("client_id", ""),
        "client_name": j.get("client_name", ""),
        "biz_name": j.get("biz_name", ""),
        "biz_address": j.get("biz_address", "") or j.get("search_address", ""),
        "biz_lat": j.get("biz_lat", 0) or 0,
        "biz_lng": j.get("biz_lng", 0) or 0,
        "biz_timezone": j.get("biz_timezone", ""),
        "campaign_id": j.get("campaign_id", ""),
        "campaign_name": j.get("campaign_name", ""),
        "targetDate": j.get("targetDate", ""),
    }


def _build_spec(device_idx: int, sid: str) -> dict:
    return {
        "port": BASE_GOST + device_idx,
        "upstream_user": (
            f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}-{PROXY_TARGET}"
        ),
        "sid": sid,
    }


def dispatch_one(job: dict, csv_path: str, wave_index: int = 0) -> dict:
    """Run one job end-to-end. Honors PROXY_TARGET. Retries once on transient err."""
    POOL.setup_forwards()
    device_idx = POOL.acquire(timeout=300)
    if device_idx is None:
        row = _err_row(
            job, "device-?", _build_spec(0, ""), wave_index,
            "device_pool_timeout", "no idle device within timeout",
        )
        append_row(csv_path, row)
        return row

    device_id, serial = DEVICES[device_idx]
    sid = rsid()
    spec = _build_spec(device_idx, sid)
    gost_proc = None
    gost_cfg = None
    row: dict | None = None
    try:
        gost_proc, gost_cfg = gost_start([spec])
        socksdroid_connect(serial, spec["port"])
        time.sleep(TUNNEL_SETTLE_S)
        if not wait_tunnel(serial):
            row = _err_row(job, device_id, spec, wave_index, "tunnel_failed", "tunnel failed")
        else:
            row = _run_session(job, device_idx, device_id, serial, spec, wave_index)
            err = (row.get("error") or "").lower()
            if ROLLING_RETRY and row.get("status") == "error" and any(t in err for t in RETRY_TRIGGERS):
                reason = next(t for t in RETRY_TRIGGERS if t in err).replace(" ", "_")
                # Zip-aware retry (mirrors device_dispatch.py b758d1b): instead of
                # repeating country-only US (which gave us the burned IP), target the
                # state's empirically-validated good Decodo zip. State parsed from
                # biz_address; NYC 10001 fallback if no parseable 'STATE ZIP' tail.
                from audit_dispatch_http import _STATE_GOOD_ZIP, _FALLBACK_GOOD_ZIP
                state = _parse_state(job.get("biz_address", ""))
                retry_zip = _STATE_GOOD_ZIP.get(state.upper(), _FALLBACK_GOOD_ZIP) if state else _FALLBACK_GOOD_ZIP
                print(
                    f"  [retry] {reason} on {device_id} — rotating Decodo session, "
                    f"state={state or '?'} zip={retry_zip}",
                    flush=True,
                )
                gost_stop(gost_proc, gost_cfg)
                gost_proc, gost_cfg = None, None
                try:
                    socksdroid_disconnect(serial)
                except Exception:
                    pass
                time.sleep(2)
                sid = rsid()
                spec = {
                    "port": BASE_GOST + device_idx,
                    "upstream_user": (
                        f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}"
                        f"-country-us-zip-{retry_zip}"
                    ),
                    "sid": sid,
                }
                gost_proc, gost_cfg = gost_start([spec])
                socksdroid_connect(serial, spec["port"])
                time.sleep(TUNNEL_SETTLE_S)
                if not wait_tunnel(serial):
                    row = _err_row(
                        job, device_id, spec, wave_index,
                        "tunnel_failed_retry", "tunnel failed on retry",
                    )
                else:
                    row = _run_session(job, device_idx, device_id, serial, spec, wave_index)
    except Exception as e:
        row = _err_row(
            job, device_id, spec, wave_index,
            "dispatch_exception", f"{type(e).__name__}: {e}",
        )
    finally:
        if gost_proc is not None and gost_cfg is not None:
            gost_stop(gost_proc, gost_cfg)
        try:
            socksdroid_disconnect(serial)
        except Exception:
            pass
        POOL.release(device_idx)
    if row is not None:
        append_row(csv_path, row)
    return row


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: run_rolling_plan.py <plan.json>")
        sys.exit(1)
    plan_path = sys.argv[1]
    csv_path = os.path.splitext(plan_path)[0] + "_results.csv"
    plan = json.load(open(plan_path))
    jobs = [normalize_plan_job(j) for w in plan["waves"] for j in w]

    print("=" * 70, flush=True)
    print(f"  plan:        {plan_path}", flush=True)
    print(f"  total jobs:  {len(jobs)}", flush=True)
    print(f"  parallel:    {MAX_PARALLEL} phones at a time (rolling)", flush=True)
    print(f"  proxy user:  {PROXY_USER}", flush=True)
    print(f"  target:      {PROXY_TARGET}", flush=True)
    print(f"  session dur: {DURATION} min", flush=True)
    print(f"  retry:       {'on' if ROLLING_RETRY else 'off'}  triggers={', '.join(RETRY_TRIGGERS)}", flush=True)
    print(f"  csv:         {csv_path}", flush=True)
    print("=" * 70, flush=True)

    job_q: queue.Queue = queue.Queue()
    for j in jobs:
        job_q.put(j)

    ok_count = 0
    err_count = 0
    count_lock = threading.Lock()
    t0 = time.time()
    total = len(jobs)

    def worker(worker_id: int) -> None:
        nonlocal ok_count, err_count
        while True:
            try:
                job = job_q.get(block=False)
            except queue.Empty:
                return
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            biz = (job.get("biz_name") or "")[:25]
            plat = job.get("platform") or "?"
            print(f"  [{ts} w{worker_id}] START   {plat:11s} biz={biz}", flush=True)
            try:
                row = dispatch_one(job, csv_path=csv_path)
            except Exception as e:
                print(
                    f"  [{ts} w{worker_id}] EXC     {type(e).__name__}: {e}",
                    flush=True,
                )
                row = None
            done_ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            with count_lock:
                done = ok_count + err_count + 1
                if row and row.get("status") == "success":
                    ok_count += 1
                    rate = 100 * ok_count / done
                    print(
                        f"  [{done_ts} w{worker_id}] OK      {plat:11s} {biz} "
                        f"dur={row.get('duration_s')}s ip={row.get('proxy_ip','-')[:18]} | "
                        f"{done}/{total} done | ok={ok_count} ({rate:.0f}%)",
                        flush=True,
                    )
                else:
                    err_count += 1
                    step = (row.get("failure_step") if row else "no-result") or ""
                    rate = 100 * ok_count / done
                    print(
                        f"  [{done_ts} w{worker_id}] ERR     {plat:11s} {biz} "
                        f"step={step[:25]} | {done}/{total} done | ok={ok_count} ({rate:.0f}%)",
                        flush=True,
                    )
            time.sleep(SLEEP_BETWEEN_JOBS_S)

    threads = []
    for i in range(MAX_PARALLEL):
        t = threading.Thread(target=worker, args=(i + 1,), daemon=False)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    elapsed = time.time() - t0
    print(
        f"\nDone. {total} jobs | OK={ok_count} ERR={err_count} | "
        f"{elapsed/60:.1f} min | {csv_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
