#!/usr/bin/env python3
"""Publish synthetic DAILY JobRecords directly to the consumer's queue (RabbitMQ).

Bypasses the orchestrator + scheduler + Postgres entirely — this is a smoke test
for the consumer → phone path. Useful for local single-Mac testing without
bringing the whole aeolocal stack up.

Default: publishes 3 DAILY jobs, one per platform, to localhost RabbitMQ
(matches the consumer's local-broker defaults).

Usage:
    # 3 jobs, one per platform, against localhost RabbitMQ (admin/admin)
    python3 test_publish_dummy.py

    # 10 jobs against the dev broker
    RABBITMQ_HOST=3.212.68.223 RABBITMQ_USERNAME=devicemanager \
      RABBITMQ_PASSWORD='your-pass' python3 test_publish_dummy.py --count 10

    # 1 audit (RANKING) job for end-to-end audit verification
    python3 test_publish_dummy.py --type RANKING --count 1

Companion: the consumer must be running with `TEST_MODE=1` env so the synthesized
prompts in this script are used directly (without calling AEOAdmin's
/api/llm/build-session).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone

import pika

# ── Broker (override via env) ──────────────────────────────────────────────
RABBITMQ_HOST     = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT     = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USERNAME = os.environ.get("RABBITMQ_USERNAME", "admin")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "admin")
RABBITMQ_VHOST    = os.environ.get("RABBITMQ_VHOST", "/")

# Default-exchange routing-key shortcut: route by exact queue name.
QUEUE_NAME = "local_device_manager_jobs_queue"

# ── Sample businesses (real names from clients.json, safe for live AI calls) ─
BUSINESSES = [
    {
        "businessName": "Mae's Childcare",
        "clientName":   "Mae's Childcare LLC",
        "clientId":     "dummy-mae",
        "addressLine1": "1234 Bilingual Way",
        "city":         "San Francisco",
        "state":        "California",
        "stateCode":    "CA",
        "gmb":          {"id": 1, "name": "https://maes.example.com", "type": "GMB"},
    },
    {
        "businessName": "Acme Plumbing Co",
        "clientName":   "Acme Plumbing LLC",
        "clientId":     "dummy-acme",
        "addressLine1": "500 Pipe Street",
        "city":         "Austin",
        "state":        "Texas",
        "stateCode":    "TX",
        "gmb":          {"id": 2, "name": "https://acme-plumbing.example.com", "type": "GMB"},
    },
    {
        "businessName": "Garcia Auto Body",
        "clientName":   "Garcia Auto Body Inc",
        "clientId":     "dummy-garcia",
        "addressLine1": "1800 Repair Ave",
        "city":         "Los Angeles",
        "state":        "California",
        "stateCode":    "CA",
        "gmb":          {"id": 3, "name": "https://garcia-auto.example.com", "type": "GMB"},
    },
]

KEYWORDS = ["best plumber near me", "emergency child care", "auto body repair"]
PLATFORMS = ("chatgpt", "gemini", "perplexity")


def build_daily_job(job_id: int, biz: dict, keyword: str, platform: str) -> dict:
    """Synthesize the orchestrator-hydrated DAILY JobRecord shape.

    Mirrors what the real orchestrator emits — see
    `solace_consumer.py:enrich_and_handle` for the parsing logic.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": job_id,
        "status": "PENDING",
        "type": "DAILY",
        "targetDate": now,
        "retryAttempts": 1,
        "platform": platform.lower(),
        "campaign": {
            "id": 90_000_000 + job_id,
            "subscriptionId": None,
            "openingTime": "08:00:00",
            "closingTime": "23:59:59",
            "business": biz,
            "address": {
                "addressLine1": biz["addressLine1"],
                "city": biz["city"],
                "state": biz["state"],
                "stateCode": biz["stateCode"],
            },
        },
        "detail": {
            "keyword": {"id": 99_000_000 + job_id, "name": keyword},
            "backlink": {"status": False, "url": ""},
        },
        "conversation": {
            "platform": platform.lower(),
            "status": False,
            "prompts": [
                {"id": 1, "prompt": (
                    f"Friend mentioned {biz['businessName']} over near "
                    f"{biz['addressLine1']} in {biz['city']} — they actually any good when "
                    f"it comes to {keyword}?"
                )},
            ],
        },
        # Top-level platform too — consumer falls back to it if conversation.platform missing
        "voice": "dummy",
        "variantText": "",
        "variantId": None,
        "backlinkInjected": False,
        "backlinkUrl": "",
    }


def build_audit_job(job_id: int, biz: dict, keyword: str, platform: str | None = None) -> dict:
    """Synthesize the RANKING (audit) JobRecord shape."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": job_id,
        "status": "PENDING",
        "type": "RANKING",
        "targetDate": now,
        "retryAttempts": 1,
        "platform": (platform or "gemini").lower(),
        "campaign": {
            "id": 90_000_000 + job_id,
            "openingTime": "08:00:00",
            "closingTime": "23:59:59",
            "business": biz,
            "address": {
                "addressLine1": biz["addressLine1"],
                "city": biz["city"],
                "state": biz["state"],
                "stateCode": biz["stateCode"],
            },
        },
        "detail": {
            "keyword": {"id": 99_000_000 + job_id, "name": keyword},
        },
        # Audit-specific top-level fields the consumer's _handle_audit reads
        "bizName": biz["businessName"],
        "bizUrl": biz["gmb"]["name"],
        "city": biz["city"],
        "state": biz["stateCode"],
        "keyword": keyword,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3,
                    help="Number of jobs to publish (default 3)")
    ap.add_argument("--type", choices=["DAILY", "RANKING"], default="DAILY",
                    help="Job type (default DAILY)")
    ap.add_argument("--platform", choices=list(PLATFORMS) + ["all"], default="all",
                    help="Pin to one platform, or 'all' to cycle (default all)")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for deterministic job IDs")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"[publish] broker amqp://{RABBITMQ_HOST}:{RABBITMQ_PORT}{RABBITMQ_VHOST}", flush=True)
    print(f"[publish] queue: {QUEUE_NAME}", flush=True)
    print(f"[publish] count={args.count}  type={args.type}  platform={args.platform}", flush=True)

    creds = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST, port=RABBITMQ_PORT, virtual_host=RABBITMQ_VHOST,
        credentials=creds, heartbeat=30, blocked_connection_timeout=10,
    )
    conn = pika.BlockingConnection(params)
    try:
        ch = conn.channel()
        # Ensure queue exists (idempotent) — production setup uses rabbitmq-init.sh
        # to bind it to an exchange; default exchange routes by queue name so
        # we publish with exchange='' to avoid depending on the exchange wiring.
        ch.queue_declare(queue=QUEUE_NAME, durable=True)

        platforms_cycle = (
            [args.platform] if args.platform != "all" else list(PLATFORMS)
        )
        jid_base = int(time.time())

        for i in range(args.count):
            biz     = BUSINESSES[i % len(BUSINESSES)]
            keyword = KEYWORDS[i % len(KEYWORDS)]
            plat    = platforms_cycle[i % len(platforms_cycle)]
            jid     = jid_base + i

            if args.type == "DAILY":
                job = build_daily_job(jid, biz, keyword, plat)
            else:
                job = build_audit_job(jid, biz, keyword, plat)

            body = json.dumps(job).encode("utf-8")
            ch.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # persistent
                ),
            )
            print(f"  [{i+1:>2d}/{args.count}] published job_id={jid} type={args.type} "
                  f"platform={plat} biz='{biz['businessName']}' kw='{keyword}'", flush=True)
    finally:
        conn.close()

    print(f"[publish] done — start the consumer (with TEST_MODE=1) to drain", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
