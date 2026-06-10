#!/usr/bin/env python3
"""CitedLogic publisher — read the standing MASTER-jobs.csv, stamp today's UTC
date into the {DATE} placeholders, and publish one message per AI-engine row to
the citedlogic_jobs RabbitMQ queue for citedlogic_consumer.py to capture.

{DATE} = today in UTC (YYYY-MM-DD). datetime.now(timezone.utc) is the true UTC
date regardless of the Mac's local timezone — this is the fix for the handover's
"Mac date -u disagreed with AWS by a day" skew. Override with DATE=YYYY-MM-DD.

google-maps rows (125/500) are HELD — there is no Maps map-pack flow yet, so
publishing them would just churn the consumer. Only the 375 AI rows go out.

Usage:
  DRY_RUN=1 python3 citedlogic_publish.py                     # show plan, no publish
  set -a; source .env.dev; set +a; python3 citedlogic_publish.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone

import pika

CSV_PATH = os.environ.get("CL_CSV", "/Users/seolocal3/Downloads/citedlogic-MASTER-jobs.csv")
DATE = os.environ.get("DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
AI_ENGINES = {"chatgpt", "gemini", "perplexity"}

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USERNAME = os.environ.get("RABBITMQ_USERNAME", "admin")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "admin")
RABBITMQ_VHOST = os.environ.get("RABBITMQ_VHOST", "/")
QUEUE_NAME = os.environ.get("CL_QUEUE", "citedlogic_jobs")


def sub(s: str) -> str:
    return (s or "").replace("{DATE}", DATE)


def load_messages() -> tuple[list[dict], int]:
    """Return (ai_messages, held_gmaps_count). Messages have {DATE} resolved."""
    ai: list[dict] = []
    held = 0
    for r in csv.DictReader(open(CSV_PATH)):
        engine = r["engine"].strip().lower()
        if engine not in AI_ENGINES:
            held += 1
            continue
        ai.append({
            "jobId": sub(r["jobId"]),
            "engine": engine,
            "metro": r.get("metro", ""),
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
            "promptText": r["promptText"],
            "screenshotKey": sub(r["screenshotKey"]),
            "rawKey": sub(r["rawKey"]),
        })
    return ai, held


def main() -> None:
    messages, held = load_messages()
    print(f"CitedLogic publish | DATE={DATE} (UTC) | queue={QUEUE_NAME}", flush=True)
    print(f"  AI-engine rows to publish: {len(messages)}", flush=True)
    print(f"  google-maps rows HELD (no flow yet): {held}", flush=True)
    if messages:
        print(f"  sample jobId: {messages[0]['jobId']}", flush=True)
        print(f"  sample key  : {messages[0]['screenshotKey']}", flush=True)

    if DRY_RUN:
        print("\nDRY_RUN=1 — nothing published. Exiting.", flush=True)
        return

    if RABBITMQ_PASSWORD == "admin":
        print("  [warn] RABBITMQ_PASSWORD looks like the default — did you source .env.dev?", flush=True)

    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST,
        credentials=pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD),
    )
    conn = pika.BlockingConnection(params)
    try:
        channel = conn.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        persistent = pika.BasicProperties(delivery_mode=2, content_type="application/json")
        for n, msg in enumerate(messages, 1):
            channel.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=json.dumps(msg).encode("utf-8"),
                properties=persistent,
            )
            if n % 50 == 0 or n == len(messages):
                print(f"  published {n}/{len(messages)}", flush=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    print(f"\nDONE — {len(messages)} messages on {QUEUE_NAME}. Start citedlogic_consumer.py to capture.", flush=True)


if __name__ == "__main__":
    main()
