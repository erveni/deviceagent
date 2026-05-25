"""Subscribes to local_device_manager_jobs_queue (RabbitMQ), calls AEOAdmin
/api/llm/build-session to enrich each JobRecord, and either logs or dispatches
to a phone.

Run: ./venv-solace/bin/python solace_consumer.py
Stop: Ctrl-C

Modes:
  DISPATCH_ENABLED=0 (default) — log enriched payload only
  DISPATCH_ENABLED=1 — submit to device_dispatch.dispatch_one_job (real phone session)

Broker note: file name kept as `solace_consumer.py` for backward compatibility
with shell scripts/aliases; the broker switched to RabbitMQ on 2026-05-18
(upstream PR #4 orchestrator, #6 job-scheduler).
"""
from __future__ import annotations

import collections
import itertools
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


class CircuitBreaker:
    """Trip when recent dispatch outcomes look broken — avoid burning Decodo on a
    consistently failing setup (bad proxy account, account-wide app regression, etc.).

    Trips on EITHER:
      - rolling window: last N outcomes have >= fail_threshold failure rate
      - streak:         M consecutive failures
    When tripped, callers should publish FAILED without dispatching.
    Auto-resets after cooldown_s and re-arms with a fresh window.
    """

    def __init__(self, window_size: int = 20, fail_threshold: float = 0.5,
                 streak_size: int = 5, cooldown_s: int = 300) -> None:
        self._window: collections.deque[bool] = collections.deque(maxlen=window_size)
        self._streak = 0
        self._lock = threading.Lock()
        self._tripped_at: float | None = None
        self._trip_reason = ""
        self.window_size = window_size
        self.fail_threshold = fail_threshold
        self.streak_size = streak_size
        self.cooldown_s = cooldown_s

    def record(self, ok: bool) -> None:
        with self._lock:
            self._window.append(ok)
            self._streak = 0 if ok else self._streak + 1
            if self._tripped_at is not None:
                return
            if self._streak >= self.streak_size:
                self._trip(f"{self._streak} consecutive failures")
                return
            if len(self._window) >= self.window_size:
                fail_rate = 1.0 - (sum(self._window) / len(self._window))
                if fail_rate >= self.fail_threshold:
                    self._trip(f"{int(fail_rate*100)}% errors in last {self.window_size}")

    def _trip(self, reason: str) -> None:
        self._tripped_at = time.time()
        self._trip_reason = reason
        print(f"  [BREAKER TRIPPED] {reason} — halting dispatch for {self.cooldown_s}s", flush=True)

    def is_tripped(self) -> bool:
        with self._lock:
            if self._tripped_at is None:
                return False
            if time.time() - self._tripped_at >= self.cooldown_s:
                print(f"  [BREAKER RESET] cooldown elapsed, re-arming (was: {self._trip_reason})", flush=True)
                self._tripped_at = None
                self._trip_reason = ""
                self._window.clear()
                self._streak = 0
                return False
            return True


BREAKER = CircuitBreaker(
    window_size=int(os.environ.get("BREAKER_WINDOW", "20")),
    fail_threshold=float(os.environ.get("BREAKER_FAIL_RATE", "0.5")),
    streak_size=int(os.environ.get("BREAKER_STREAK", "5")),
    cooldown_s=int(os.environ.get("BREAKER_COOLDOWN_S", "300")),
)


# Heartbeat: visibility-only counters + periodic stdout line. Grep '[heartbeat]'
# in the consumer log to track live throughput / detect a stalled drain.
HEARTBEAT_INTERVAL_S = int(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))
_STATS_LOCK = threading.Lock()
_STATS = {"received": 0, "success": 0, "error": 0, "crashed": 0, "last_completed_at": None}

def _stat_inc(field: str) -> None:
    with _STATS_LOCK:
        _STATS[field] = _STATS.get(field, 0) + 1
        if field in ("success", "error"):
            _STATS["last_completed_at"] = datetime.now(timezone.utc).isoformat()

def _heartbeat_loop() -> None:
    while True:
        time.sleep(HEARTBEAT_INTERVAL_S)
        with _STATS_LOCK:
            s = dict(_STATS)
        in_flight = s["received"] - s["success"] - s["error"] - s["crashed"]
        print(
            f"[heartbeat] ts={datetime.now(timezone.utc).isoformat()} "
            f"in_flight={in_flight} received={s['received']} "
            f"success={s['success']} error={s['error']} crashed={s['crashed']} "
            f"last_completed={s['last_completed_at']}",
            flush=True,
        )


def get_online_serials() -> set[str]:
    """Return set of currently-adb-reachable phone serials (state == 'device').

    Used as a capacity check before submitting a job to the dispatch pool —
    if no phones are online, we publish FAILED back to the orchestrator
    instead of letting the dispatcher hang on a missing phone.
    """
    try:
        r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        out: set[str] = set()
        for ln in r.stdout.strip().split("\n")[1:]:
            ln = ln.rstrip()
            if ln.endswith("\tdevice"):
                out.add(ln[:-len("\tdevice")])
        return out
    except Exception:
        return set()

import pika

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USERNAME = os.environ.get("RABBITMQ_USERNAME", "admin")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "admin")
RABBITMQ_VHOST = os.environ.get("RABBITMQ_VHOST", "/")

QUEUE_NAME = "local_device_manager_jobs_queue"
# Result/status updates go BACK to the orchestrator's main inbound exchange
# (loopback pattern). Orchestrator's switch routes on JobRecord.status:
#   CREATED → publish to consumer; COMPLETED → save to DB; FAILED → retry.
# Per the upstream RabbitMQ migration (aeolocal commit c7eaf4e + orchestrator
# PR #4), there is NO separate `.results` exchange — consumer publishes to
# the same exchange that scheduler→orchestrator uses.
RESULTS_TOPIC = "local.client.business.campaign.keyword.jobs"

ADMIN_BASE = os.environ.get("ADMIN_BASE", "https://jjm59vpn3y.us-east-1.awsapprunner.com")
EXECUTOR_TOKEN = os.environ.get("EXECUTOR_TOKEN", "")
BUILD_SESSION_URL = f"{ADMIN_BASE}/api/llm/build-session"
HTTP_TIMEOUT = 30

PLATFORMS = ("chatgpt", "gemini", "perplexity")
_platform_cycle = itertools.cycle(PLATFORMS)

DISPATCH_ENABLED = os.environ.get("DISPATCH_ENABLED", "0") == "1"
TEST_MODE = os.environ.get("TEST_MODE", "0") == "1"
DISPATCH_CSV = os.environ.get(
    "DISPATCH_CSV",
    "/Users/seolocalph/projects/device-agent/solace_pilot_results.csv",
)
AUDIT_CSV = os.environ.get(
    "AUDIT_CSV",
    "/Users/seolocalph/projects/device-agent/rabbitmq_audit_results.csv",
)

DAILY_TYPES = {"DAILY"}
AUDIT_TYPES = {"RANKING", "INITIAL_RANKING"}

_dispatch_pool: ThreadPoolExecutor | None = None
_build_dispatch_job = None
_dispatch_one_job = None
_build_audit_dispatch_job = None
_dispatch_audit_job = None
if DISPATCH_ENABLED:
    from device_dispatch import (
        DEVICES as _DEVICES,
        build_dispatch_job as _build_dispatch_job,
        dispatch_one_job as _dispatch_one_job,
    )
    # AUDIT_DISPATCHER env: "http" (default — talks to com.deviceagent on phone:8765)
    #                       "subprocess" (legacy — shells out to aeo-appium/audit.py)
    _audit_mode = os.environ.get("AUDIT_DISPATCHER", "http").lower()
    if _audit_mode == "subprocess":
        from audit_dispatch import (
            build_audit_dispatch_job as _build_audit_dispatch_job,
            dispatch_audit_job as _dispatch_audit_job,
        )
    else:
        from audit_dispatch_http import (
            build_audit_dispatch_job as _build_audit_dispatch_job,
            dispatch_audit_job as _dispatch_audit_job,
        )
    _DISPATCH_MAX_WORKERS = int(os.environ.get("DISPATCH_MAX_WORKERS", len(_DEVICES)))
    _dispatch_pool = ThreadPoolExecutor(max_workers=_DISPATCH_MAX_WORKERS)
    # Fair-share gate: bounds how many messages we can hold unack'd at once.
    # Runner acquires this BEFORE acking the broker — so when all phones are
    # busy, RabbitMQ holds the next message back and (with multiple Macs
    # subscribed) routes it to whichever Mac has free capacity.
    _PHONE_SLOTS: threading.BoundedSemaphore | None = threading.BoundedSemaphore(_DISPATCH_MAX_WORKERS)
else:
    _DISPATCH_MAX_WORKERS = 1
    _PHONE_SLOTS = None

_publisher_params = pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    virtual_host=RABBITMQ_VHOST,
    credentials=pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD),
    heartbeat=30,
    blocked_connection_timeout=10,
)


def call_build_session(keyword_id: int, platform: str) -> dict:
    body = json.dumps({"keyword_id": keyword_id, "platform": platform}).encode("utf-8")
    req = urllib.request.Request(
        BUILD_SESSION_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Executor-Token": EXECUTOR_TOKEN,
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _log_enriched(enriched: dict) -> None:
    print(f"  variant_id={enriched.get('variantId')} voice={enriched.get('voice')} backlink={enriched.get('backlinkInjected')}", flush=True)
    print(f"  prompt: {enriched.get('prompt')!r}", flush=True)
    if enriched.get("hasFollowUp"):
        print(f"  follow: {enriched.get('followUp')!r}", flush=True)
    print(f"  biz: {enriched.get('bizName')} ({enriched.get('city')}, {enriched.get('state')})", flush=True)


def _submit_daily_dispatch(job_record: dict, enriched: dict, ack_callback) -> None:
    if _dispatch_pool is None or _build_dispatch_job is None or _dispatch_one_job is None:
        ack_callback()
        return
    if BREAKER.is_tripped():
        print(f"  [skip daily] circuit breaker tripped — publishing FAILED without burning Decodo", flush=True)
        publish_result(job_record, "FAILED")
        ack_callback()
        return
    # Capacity check: bail if no phones are reachable. The orchestrator will
    # retry the job later; better than hanging the dispatcher on a dead phone.
    if not get_online_serials():
        print(f"  [skip daily] no phones online — NACKing job back to orchestrator", flush=True)
        publish_result(job_record, "FAILED")
        ack_callback()
        return
    dispatch_job = _build_dispatch_job(job_record, enriched)

    def runner():
        # Fair-share: block until a phone slot is free, then ack the broker.
        # Until the ack fires the broker keeps this message marked "in flight" for
        # this Mac and refuses to deliver beyond prefetch — so a second Mac on
        # the same queue picks up the slack instead of sitting idle.
        _PHONE_SLOTS.acquire()
        ack_callback()
        final_status = "FAILED"
        conversation_happened = False
        backlink_clicked = False
        row = None
        try:
            row = _dispatch_one_job(dispatch_job, csv_path=DISPATCH_CSV)
            print(
                f"  [done daily] device={row['device_id']} platform={row['platform']} "
                f"status={row['status']} dur={row['duration_s']}s bk={row['backlink_found']}",
                flush=True,
            )
            final_status = "COMPLETED" if row.get("status") == "success" else "FAILED"
            conversation_happened = row.get("status") == "success"
            backlink_clicked = bool(row.get("backlink_found"))
            BREAKER.record(final_status == "COMPLETED")
            _stat_inc("success" if final_status == "COMPLETED" else "error")
        except Exception as e:
            print(f"  [err] dispatch crashed: {type(e).__name__}: {e}", flush=True)
            BREAKER.record(False)
            _stat_inc("crashed")

        # Update nested status fields so orchestrator persists the full outcome
        if isinstance(job_record.get("conversation"), dict):
            job_record["conversation"]["status"] = conversation_happened
        detail = job_record.get("detail") or {}
        if isinstance(detail.get("backlink"), dict):
            detail["backlink"]["status"] = backlink_clicked

        # Update proxy + mock location from the actual run row (if dispatch ran)
        if row is not None:
            device = job_record.get("device") or {}
            if isinstance(device.get("proxy"), dict):
                device["proxy"]["host"] = row.get("proxy_host", "") or ""
                device["proxy"]["port"] = int(row.get("proxy_port") or 0)
                device["proxy"]["username"] = row.get("proxy_username", "") or ""
            if isinstance(device.get("location"), dict):
                device["location"]["latitude"] = float(row.get("mocked_latitude") or 0)
                device["location"]["longitude"] = float(row.get("mocked_longitude") or 0)
            # Echo the actual phone serial used (helps trace which phone ran what)
            if "serialNo" in device:
                device["serialNo"] = row.get("device_id") or device.get("serialNo")
            # We consumed one retry attempt — decrement so orchestrator knows
            # how many tries remain (only when we actually dispatched).
            try:
                job_record["retryAttempts"] = max(0, int(job_record.get("retryAttempts", 0)) - 1)
            except (TypeError, ValueError):
                pass

        try:
            publish_result(job_record, final_status)
        finally:
            _PHONE_SLOTS.release()

    _dispatch_pool.submit(runner)


def _submit_audit_dispatch(job_record: dict, platform: str, ack_callback) -> None:
    if _dispatch_pool is None or _build_audit_dispatch_job is None or _dispatch_audit_job is None:
        ack_callback()
        return
    if BREAKER.is_tripped():
        print(f"  [skip audit] circuit breaker tripped — publishing FAILED without burning Decodo", flush=True)
        publish_result(job_record, "FAILED")
        ack_callback()
        return
    if not get_online_serials():
        print(f"  [skip audit] no phones online — NACKing job back to orchestrator", flush=True)
        publish_result(job_record, "FAILED")
        ack_callback()
        return
    audit_job = _build_audit_dispatch_job(job_record)

    def runner():
        _PHONE_SLOTS.acquire()
        ack_callback()
        final_status = "FAILED"
        audit_succeeded = False
        row = None
        try:
            row = _dispatch_audit_job(audit_job, platform=platform, csv_path=AUDIT_CSV)
            print(
                f"  [done audit] device={row['device']} platform={row['platform']} "
                f"status={row['status']} dur={row['duration_s']}s rank={row['rank_position']}/{row['rank_total']}",
                flush=True,
            )
            final_status = "COMPLETED" if row.get("status") == "success" else "FAILED"
            audit_succeeded = row.get("status") == "success"
            BREAKER.record(final_status == "COMPLETED")
            _stat_inc("success" if final_status == "COMPLETED" else "error")
        except Exception as e:
            print(f"  [err] audit dispatch crashed: {type(e).__name__}: {e}", flush=True)
            BREAKER.record(False)
            _stat_inc("crashed")

        # For audits, conversation.status reflects whether ranking was captured.
        if isinstance(job_record.get("conversation"), dict):
            job_record["conversation"]["status"] = audit_succeeded

        if row is not None:
            # Mirror daily-path updates: proxy details, mock location used, serial.
            device = job_record.get("device") or {}
            if isinstance(device.get("proxy"), dict):
                device["proxy"]["host"] = row.get("proxy_host", "") or ""
                device["proxy"]["port"] = int(row.get("proxy_port") or 0)
                device["proxy"]["username"] = row.get("proxy_username", "") or ""
            if isinstance(device.get("location"), dict):
                device["location"]["latitude"] = float(row.get("mocked_latitude") or 0)
                device["location"]["longitude"] = float(row.get("mocked_longitude") or 0)
            if "serialNo" in device:
                device["serialNo"] = row.get("device") or device.get("serialNo")

            # Ranking result goes into result.rankingRecord per JobRecord DTO.
            # row["response_text"] now holds a .txt file path (audit_results/<Platform>/kw*_<platform>_<TS>.txt)
            # containing the full LLM response — same pattern as row["screenshot"].
            kw_obj = job_record.get("detail", {}).get("keyword") or {}
            ranking_record = {
                "keywordId": kw_obj.get("id"),
                "platform": platform.upper(),
                "position": int(row.get("rank_position") or 0),
                "total": int(row.get("rank_total") or 0),
                "conversation": row.get("response_text") or row.get("rank_context") or "",
                "screenshot": row.get("screenshot") or row.get("screenshot_path") or "",
            }
            job_record["result"] = {"rankingRecord": ranking_record}

            # Consumed one retry — decrement so orchestrator can stop retrying after N.
            try:
                job_record["retryAttempts"] = max(0, int(job_record.get("retryAttempts", 0)) - 1)
            except (TypeError, ValueError):
                pass

        try:
            publish_result(job_record, final_status)
        finally:
            _PHONE_SLOTS.release()

    _dispatch_pool.submit(runner)


def publish_result(job_record: dict, status: str) -> None:
    """Publish JobRecord back to RESULTS_TOPIC exchange with status flipped.

    Orchestrator's jobConsumer queue is bound to this exchange (cross-bind
    declared by rabbitmq-init.sh) and routes COMPLETED/FAILED to
    JobRepository.update(). Each call opens a one-shot connection so any
    background dispatch thread can publish safely (pika channels are not
    thread-safe; jobs complete ~1/min so the connection overhead is fine).

    Retries on transient errors. AWS MQ drops idle TCP sockets every ~60s
    and the one-shot connect occasionally races that drop, raising
    AMQPConnectionError. Without retry the result is lost and the
    orchestrator's DB diverges from reality (measured on Mac-2 2026-05-25:
    142/402 publishes silently failed ≈ 35% loss rate).
    """
    out = dict(job_record)
    out["status"] = status
    body = json.dumps(out).encode("utf-8")
    last_err: Exception | None = None
    for attempt in range(5):
        if attempt > 0:
            time.sleep(2 ** (attempt - 1))  # 1, 2, 4, 8s
        try:
            conn = pika.BlockingConnection(_publisher_params)
            try:
                ch = conn.channel()
                ch.basic_publish(
                    exchange=RESULTS_TOPIC,
                    routing_key=RESULTS_TOPIC,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,  # persistent
                    ),
                )
            finally:
                conn.close()
            suffix = f" (recovered after {attempt} retries)" if attempt > 0 else ""
            print(f"  [result] job_id={out.get('id')} -> {status} on {RESULTS_TOPIC}{suffix}", flush=True)
            return
        except Exception as e:
            last_err = e
            if attempt < 4:
                print(f"  [warn] result publish attempt {attempt+1}/5 failed for job_id={out.get('id')}: {type(e).__name__}: {e}", flush=True)
    # All retries exhausted — grep '[LOST]' to find these.
    print(f"  [LOST] result publish FAILED after 5 attempts for job_id={out.get('id')} status={status}: {type(last_err).__name__}: {last_err}", flush=True)


def enrich_and_handle(payload: str, *, ack_callback) -> None:
    try:
        job = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"  [warn] payload is not JSON: {e}; raw={payload[:200]!r}", flush=True)
        ack_callback()
        return

    job_id = job.get("id")
    job_type = (job.get("type") or "DAILY").upper()
    # Real orchestrator payloads nest keyword under `detail.keyword`; dummy
    # publishers put it at top-level. Support both shapes.
    keyword = job.get("keyword") or (job.get("detail") or {}).get("keyword") or {}
    keyword_id = keyword.get("id")
    keyword_name = keyword.get("name", "?")
    campaign = job.get("campaign") or {}
    campaign_id = campaign.get("id")

    # Platform also has two homes: top-level on dummies, nested under
    # conversation.platform on real orchestrator payloads. Falls back to round-robin.
    explicit_platform = (
        job.get("platform")
        or (job.get("conversation") or {}).get("platform")
    )
    platform = (explicit_platform or next(_platform_cycle)).lower()
    print(f"  job_id={job_id} type={job_type} kid={keyword_id} kw='{keyword_name}' campaign={campaign_id} platform={platform}", flush=True)

    if job_type in AUDIT_TYPES:
        _handle_audit(job, platform, ack_callback)
        return

    if job_type not in DAILY_TYPES:
        print(f"  [warn] unknown job type {job_type}; falling back to DAILY enrichment", flush=True)

    if keyword_id is None:
        print(f"  [warn] daily job {job_id} missing keyword.id — publishing FAILED", flush=True)
        publish_result(job, "FAILED")
        ack_callback()
        return

    _handle_daily(job, keyword_id, platform, ack_callback)


def _build_enriched_from_job(job: dict, keyword_id: int, platform: str) -> dict:
    """For dummy/test JobRecords that already carry the prompt — synthesize the
    enriched dict the dispatch path expects, skipping AEOAdmin.

    Accepts both shapes:
      - OLD (pre-2026-05-24): business.businessName, business.clientId
      - NEW (2026-05-24+):    business.name, business.client.{clientName, accountId}
    """
    campaign = job.get("campaign") or {}
    biz = campaign.get("business") or {}
    client = biz.get("client") or {}
    addr = campaign.get("address") or {}
    kw_obj = job.get("keyword") or (job.get("detail") or {}).get("keyword") or {}
    # New shape: backlink is {id, url:{id,name,type}, status}; old: {url, status}
    detail = job.get("detail") or {}
    backlink_obj = detail.get("backlink") or {}
    backlink_url_obj = backlink_obj.get("url")
    if isinstance(backlink_url_obj, dict):
        backlink_url = backlink_url_obj.get("name", "")
    else:
        backlink_url = backlink_obj.get("url") or job.get("backlinkUrl", "")
    return {
        "keywordId": keyword_id,
        "keywordText": kw_obj.get("name", ""),
        "variantText": job.get("variantText", ""),
        "variantId": job.get("variantId"),
        "voice": job.get("voice", "dummy"),
        "platform": platform,
        "prompt": job.get("prompt", ""),
        "followUp": job.get("followUp", ""),
        "hasFollowUp": bool(job.get("followUp")),
        "backlinkInjected": bool(job.get("backlinkInjected") or backlink_obj.get("status")),
        "backlinkUrl": backlink_url,
        "backlinkType": "",
        "clientId": client.get("clientId") or client.get("accountId") or biz.get("clientId") or client.get("clientName", ""),
        "clientName": client.get("clientName", ""),
        "bizName": biz.get("businessName") or biz.get("name", ""),
        "searchAddress": ", ".join(filter(None, [addr.get("addressLine1"), addr.get("city"), addr.get("state") or addr.get("stateCode")])),
        "campaignId": campaign.get("id", ""),
        "city": addr.get("city", ""),
        "state": addr.get("state") or addr.get("stateCode", ""),
    }


def _handle_daily(job: dict, keyword_id: int, platform: str, ack_callback) -> None:
    # Orchestrator-hydrated payloads carry prompts at conversation.prompts[*].prompt
    # (PromptRecord = {id, prompt}). Lift them to top-level prompt/followUp so the
    # rest of this function keeps working unchanged.
    if not job.get("prompt"):
        prompts = ((job.get("conversation") or {}).get("prompts")) or []
        if prompts:
            job["prompt"] = (prompts[0] or {}).get("prompt") or ""
            if len(prompts) > 1:
                job["followUp"] = (prompts[1] or {}).get("prompt") or ""

    # TEST_MODE: synthesize a prompt from the keyword name and skip AEOAdmin.
    # Real orchestrator payloads have keyword under detail.keyword; dummies at
    # top-level. Check both before falling back to placeholder.
    if TEST_MODE and not job.get("prompt"):
        kw_obj = job.get("keyword") or (job.get("detail") or {}).get("keyword") or {}
        kw_name = kw_obj.get("name") or "test keyword"
        biz = (((job.get("campaign") or {}).get("business") or {}).get("businessName")
               or "this business")
        job["prompt"] = f"I heard {biz} is solid for {kw_name} — anyone with recent experience?"
        job["followUp"] = f"Cool, what should I look for when comparing options for {kw_name}?"
        print(f"  [TEST_MODE] synthesized prompt for kid={keyword_id} kw='{kw_name}'", flush=True)

    # If the JobRecord already carries a prompt (test/dummy publish), use it
    # directly and skip AEOAdmin.
    if job.get("prompt"):
        enriched = _build_enriched_from_job(job, keyword_id, platform)
        _log_enriched(enriched)
        if DISPATCH_ENABLED:
            _submit_daily_dispatch(job, enriched, ack_callback)
        else:
            publish_result(job, "COMPLETED")
            ack_callback()
        return

    try:
        enriched = call_build_session(keyword_id, platform)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"  [err] build-session HTTP {e.code}: {body}", flush=True)
        publish_result(job, "FAILED")
        ack_callback()
        return
    except Exception as e:
        print(f"  [err] build-session call failed: {e}", flush=True)
        publish_result(job, "FAILED")
        ack_callback()
        return

    _log_enriched(enriched)

    if DISPATCH_ENABLED:
        _submit_daily_dispatch(job, enriched, ack_callback)
    else:
        publish_result(job, "COMPLETED")
        ack_callback()


def _handle_audit(job: dict, platform: str, ack_callback) -> None:
    campaign = job.get("campaign") or {}
    business = campaign.get("business") or {}
    address = campaign.get("address") or {}
    # New orchestrator (2026-05-24+) uses business.name; old shape used businessName.
    biz_name = business.get("businessName") or business.get("name") or "?"
    # New orchestrator: business.gmb is a UrlRecord {id, name, type}. Old dummies put the URL string at gmbUrl/bizUrl.
    gmb_obj = business.get("gmb")
    biz_url = (
        (gmb_obj.get("name") if isinstance(gmb_obj, dict) else None)
        or business.get("gmbUrl")
        or business.get("bizUrl")
        or ""
    )
    city = address.get("city", "?")
    state = address.get("stateCode") or address.get("state") or "?"
    # Orchestrator nests keyword under detail.keyword; dummies use top-level keyword.
    keyword_obj = job.get("keyword") or (job.get("detail") or {}).get("keyword") or {}
    keyword_name = keyword_obj.get("name", "?")

    print(f"  audit: biz='{biz_name}' kw='{keyword_name}' loc={city},{state} url={biz_url or '<none>'}", flush=True)

    if not biz_name or not biz_url or not city or not state:
        print(f"  [warn] audit missing required fields (bizName/bizUrl/city/state) — phone will reject", flush=True)
        if not DISPATCH_ENABLED:
            publish_result(job, "FAILED")
            ack_callback()
            return

    if DISPATCH_ENABLED:
        _submit_audit_dispatch(job, platform, ack_callback)
    else:
        publish_result(job, "COMPLETED")
        ack_callback()


def _on_amqp_message(channel, method, properties, body: bytes) -> None:
    routing_key = method.routing_key
    print(f"[recv] routing_key={routing_key} bytes={len(body)}", flush=True)
    _stat_inc("received")
    delivery_tag = method.delivery_tag
    connection = channel.connection

    # Ack is fired from a worker thread once a phone slot is acquired (fair-share),
    # so it must be marshalled back to the pika I/O thread — direct basic_ack from
    # a worker corrupts the BlockingConnection channel state.
    acked = threading.Event()
    def _ack():
        if acked.is_set():
            return
        acked.set()
        try:
            connection.add_callback_threadsafe(
                lambda: channel.basic_ack(delivery_tag=delivery_tag)
            )
        except Exception as e:
            print(f"  [err] ack schedule failed: {type(e).__name__}: {e}", flush=True)

    if not body:
        print("  [warn] empty body", flush=True)
        _ack()
        return
    try:
        enrich_and_handle(body.decode("utf-8"), ack_callback=_ack)
    except Exception as e:
        # If enrich_and_handle blew up before any handler could schedule the ack,
        # ack here so RabbitMQ doesn't redeliver indefinitely.
        print(f"  [err] enrich_and_handle crashed: {type(e).__name__}: {e}", flush=True)
        _stat_inc("crashed")
        _ack()


# Connection state shared across reconnects so SIGINT/SIGTERM can close the live
# channel even after a reconnect has swapped it out.
_conn_state: dict = {"conn": None, "channel": None, "shutdown_requested": False}


def _consume_once() -> None:
    """One subscribe-and-consume cycle. Returns normally on broker disconnect
    (so the outer loop can reconnect); raises on shutdown."""
    conn = pika.BlockingConnection(_publisher_params)
    print(f"connected to amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}{RABBITMQ_VHOST}", flush=True)
    channel = conn.channel()
    # Prefetch matches phone capacity so the broker can hold up to N unack'd in
    # flight per Mac (fair-share). Combined with ack-after-acquire in the dispatch
    # runner, this means a saturated Mac stops pulling and another Mac on the same
    # queue picks up the slack instead of sitting idle.
    channel.basic_qos(prefetch_count=_DISPATCH_MAX_WORKERS)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=_on_amqp_message, auto_ack=False)
    print(f"subscribed to queue: {QUEUE_NAME}", flush=True)
    _conn_state["conn"] = conn
    _conn_state["channel"] = channel
    try:
        channel.start_consuming()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> None:
    print(f"DISPATCH_ENABLED={DISPATCH_ENABLED} CSV={DISPATCH_CSV if DISPATCH_ENABLED else '<n/a>'}", flush=True)
    print(f"publisher topic (results exchange): {RESULTS_TOPIC}", flush=True)
    print(f"build-session URL: {BUILD_SESSION_URL}", flush=True)

    threading.Thread(target=_heartbeat_loop, name="heartbeat", daemon=True).start()
    print(f"heartbeat: every {HEARTBEAT_INTERVAL_S}s — grep '[heartbeat]' in log", flush=True)

    def shutdown(*_):
        print("shutting down...", flush=True)
        _conn_state["shutdown_requested"] = True
        ch = _conn_state.get("channel")
        cn = _conn_state.get("conn")
        if ch is not None:
            try: ch.stop_consuming()
            except Exception: pass
        if cn is not None:
            try: cn.close()
            except Exception: pass
        if _dispatch_pool is not None:
            _dispatch_pool.shutdown(wait=False, cancel_futures=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Auto-reconnect loop. AWS MQ kills idle TCP after ~60s; pika BlockingConnection
    # can't send AMQP heartbeats while build-session is mid-call, so the broker
    # closes the socket and start_consuming raises StreamLostError. Without this
    # loop the process dies and the wave stalls. See PID 99381 + 81776 crashes
    # on 2026-05-23 — both StreamLostError ConnectionResetError(54).
    backoff = 2
    while not _conn_state["shutdown_requested"]:
        try:
            _consume_once()
            # _consume_once returned cleanly (no exception) — broker probably told
            # us to stop; bail out so we don't hot-loop.
            break
        except (pika.exceptions.StreamLostError,
                pika.exceptions.AMQPConnectionError,
                pika.exceptions.ConnectionClosed,
                pika.exceptions.ChannelClosed) as e:
            print(f"  [reconnect] broker connection lost: {type(e).__name__}: {e}; sleeping {backoff}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception as e:
            print(f"  [reconnect] unexpected error: {type(e).__name__}: {e}; sleeping {backoff}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        else:
            backoff = 2  # reset on clean cycle


if __name__ == "__main__":
    main()
