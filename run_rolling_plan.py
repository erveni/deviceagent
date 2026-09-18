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
import os, subprocess
from pathlib import Path
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


VOICE_AGENT = Path(os.environ.get(
    "VOICE_AGENT_PATH",
    str(Path(__file__).resolve().parent.parent / "voice-search" / "agent" / "voice_agent.py"),
))
VOICE_OUTPUT_DIR = os.environ.get("VOICE_OUTPUT_DIR", "/tmp/device-agent-voice-results")


def _run_voice_session(job: dict, device_id: str, serial: str, spec: dict, wave_index: int) -> dict:
    """Run one voice job through the standalone voice-search executor.

    The device pool lease remains held by the caller for the whole subprocess,
    so typed and voice jobs cannot share a phone concurrently.
    """
    slot = job.get("daily_slot_id") or job.get("backfill_slot_id") or f"{job.get('date','')}-{job.get('campaign_id','')}-{job.get('keyword_id','')}"
    request_id = re.sub(r"[^A-Za-z0-9_-]+", "-", f"daily-{slot}")[:80]
    request = {
        "version": 1, "request_id": request_id, "mode": "voice",
        "platform": (job.get("platform") or "chatgpt").lower(),
        "phrase": job.get("prompt", ""), "device_serial": serial,
        "gost_port": int(spec.get("port", 0)),
        "proxy": {"enabled": os.environ.get("VOICE_PROXY_ENABLED", "1") == "1",
                   "target": PROXY_TARGET, "rounds": 1},
        "voice": {"engine": job.get("voiceConfig", {}).get("engine", "say"),
                  "realistic": bool(job.get("voiceConfig", {}).get("realistic", False))},
        "location": {k: job.get(src) for k, src in (("lat", "biz_lat"), ("lng", "biz_lng"), ("timezone", "biz_timezone")) if job.get(src) not in (None, "")},
        "expected_business": job.get("biz_name", ""),
        "expected_domain": (job.get("gmb_url") or "").split("//")[-1].split("/")[0],
    }
    out = Path(VOICE_OUTPUT_DIR); out.mkdir(parents=True, exist_ok=True)
    # A completed bundle is reusable under the stable slot ID. An interrupted
    # or failed bundle must receive an explicit retry suffix per voice-agent's
    # idempotency contract.
    prior = out / request_id / "result.json"
    if prior.exists() or (out / request_id / "request.json").exists():
        try:
            if json.loads(prior.read_text()).get("status") != "success":
                request_id = f"{request_id}-retry-{int(time.time())}"[:80]
        except Exception:
            request_id = f"{request_id}-retry-{int(time.time())}"[:80]
    request["request_id"] = request_id
    req_file = out / f"{request_id}.request.json"; req_file.write_text(json.dumps(request))
    started = time.time()
    try:
        proc = subprocess.run(["python3", str(VOICE_AGENT), "run", "--request", str(req_file), "--output-dir", str(out)],
                              capture_output=True, text=True, timeout=float(os.environ.get("VOICE_TIMEOUT_S", "300")))
        bundle = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {"status": "error", "error": proc.stderr[-1000:]}
    except Exception as exc:
        bundle = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    result = bundle.get("result") or {}
    ok = bundle.get("status") == "success" and bundle.get("exact") is True and result.get("answer_state") in (None, "complete", "completed", "done") and not bundle.get("error")
    row = _err_row(job, device_id, spec, wave_index, "voice_executor" if not ok else "", bundle.get("error", "") if not ok else "")
    row.update(status="success" if ok else "error", proxy_status="CONNECTED" if ok else "FAILED",
               duration_s=round(time.time() - started, 1),
               failure_step="" if ok else "voice_executor", voice_engine_requested=request["voice"]["engine"],
               voice_realistic_requested=request["voice"]["realistic"], recognized_prompt=bundle.get("recognized") or "",
               recognition_exact=bundle.get("exact"), voice_trace=bundle.get("voice_trace") or {})
    return row

from device_dispatch import (
    DEVICES, BASE_GOST, PROXY_USER, TUNNEL_SETTLE_S, RETRY_TRIGGERS,
    POOL, _run_session, _err_row, append_row,
)
from daily_prompt_plan import metadata as daily_metadata
from run_with_proxy import (
    gost_start, gost_stop, socksdroid_connect, socksdroid_disconnect,
    wait_tunnel, rsid, build_upstream_user,
)

MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", "3"))
# Copilot fails as a function of how many Copilot sessions are open at once from the
# same residential pool — measured 2026-09-04 on Evomi with the same phones: 1 in flight
# ~70% success, ~5 of 15 (base wave) 28-38%, ~15 (retry round, almost all Copilot) 8%,
# 8 simultaneous 0/7. ChatGPT/Gemini are unaffected by the same load. Cap Copilot
# in-flight fleet-wide; Chrome jobs keep the remaining phones busy.
COPILOT_MAX_PARALLEL = max(1, min(4, int(os.environ.get("COPILOT_MAX_PARALLEL", "4"))))
_COPILOT_SLOTS = threading.BoundedSemaphore(COPILOT_MAX_PARALLEL)
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
        **daily_metadata(j),
        "keyword_text": j.get("keyword_text") or j.get("keyword") or "",
        "keyword_variant": j.get("keyword_variant") or j.get("keyword_text") or "",
        "variant_id": j.get("variant_id"),
        "platform": (j.get("platform") or "chatgpt").lower(),
        "mode": (j.get("mode") or "type").lower(),
        # Optional browser routing for the mixed-browser rollout. Legacy jobs
        # remain Chrome by default; Edge is opt-in per job.
        "browser": (j.get("browser") or "chrome").lower(),
        "voiceConfig": j.get("voiceConfig") or j.get("voice_config") or {},
        "prompt": j.get("prompt", ""),
        "follow_up": j.get("follow_up", "") or "",
        "backlink_injected": bool(j.get("backlink_injected")),
        "backlinks": j.get("backlinks", []),
        "client_id": j.get("client_id", ""),
        "client_name": j.get("client_name", ""),
        "biz_name": j.get("biz_name", ""),
        "biz_address": j.get("biz_address", "") or j.get("search_address", ""),
        "biz_city": j.get("biz_city", ""),
        "biz_state": j.get("biz_state", ""),
        "biz_zip": j.get("biz_zip", ""),
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
        "upstream_user": build_upstream_user(sid),
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
    is_voice = job.get("mode", "type") == "voice"
    try:
        # Voice-search owns its own GOST/SocksDroid lifecycle. Starting the
        # typed tunnel here as well caused the voice executor's local listener
        # to collide and return `http fail`. Typed jobs retain the existing
        # DeviceAgent-owned tunnel path.
        if not is_voice:
            gost_proc, gost_cfg = gost_start([spec])
            socksdroid_connect(serial, spec["port"])
            time.sleep(TUNNEL_SETTLE_S)
        if not is_voice and not wait_tunnel(serial):
            row = _err_row(job, device_id, spec, wave_index, "tunnel_failed", "tunnel failed")
        else:
            if job.get("mode", "type") == "voice":
                row = _run_voice_session(job, device_id, serial, spec, wave_index)
            else:
                row = _run_session(job, device_idx, device_id, serial, spec, wave_index)
            err = (row.get("error") or "").lower()
            if ROLLING_RETRY and job.get("mode", "type") != "voice" and row.get("status") == "error" and any(t in err for t in RETRY_TRIGGERS):
                reason = next(t for t in RETRY_TRIGGERS if t in err).replace(" ", "_")
                # Zip-aware retry (mirrors device_dispatch.py b758d1b): instead of
                # repeating country-only US (which gave us the burned IP), target the
                # state's empirically-validated good Decodo zip. State parsed from
                # biz_address; NYC 10001 fallback if no parseable 'STATE ZIP' tail.
                from audit_dispatch_http import _STATE_GOOD_ZIP, _FALLBACK_GOOD_ZIP
                state = _parse_state(job.get("biz_address", ""))
                retry_zip = _STATE_GOOD_ZIP.get(state.upper(), _FALLBACK_GOOD_ZIP) if state else _FALLBACK_GOOD_ZIP
                print(
                    f"  [retry] {reason} on {device_id} — rotating proxy session, "
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
                    "upstream_user": build_upstream_user(sid, zip_=retry_zip, state=state),
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
        if not is_voice:
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
    if plan.get('daily_protocol') == 'eight-v1':
        from daily_prompt_plan import validate_typed_plan
        validate_typed_plan(plan)
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

    budget = None
    if any(j.get('daily_slot_id') or j.get('backfill_slot_id') for j in jobs):
        from daily_budget import DailyBudget
        budget = DailyBudget()
        if not budget.admit():raise SystemExit(3)
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
            if budget is not None and not budget.admit():return
            try:
                job = job_q.get(block=False)
            except queue.Empty:
                return
            is_copilot = (job.get("platform") or "").lower() == "copilot"
            if is_copilot and not _COPILOT_SLOTS.acquire(blocking=False):
                # Cap reached: hand this Copilot job back and take a non-Copilot one so
                # the phone keeps working. If the queue is all Copilot (retry rounds),
                # pace instead of spinning.
                job_q.put(job)
                time.sleep(3 if job_q.qsize() > MAX_PARALLEL else 15)
                continue
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
            finally:
                if is_copilot:
                    _COPILOT_SLOTS.release()
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
    if budget is not None and budget.stopped:raise SystemExit(3)


if __name__ == "__main__":
    main()
