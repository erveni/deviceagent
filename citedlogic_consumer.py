#!/usr/bin/env python3
"""CitedLogic RabbitMQ consumer — RabbitMQ → phone capture → OCR → S3 → ack.

A SEPARATE workflow from the AEO daily/ranking consumer (solace_consumer.py). It
only borrows the phone fleet + capture mechanism; it never touches AEOAdmin, the
catalog, or the DB. The only output is S3 (PNG + JSON per job).

Per message {jobId, engine, metro, lat, lng, promptText, screenshotKey, rawKey}:
  1. acquire a phone (shared audit_dispatch_http POOL; honours DEVICE_EXCLUDE)
  2. gost proxy targeting the metro + mock_location to the EXACT coords
  3. POST type=capture (verbatim prompt) → screenshot_b64 + answer text
  4. OCR-validate, decode PNG, build JSON
  5. upload BOTH to S3, then ACK. A failed capture/upload → nack/requeue so it
     retries (idempotent: a job whose two S3 objects already exist is skipped).

google-maps rows have no flow yet → acked + skipped (publisher already holds them
back, this is just a safety net).

Canonical start (env sourcing is MANDATORY — same pitfall as solace_consumer):
  cd ~/projects/device-agent
  set -a; source .env.dev; set +a
  WORKERS=6 DEVICE_EXCLUDE=105,107 \
  nohup python3 citedlogic_consumer.py > /tmp/citedlogic_consumer_$(date +%Y%m%d_%H%M%S).log 2>&1 &
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import pika

sys.path.insert(0, "/Users/seolocalph/projects/device-agent")
from citedlogic_capture import run_one  # noqa: E402

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USERNAME = os.environ.get("RABBITMQ_USERNAME", "admin")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "admin")
RABBITMQ_VHOST = os.environ.get("RABBITMQ_VHOST", "/")
QUEUE_NAME = os.environ.get("CL_QUEUE", "citedlogic_jobs")

WORKERS = int(os.environ.get("WORKERS", "6"))
HEARTBEAT_INTERVAL_S = int(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))

_params = pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    virtual_host=RABBITMQ_VHOST,
    credentials=pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD),
    heartbeat=600,
    blocked_connection_timeout=300,
)

# Fair-share gate: bound unacked-in-flight to phone capacity so a saturated Mac
# stops pulling and a second Mac on the same queue takes the slack.
_PHONE_SLOTS = threading.BoundedSemaphore(WORKERS)

_STATS_LOCK = threading.Lock()
_STATS = {"received": 0, "ok": 0, "skip": 0, "err": 0, "gmaps": 0, "last_completed_at": None}


def _stat_inc(field: str) -> None:
    with _STATS_LOCK:
        _STATS[field] = _STATS.get(field, 0) + 1
        if field in ("ok", "skip", "err", "gmaps"):
            _STATS["last_completed_at"] = datetime.now(timezone.utc).isoformat()


def _heartbeat_loop() -> None:
    while True:
        time.sleep(HEARTBEAT_INTERVAL_S)
        with _STATS_LOCK:
            s = dict(_STATS)
        in_flight = s["received"] - s["ok"] - s["skip"] - s["err"] - s["gmaps"]
        print(
            f"[heartbeat] ts={datetime.now(timezone.utc).isoformat()} "
            f"in_flight={in_flight} received={s['received']} ok={s['ok']} "
            f"skip={s['skip']} err={s['err']} gmaps={s['gmaps']} "
            f"last_completed={s['last_completed_at']}",
            flush=True,
        )


def _metro_from(msg: dict) -> str:
    """Metro for proxy-region derivation. Prefer the explicit field; fall back to
    the jobId ('{DATE}|atlanta-ga|p0|...') which always carries it second."""
    metro = (msg.get("metro") or "").strip()
    if metro:
        return metro
    parts = (msg.get("jobId") or "").split("|")
    return parts[1] if len(parts) > 1 else ""


def _job_view(msg: dict) -> dict:
    """Build the dict shape citedlogic_capture.run_one expects. The publisher has
    already resolved {DATE} in the keys, so they are used verbatim. `row` only
    feeds the synthetic keyword_id (phone-pool + screenshot naming) — derive a
    stable non-negative int from jobId so concurrent jobs don't collide."""
    job_id = msg.get("jobId") or ""
    row = sum(ord(c) for c in job_id) % 1_000_000
    return {
        "row": row,
        "jobId": job_id,
        "engine": (msg.get("engine") or "").strip().lower(),
        "metro": _metro_from(msg),
        "lat": float(msg["lat"]),
        "lng": float(msg["lng"]),
        "promptText": msg["promptText"],
        "screenshotKey": msg["screenshotKey"],
        "rawKey": msg["rawKey"],
    }


def _on_message(channel, method, properties, body: bytes) -> None:
    _stat_inc("received")
    delivery_tag = method.delivery_tag
    connection = channel.connection

    # ack/nack fire from a worker thread, so they must be marshalled back to the
    # pika I/O thread — a direct call from a worker corrupts the channel state.
    settled = threading.Event()

    def _settle(ack: bool, requeue: bool = False):
        if settled.is_set():
            return
        settled.set()
        try:
            if ack:
                connection.add_callback_threadsafe(
                    lambda: channel.basic_ack(delivery_tag=delivery_tag)
                )
            else:
                connection.add_callback_threadsafe(
                    lambda: channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
                )
        except Exception as e:
            print(f"  [err] settle schedule failed: {type(e).__name__}: {e}", flush=True)

    if not body:
        print("  [warn] empty body", flush=True)
        _settle(ack=True)
        return

    def _work():
        acquired = False
        try:
            msg = json.loads(body.decode("utf-8"))
            j = _job_view(msg)
            print(f"[recv] {j['jobId']} engine={j['engine']} metro={j['metro']}", flush=True)
            # ACK-AFTER-COMPLETION: hold the message unacked through the whole
            # capture so a crash/kill mid-flight re-delivers it (never lost).
            _PHONE_SLOTS.acquire()
            acquired = True
            kind, _, note = run_one(j)
            if kind in ("ok", "skip"):
                _stat_inc(kind)
                print(f"  [{kind}] {j['jobId']} {note}", flush=True)
                _settle(ack=True)
            elif kind == "gmaps_todo":
                _stat_inc("gmaps")
                print(f"  [gmaps] {j['jobId']} {note} — acking (no flow yet)", flush=True)
                _settle(ack=True)
            else:  # err — requeue so another phone retries (idempotent via S3)
                _stat_inc("err")
                print(f"  [err] {j['jobId']} {note} — requeue", flush=True)
                _settle(ack=False, requeue=True)
        except Exception as e:
            _stat_inc("err")
            print(f"  [err] work crashed: {type(e).__name__}: {e} — requeue", flush=True)
            _settle(ack=False, requeue=True)
        finally:
            if acquired:
                _PHONE_SLOTS.release()

    threading.Thread(target=_work, name="cl-capture", daemon=True).start()


_conn_state: dict = {"conn": None, "channel": None, "shutdown_requested": False}


def _consume_once() -> None:
    conn = pika.BlockingConnection(_params)
    print(f"connected to amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}{RABBITMQ_VHOST}", flush=True)
    channel = conn.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=WORKERS)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=_on_message, auto_ack=False)
    print(f"subscribed to queue: {QUEUE_NAME} (prefetch={WORKERS})", flush=True)
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
    print(f"CitedLogic consumer | queue={QUEUE_NAME} | workers={WORKERS}", flush=True)
    if RABBITMQ_PASSWORD == "admin":
        print("  [warn] RABBITMQ_PASSWORD looks like the default — did you source .env.dev?", flush=True)

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
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Auto-reconnect: AWS-hosted broker drops idle TCP; pika can't heartbeat while
    # a worker thread blocks the I/O thread, so start_consuming raises. Mirror
    # solace_consumer's backoff loop so the consumer survives broker blips.
    backoff = 2
    while not _conn_state["shutdown_requested"]:
        try:
            _consume_once()
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
            backoff = 2


if __name__ == "__main__":
    main()
