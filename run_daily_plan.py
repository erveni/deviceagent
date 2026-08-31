#!/usr/bin/env python3
"""Daily plan runner for device-agent fleet (10 devices, port forwards 8765-8774)."""

import json, sys, time, csv, os, subprocess, threading
from urllib.parse import urlparse
from datetime import datetime, timezone

PLAN_PATH = sys.argv[1] if len(sys.argv) > 1 else "/Users/seolocalph/projects/aeo-appium/daily_plan_2026-05-04.json"
OUTPUT_CSV = os.path.splitext(PLAN_PATH)[0] + "_results.csv"
BASE_PORT = 8765

DEVICES = [
    # NOTE: reserved for Copilot/Edge automation dev — see run_with_proxy.py DEVICES.
    # ("device-101", "R83L112EVWK"),
    ("device-102", "adb-10HFBBFEBZ000RA-dvvJ3y._adb-tls-connect._tcp"),
    ("device-103", "adb-149145555W001028-XsQtPA._adb-tls-connect._tcp"),
    ("device-104", "adb-149145555W002563-yWaJau._adb-tls-connect._tcp"),
    ("device-105", "adb-149145555W002883-aGtZ5h._adb-tls-connect._tcp"),
    ("device-106", "adb-149145555W005208-27c1FH._adb-tls-connect._tcp"),
    ("device-107", "adb-149145555W006477-JjonPV._adb-tls-connect._tcp"),
    ("device-108", "adb-149145555W006589-2W7yzb._adb-tls-connect._tcp"),
    ("device-109", "adb-149145555W006788-Vb9M0e._adb-tls-connect._tcp"),
    ("device-110", "adb-323952008165-D1lB1f._adb-tls-connect._tcp"),
]

try:
    import urllib.request
    def http_post(port, path, body=None):
        url = f"http://localhost:{port}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"} if data else {}, method="POST" if body else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            return {"status": "error", "error": str(e)}
except:
    http_post = lambda *a, **k: {"status": "error", "error": "no urllib"}

def extract_domain(url):
    try: return urlparse(url).netloc
    except: return url

def run(cmd):
    subprocess.run(cmd, shell=True, capture_output=True)

def setup_ports():
    run("adb forward --remove-all")
    for i, (_, serial) in enumerate(DEVICES):
        run(f"adb -s {serial} forward tcp:{BASE_PORT+i} tcp:8765")
        print(f"  {serial[:25]}... → :{BASE_PORT+i}")

def session(device_idx, job):
    """Run one job on one device. Returns result dict."""
    name, serial = DEVICES[device_idx]
    port = BASE_PORT + device_idx
    platform = job.get("platform", "chatgpt").lower()
    prompt = job.get("prompt", "")
    follow_up = job.get("follow_up", "") or None
    backlinks = job.get("backlinks", [])
    backlink_domain = extract_domain(backlinks[0]["url"]) if backlinks else ""
    t0 = time.time()

    # Fire
    resp = http_post(port, "/session", {
        "platform": platform,
        "prompt": prompt,
        "followUp": follow_up,
        "backlinkDomain": backlink_domain,
    })

    # Wait for completion (up to 5 min)
    for _ in range(40):
        time.sleep(8)
        resp = http_post(port, "/status")
        if resp.get("status") in ("completed", "error"):
            break

    duration = round(time.time() - t0, 1)
    status = resp.get("status", "?")
    error = resp.get("error", "") if status == "error" else ""
    backlink_found = resp.get("backlink_clicked", False)
    backlink_url = backlinks[0]["url"] if (backlink_found and backlinks) else ""

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "wave_index": 0,
        "client_id": job.get("client_id", ""),
        "client_name": job.get("client_name", ""),
        "biz_name": job.get("biz_name", ""),
        "campaign_id": job.get("campaign_id", ""),
        "keyword": job.get("keyword_text", ""),
        "prompt": prompt,
        "follow_up": follow_up or "",
        "has_follow_up": bool(follow_up),
        "device_id": name,
        "platform": platform,
        "status": "success" if status == "completed" and not error else "error",
        "duration_s": duration,
        "backlinks_expected": len(backlinks),
        "backlink_injected": job.get("backlink_injected", False),
        "backlink_found": backlink_found,
        "backlink_url": backlink_url,
        "failure_step": error,
        "error": error,
    }

def main():
    plan = json.load(open(PLAN_PATH))
    waves = plan["waves"]
    num_devices = len(DEVICES)

    print(f"Plan: {PLAN_PATH}  — {plan['total_jobs']} jobs, {len(waves)} waves")
    print(f"Devices: {num_devices}  |  Ports: {BASE_PORT}-{BASE_PORT+num_devices-1}\n")

    print("Port forwarding...")
    setup_ports()
    print()

    results = []
    job_count = 0

    for wi, wave in enumerate(waves):
        wave_num = wi + 1
        n = len(wave)
        print(f"── Wave {wave_num}/{len(waves)} ({n} jobs) ──", end=" ")

        # Assign jobs to devices round-robin, each device gets at most 1 per wave
        threads = []
        wave_results = [None] * n

        def run_wave_job(di, job, idx):
            wave_results[idx] = session(di, job)

        for i, job in enumerate(wave):
            di = i % num_devices
            t = threading.Thread(target=run_wave_job, args=(di, job, i))
            t.start()
            threads.append(t)
            job_count += 1

        for t in threads:
            t.join()

        # Print compact summary
        ok = sum(1 for r in wave_results if r and r["status"] == "success")
        bk = sum(1 for r in wave_results if r and r["backlink_found"])
        print(f"→ {ok}/{n} OK  backlinks={bk}")

        for r in wave_results:
            if r:
                r["wave_index"] = wave_num
                results.append(r)

    # Write CSV
    if results:
        fnames = ["timestamp","date","wave_index","client_id","client_name","biz_name",
                  "campaign_id","keyword","prompt","follow_up","has_follow_up",
                  "device_id","platform","status","duration_s",
                  "backlinks_expected","backlink_injected","backlink_found","backlink_url",
                  "failure_step","error"]
        with open(OUTPUT_CSV, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fnames); w.writeheader(); w.writerows(results)

        ok = sum(1 for r in results if r["status"] == "success")
        bk = sum(1 for r in results if r["backlink_found"])
        print(f"\n═══ DONE ═══")
        print(f"Total: {len(results)}  |  Success: {ok}  |  Failed: {len(results)-ok}")
        print(f"Backlinks found: {bk}/{len(results)}")
        print(f"Results: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
