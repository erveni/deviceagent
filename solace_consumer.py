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

import itertools
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


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
    "/Users/seolocalph/projects/device-agent/solace_pilot_audit_results.csv",
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
    _dispatch_pool = ThreadPoolExecutor(
        max_workers=int(os.environ.get("DISPATCH_MAX_WORKERS", len(_DEVICES)))
    )

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


def _submit_daily_dispatch(job_record: dict, enriched: dict) -> None:
    if _dispatch_pool is None or _build_dispatch_job is None or _dispatch_one_job is None:
        return
    # Capacity check: bail if no phones are reachable. The orchestrator will
    # retry the job later; better than hanging the dispatcher on a dead phone.
    if not get_online_serials():
        print(f"  [skip daily] no phones online — NACKing job back to orchestrator", flush=True)
        publish_result(job_record, "FAILED")
        return
    dispatch_job = _build_dispatch_job(job_record, enriched)

    def runner():
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
        except Exception as e:
            print(f"  [err] dispatch crashed: {type(e).__name__}: {e}", flush=True)

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

        publish_result(job_record, final_status)

    _dispatch_pool.submit(runner)


def _submit_audit_dispatch(job_record: dict, platform: str) -> None:
    if _dispatch_pool is None or _build_audit_dispatch_job is None or _dispatch_audit_job is None:
        return
    if not get_online_serials():
        print(f"  [skip audit] no phones online — NACKing job back to orchestrator", flush=True)
        publish_result(job_record, "FAILED")
        return
    audit_job = _build_audit_dispatch_job(job_record)

    def runner():
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
        except Exception as e:
            print(f"  [err] audit dispatch crashed: {type(e).__name__}: {e}", flush=True)

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

        publish_result(job_record, final_status)

    _dispatch_pool.submit(runner)


def publish_result(job_record: dict, status: str) -> None:
    """Publish JobRecord back to RESULTS_TOPIC exchange with status flipped.

    Orchestrator's jobConsumer queue is bound to this exchange (cross-bind
    declared by rabbitmq-init.sh) and routes COMPLETED/FAILED to
    JobRepository.update(). Each call opens a one-shot connection so any
    background dispatch thread can publish safely (pika channels are not
    thread-safe; jobs complete ~1/min so the connection overhead is fine).
    """
    out = dict(job_record)
    out["status"] = status
    try:
        conn = pika.BlockingConnection(_publisher_params)
        try:
            ch = conn.channel()
            ch.basic_publish(
                exchange=RESULTS_TOPIC,
                routing_key=RESULTS_TOPIC,
                body=json.dumps(out).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                ),
            )
        finally:
            conn.close()
        print(f"  [result] job_id={out.get('id')} -> {status} on {RESULTS_TOPIC}", flush=True)
    except Exception as e:
        print(f"  [err] result publish failed: {type(e).__name__}: {e}", flush=True)


def enrich_and_handle(payload: str) -> None:
    try:
        job = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"  [warn] payload is not JSON: {e}; raw={payload[:200]!r}", flush=True)
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
        _handle_audit(job, platform)
        return

    if job_type not in DAILY_TYPES:
        print(f"  [warn] unknown job type {job_type}; falling back to DAILY enrichment", flush=True)

    if keyword_id is None:
        print(f"  [warn] daily job {job_id} missing keyword.id — publishing FAILED", flush=True)
        publish_result(job, "FAILED")
        return

    _handle_daily(job, keyword_id, platform)


def _build_enriched_from_job(job: dict, keyword_id: int, platform: str) -> dict:
    """For dummy/test JobRecords that already carry the prompt — synthesize the
    enriched dict the dispatch path expects, skipping AEOAdmin."""
    campaign = job.get("campaign") or {}
    biz = campaign.get("business") or {}
    client = biz.get("client") or {}
    addr = campaign.get("address") or {}
    # Real orchestrator payloads have keyword under detail.keyword; dummies have
    # it at top-level. Support both.
    kw_obj = job.get("keyword") or (job.get("detail") or {}).get("keyword") or {}
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
        "backlinkInjected": bool(job.get("backlinkInjected")),
        "backlinkUrl": job.get("backlinkUrl", ""),
        "backlinkType": "",
        "clientId": client.get("clientId") or client.get("clientName", ""),
        "clientName": client.get("clientName", ""),
        "bizName": biz.get("businessName", ""),
        "searchAddress": ", ".join(filter(None, [addr.get("addressLine1"), addr.get("city"), addr.get("state") or addr.get("stateCode")])),
        "campaignId": campaign.get("id", ""),
        "city": addr.get("city", ""),
        "state": addr.get("state") or addr.get("stateCode", ""),
    }


def _handle_daily(job: dict, keyword_id: int, platform: str) -> None:
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
            _submit_daily_dispatch(job, enriched)
        else:
            publish_result(job, "COMPLETED")
        return

    try:
        enriched = call_build_session(keyword_id, platform)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"  [err] build-session HTTP {e.code}: {body}", flush=True)
        publish_result(job, "FAILED")
        return
    except Exception as e:
        print(f"  [err] build-session call failed: {e}", flush=True)
        publish_result(job, "FAILED")
        return

    _log_enriched(enriched)

    if DISPATCH_ENABLED:
        _submit_daily_dispatch(job, enriched)
    else:
        publish_result(job, "COMPLETED")


def _handle_audit(job: dict, platform: str) -> None:
    campaign = job.get("campaign") or {}
    business = campaign.get("business") or {}
    address = campaign.get("address") or {}
    biz_name = business.get("businessName", "?")
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
            return

    if DISPATCH_ENABLED:
        _submit_audit_dispatch(job, platform)
    else:
        publish_result(job, "COMPLETED")


def _on_amqp_message(channel, method, properties, body: bytes) -> None:
    routing_key = method.routing_key
    print(f"[recv] routing_key={routing_key} bytes={len(body)}", flush=True)
    if not body:
        print("  [warn] empty body", flush=True)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return
    try:
        enrich_and_handle(body.decode("utf-8"))
    finally:
        # Always ack: dispatch is fire-and-forget via the thread pool; the
        # consumer's job is to hand the payload off, not wait for execution.
        # Result lands later via publish_result() on the .results exchange.
        channel.basic_ack(delivery_tag=method.delivery_tag)


def main() -> None:
    print(f"DISPATCH_ENABLED={DISPATCH_ENABLED} CSV={DISPATCH_CSV if DISPATCH_ENABLED else '<n/a>'}", flush=True)

    conn = pika.BlockingConnection(_publisher_params)
    print(f"connected to amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}{RABBITMQ_VHOST}", flush=True)

    channel = conn.channel()
    # Process one message at a time so dispatcher thread pool stays the
    # backpressure point (matches old Solace receive_async semantics).
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=_on_amqp_message, auto_ack=False)
    print(f"subscribed to queue: {QUEUE_NAME}", flush=True)
    print(f"publisher topic (results exchange): {RESULTS_TOPIC}", flush=True)
    print(f"build-session URL: {BUILD_SESSION_URL}", flush=True)

    def shutdown(*_):
        print("shutting down...", flush=True)
        try:
            channel.stop_consuming()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        if _dispatch_pool is not None:
            _dispatch_pool.shutdown(wait=False, cancel_futures=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    channel.start_consuming()


if __name__ == "__main__":
    main()
