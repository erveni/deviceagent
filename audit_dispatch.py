"""Audit (RANKING) dispatch — shells out to aeo-appium/audit.py.

The legacy production runner (`/Users/seolocalph/projects/aeo-appium/audit.py`)
is the source of truth for ranking-audit logic. It owns:
  * AEOAdmin /api/llm/build-audit (variant rotation)
  * gost + socksdroid + mock-location proxy setup (via proxy.py:setup_device)
  * ADB-driven Chrome flows (audit_chatgpt_adb / audit_gemini_adb / audit_perplexity_adb)
  * [RANK: X/Y] parser
  * IP-geo lookup
  * audit_results/audit_log.csv writer

We invoke it as a subprocess per Solace audit job — minimum coupling, no code
duplication. POOL is used only to prevent two audits hitting the same phone.

NOTE: today this only supports `--test` mode (TEST_CLIENT = Mae's Childcare) +
one platform per call. Production support for arbitrary clients requires a CLI
extension on aeo-appium side (accepting a JSON job spec) — separate ticket.
"""
from __future__ import annotations

import csv
import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from run_with_proxy import DEVICES
from device_dispatch import POOL  # share the device pool with daily

# aeo-appium has GostManager — required for per-job 1-IP-per-job dispatch
sys.path.insert(0, "/Users/seolocalph/projects/aeo-appium")
from gost_manager import GostManager  # noqa: E402

# Port allocator for per-job gost listeners. Each job grabs a unique port from
# this pool; releases on completion. Range chosen to not overlap with run_with_proxy.
_GOST_PORTS = list(range(16001, 16101, 2))  # 50 ports, 2 apart (gost uses 2 sequential)
_gost_port_lock = threading.Lock()
_gost_port_avail = list(_GOST_PORTS)
_gost_seq = itertools.count(1)


def _acquire_gost_port() -> int:
    with _gost_port_lock:
        if not _gost_port_avail:
            raise RuntimeError("no free gost port — too many concurrent audits")
        return _gost_port_avail.pop(0)


def _release_gost_port(p: int) -> None:
    with _gost_port_lock:
        _gost_port_avail.append(p)

AEO_APPIUM_DIR = "/Users/seolocalph/projects/aeo-appium"
AUDIT_SCRIPT = os.path.join(AEO_APPIUM_DIR, "audit.py")
AUDIT_LOG = os.path.join(AEO_APPIUM_DIR, "audit_results", "audit_log.csv")
AEO_APPIUM_ENV_FILE = os.path.join(AEO_APPIUM_DIR, ".env")
PYTHON3 = shutil.which("python3") or "/usr/bin/env python3"

# Clients catalog file passed to audit.py via --client-json.
# Override with env AUDIT_CLIENTS_JSON_PATH; default to aeo-appium/clients.json.
AUDIT_CLIENTS_JSON = os.environ.get(
    "AUDIT_CLIENTS_JSON_PATH",
    os.path.join(AEO_APPIUM_DIR, "clients.json"),
)

# Required by aeo-appium/audit.py:69 (`os.environ["EXECUTOR_TOKEN"]`).
# Same token used by device-agent's daily AEOAdmin call.
DEFAULT_EXECUTOR_TOKEN = os.environ.get("EXECUTOR_TOKEN", "")


def _build_subprocess_env() -> dict[str, str]:
    """Compose env for the audit.py subprocess: parent env + aeo-appium/.env + EXECUTOR_TOKEN."""
    env = dict(os.environ)
    if os.path.exists(AEO_APPIUM_ENV_FILE):
        with open(AEO_APPIUM_ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env.setdefault(key.strip(), value.strip())
    env.setdefault("EXECUTOR_TOKEN", DEFAULT_EXECUTOR_TOKEN)
    # Device Manager moved to host:8090 (port 8080 is now Solace SEMP UI).
    # Override regardless of what .env says.
    env["DEVICE_MANAGER_URL"] = os.environ.get(
        "DEVICE_MANAGER_URL", "http://localhost:8090"
    )
    # Skip Chrome-based IP preflight. Per proxy.py:673, it's a SOFT check that
    # is "unreliable under parallel load (CDP races on Android UiAutomator)".
    # Yesterday's standalone smoke proved skipping it doesn't impact correctness
    # — the in-flow "site can't be reached" handler catches genuinely broken
    # tunnels during the actual AI navigation.
    env["AEO_SKIP_PREFLIGHT"] = "1"
    return env

# Mapping from Solace JobRecord platform values to audit.py's CLI choices
PLATFORM_MAP = {
    "chatgpt": "ChatGPT",
    "gemini": "Gemini",
    "perplexity": "Perplexity",
}

AUDIT_CMD_TIMEOUT_S = 900  # 15 min — covers slow proxy + ChatGPT generation
ACQUIRE_TIMEOUT_S = 600

# Canonical audit CSV header — matches
# /Users/seolocalph/projects/aeo-appium/audit_results/audit_log.csv
CSV_FIELDS = [
    "timestamp",
    "client_id", "biz_name",
    "campaign_id", "campaign_name",
    "keyword", "platform", "mode",
    "device", "status", "duration_s",
    "rank_position", "rank_total", "mentioned", "rank_context",
    "screenshot", "response_text", "error",
    "proxy_ip", "proxy_city", "proxy_region", "proxy_zip",
    "prompt", "variant_id",
]

import threading
_csv_lock = threading.Lock()


def build_audit_dispatch_job(job_record: dict[str, Any]) -> dict[str, Any]:
    """Project Solace JobRecord onto the fields we need for audit dispatch.

    For --test mode the only field we actually pass to audit.py is `--platform`
    plus `--serial`. The other fields are kept for our local row + log line.
    """
    campaign = job_record.get("campaign") or {}
    business = campaign.get("business") or {}
    client = business.get("client") or {}
    address = campaign.get("address") or {}
    keyword = job_record.get("keyword") or {}
    return {
        "client_id": client.get("clientId", ""),
        "keyword_id": keyword.get("id"),
        "campaign_id": campaign.get("id", ""),
        "campaign_name": business.get("businessName", ""),
        "biz_name": business.get("businessName", ""),
        "biz_url": business.get("gmbUrl") or business.get("bizUrl") or "",
        "city": address.get("city", ""),
        "state": address.get("stateCode") or address.get("state") or "",
        "keyword": keyword.get("name", ""),
        "mode": (job_record.get("type") or "RANKING").lower(),
    }


def dispatch_audit_job(
    job: dict[str, Any],
    platform: str,
    csv_path: str | None = None,
    acquire_timeout: float | None = ACQUIRE_TIMEOUT_S,
) -> dict[str, Any]:
    """Shell out to aeo-appium/audit.py for one (job, platform) pair.

    Returns a CSV row dict reflecting the audit_log.csv row written by
    audit.py (or an error row if the subprocess failed).
    """
    POOL.setup_forwards()
    device_idx = POOL.acquire(timeout=acquire_timeout)
    if device_idx is None:
        row = _err_row(job, platform, "device-?", "device_pool_timeout: no idle device")
        if csv_path:
            append_row(csv_path, row)
        return row

    device_label, serial = DEVICES[device_idx]
    audit_platform = PLATFORM_MAP.get((platform or "").lower())
    if audit_platform is None:
        POOL.release(device_idx)
        row = _err_row(job, platform, device_label, f"unknown platform: {platform}")
        if csv_path:
            append_row(csv_path, row)
        return row

    pre_count = _count_csv_rows(AUDIT_LOG)
    started = datetime.now(timezone.utc)
    keyword_id = job.get("keyword_id")
    if keyword_id is None:
        POOL.release(device_idx)
        row = _err_row(job, platform, device_label, "missing keyword_id in job spec")
        if csv_path:
            append_row(csv_path, row)
        return row

    # Build a per-job clients.json snippet with proxy.gost populated so
    # audit.py's setup_device takes the gost branch (lines 405-410 of proxy.py)
    # instead of the broken Device-Manager-HTTP branch.
    try:
        with open(AUDIT_CLIENTS_JSON) as f:
            catalog = json.load(f)
    except Exception as e:
        POOL.release(device_idx)
        row = _err_row(job, platform, device_label,
                       f"could not read AUDIT_CLIENTS_JSON: {e}")
        if csv_path:
            append_row(csv_path, row)
        return row

    matched = None
    for entry in catalog:
        if any((isinstance(k, dict) and k.get("keyword_id") == keyword_id)
               for k in entry.get("keywords", [])):
            matched = entry
            break
    if matched is None:
        POOL.release(device_idx)
        row = _err_row(job, platform, device_label,
                       f"keyword_id {keyword_id} not found in {AUDIT_CLIENTS_JSON}")
        if csv_path:
            append_row(csv_path, row)
        return row

    # Start per-job gost listener (1 IP per audit).
    seq = next(_gost_seq)
    gost_key = f"audit-{seq}"
    port = _acquire_gost_port()
    biz_zip = (matched.get("proxy") or {}).get("zip", "") or "10001"
    state = matched.get("state", "")
    gost = GostManager(
        [{"device_id": gost_key, "zip": biz_zip, "state": state,
          "country": "us", "session_duration": 30}],
        base_port=port,
    )
    gost.start(wait_seconds=2.0)
    snippet_path = None
    try:
        entry_copy = json.loads(json.dumps(matched))
        entry_copy.setdefault("proxy", {})["gost"] = gost.mapping[gost_key]
        snippet_path = f"/tmp/audit_job_{seq}_{keyword_id}_{platform}.json"
        with open(snippet_path, "w") as f:
            json.dump([entry_copy], f)

        cmd = [
            PYTHON3, AUDIT_SCRIPT,
            "--keyword-id", str(keyword_id),
            "--client-json", snippet_path,
            "--platform", audit_platform,
            "--serial", serial,
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=AEO_APPIUM_DIR,
                env=_build_subprocess_env(),
                capture_output=True,
                text=True,
                timeout=AUDIT_CMD_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            row = _err_row(job, platform, device_label,
                           f"audit subprocess timeout after {AUDIT_CMD_TIMEOUT_S}s")
            if csv_path:
                append_row(csv_path, row)
            return row
        except Exception as e:
            row = _err_row(job, platform, device_label,
                           f"subprocess crashed: {type(e).__name__}: {e}")
            if csv_path:
                append_row(csv_path, row)
            return row
    finally:
        try:
            gost.stop()
        except Exception:
            pass
        _release_gost_port(port)
        if snippet_path:
            try:
                os.unlink(snippet_path)
            except Exception:
                pass
        POOL.release(device_idx)

    duration_s = round((datetime.now(timezone.utc) - started).total_seconds(), 1)

    audit_row = _read_new_audit_rows(AUDIT_LOG, pre_count, audit_platform, serial)
    if audit_row is None:
        tail = (proc.stderr or proc.stdout or "")[-300:]
        row = _err_row(job, platform, device_label,
                       f"no new audit_log row after subprocess (rc={proc.returncode}); tail: {tail}")
        if csv_path:
            append_row(csv_path, row)
        return row

    row = _normalize_row(job, platform, device_label, audit_row, duration_s, pre_count)
    if csv_path:
        append_row(csv_path, row)
    return row


def _count_csv_rows(path: str) -> int:
    """Count CSV data rows (excludes header). Respects quoted multi-line fields."""
    if not os.path.exists(path):
        return 0
    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return sum(1 for _ in reader)
    except Exception:
        return 0


def _read_new_audit_rows(
    path: str,
    pre_count: int,
    audit_platform: str,
    serial: str,
) -> dict[str, str] | None:
    """Return the last audit_log.csv row added by the subprocess that matches
    our (platform, serial). audit.py appends one row per platform×keyword×client."""
    if not os.path.exists(path):
        return None
    new_rows: list[dict[str, str]] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if idx >= pre_count:
                new_rows.append(row)
    matches = [
        r for r in new_rows
        if (r.get("platform") or "").lower() == audit_platform.lower()
        and serial[:30] in (r.get("device") or "")
    ]
    if matches:
        return matches[-1]
    return new_rows[-1] if new_rows else None


def _normalize_row(
    job: dict[str, Any],
    platform: str,
    device_label: str,
    audit_row: dict[str, str],
    duration_s: float,
    pre_count: int,
) -> dict[str, Any]:
    return {
        "timestamp": audit_row.get("timestamp")
                      or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "client_id": audit_row.get("client_id") or job.get("client_id", ""),
        "biz_name": audit_row.get("biz_name") or job.get("biz_name", ""),
        "campaign_id": audit_row.get("campaign_id") or job.get("campaign_id", ""),
        "campaign_name": audit_row.get("campaign_name") or job.get("campaign_name", ""),
        "keyword": audit_row.get("keyword") or job.get("keyword", ""),
        "platform": audit_row.get("platform") or platform,
        "mode": audit_row.get("mode") or job.get("mode", "adb"),
        "device": audit_row.get("device") or device_label,
        "status": audit_row.get("status") or "error",
        "duration_s": audit_row.get("duration_s") or duration_s,
        "rank_position": audit_row.get("rank_position", ""),
        "rank_total": audit_row.get("rank_total", ""),
        "mentioned": audit_row.get("mentioned", ""),
        "rank_context": (audit_row.get("rank_context") or "")[:200],
        "screenshot": audit_row.get("screenshot", ""),
        "response_text": audit_row.get("response_text", ""),
        "error": (audit_row.get("error") or "")[:200],
        "proxy_ip": audit_row.get("proxy_ip", ""),
        "proxy_city": audit_row.get("proxy_city", ""),
        "proxy_region": audit_row.get("proxy_region", ""),
        "proxy_zip": audit_row.get("proxy_zip", ""),
        "prompt": audit_row.get("prompt", ""),
        "variant_id": audit_row.get("variant_id", ""),
    }


def _err_row(
    job: dict[str, Any],
    platform: str,
    device_label: str,
    msg: str,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "client_id": job.get("client_id", ""),
        "biz_name": job.get("biz_name", ""),
        "campaign_id": job.get("campaign_id", ""),
        "campaign_name": job.get("campaign_name", ""),
        "keyword": job.get("keyword", ""),
        "platform": platform,
        "mode": job.get("mode", "adb"),
        "device": device_label,
        "status": "error",
        "duration_s": 0,
        "rank_position": "",
        "rank_total": "",
        "mentioned": "",
        "rank_context": "",
        "screenshot": "",
        "response_text": "",
        "error": msg[:200],
        "proxy_ip": "",
        "proxy_city": "",
        "proxy_region": "",
        "proxy_zip": "",
        "prompt": "",
        "variant_id": "",
    }


def append_row(csv_path: str, row: dict[str, Any]) -> None:
    write_header = not os.path.exists(csv_path)
    with _csv_lock:
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if write_header:
                w.writeheader()
            w.writerow(row)
