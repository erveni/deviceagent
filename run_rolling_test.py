"""Rolling 1-IP-per-job test runner.

Each phone runs jobs sequentially. Between jobs on the same phone, gost listener
and socksdroid VPN are torn down + restarted with a fresh Decodo session ID, so
each job gets a brand-new egress IP. Phones run in parallel via threads.

Usage:  python3 run_rolling_test.py <plan.json>
        # writes <plan>_rolling_results.csv next to the plan
"""
import csv, json, os, sys, threading, time, subprocess
from datetime import datetime, timezone

# Reuse helpers from run_with_proxy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_with_proxy import (
    DEVICES, BASE_GOST, DURATION, MAC_IP,
    PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASS, GOST_BIN,
    run, rsid, extract_domain, randomize_location,
    gost_start, gost_stop, socksdroid_connect, socksdroid_disconnect,
    wait_tunnel, mock_location, set_timezone, http_post,
    get_online_serials,
)

PLAN_PATH = sys.argv[1]
plan = json.load(open(PLAN_PATH))
all_jobs = [j for w in plan["waves"] for j in w]
print(f"plan: {len(all_jobs)} jobs total")

# only use phones that are currently ADB-online
adb_lines = subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout.splitlines()
online = {l.split("\t")[0] for l in adb_lines if "_adb-tls-connect" in l and "device" in l}
ACTIVE = [(name, ser) for (name, ser) in DEVICES if ser in online]
# Optional cap for small-batch tests: pass --max-phones N
if "--max-phones" in sys.argv:
    n = int(sys.argv[sys.argv.index("--max-phones") + 1])
    ACTIVE = ACTIVE[:n]
print(f"using phones: {len(ACTIVE)} -> {', '.join(n for n,_ in ACTIVE)}")
if not ACTIVE:
    print("no phones online — abort")
    sys.exit(1)

# round-robin job assignment to phones
assignments = {i: [] for i in range(len(ACTIVE))}
for idx, job in enumerate(all_jobs):
    assignments[idx % len(ACTIVE)].append(job)
print("job split per phone:", {ACTIVE[i][0]: len(jobs) for i, jobs in assignments.items()})

# Port forwards for device-agent http
run("adb forward --remove-all")
for i, (_, ser) in enumerate(ACTIVE):
    run(f'adb -s "{ser}" forward tcp:{8765+i} tcp:8765')

results = []
csv_lock = threading.Lock()
out_path = os.path.splitext(PLAN_PATH)[0] + "_rolling_results.csv"
FIELDS = ["timestamp","date","wave_index","client_id","client_name","biz_name",
          "search_address","campaign_id","campaign_name","keyword","keyword_variant","prompt",
          "follow_up","has_follow_up","device_id","platform","status","duration_s",
          "proxy_status","proxy_username","proxy_host","proxy_port",
          "base_latitude","base_longitude","mocked_latitude","mocked_longitude",
          "mocked_timezone","backlinks_expected","backlink_injected",
          "backlink_found","backlink_url","failure_step","error","setup_s"]

def save_csv():
    with csv_lock:
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(results)

def run_job_on_phone(slot, job, job_global_idx, total):
    name, ser = ACTIVE[slot]
    port = BASE_GOST + slot
    agent_port = 8765 + slot
    sid = rsid()
    upstream = f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}-country-us"
    spec = {"port": port, "upstream_user": upstream, "sid": sid}

    t_setup_start = time.time()

    # 1) start gost listener with fresh session ID
    gost_proc, gost_cfg = gost_start([spec])

    # 2) connect socksdroid
    socksdroid_connect(ser, port)
    time.sleep(3)  # let VPN stabilise

    # 3) wait tunnel
    tunnel_ok = wait_tunnel(ser)

    if not tunnel_ok:
        setup_s = round(time.time() - t_setup_start, 1)
        msg = f"[{job_global_idx}/{total}] {name} TUNNEL FAILED ({setup_s}s) — skipping job"
        print(msg)
        gost_stop(gost_proc, gost_cfg)
        socksdroid_disconnect(ser)
        return _result_row(slot, job, spec, {"status":"error","error":"tunnel down"}, 0.0, setup_s)

    # 3b) IP warmup — mimic wave's implicit settle time without curl probes.
    # In wave mode the slowest device-setup gives ~100s of idle time on this IP
    # before any HTTPS fires. Cold Decodo IPs benefit from that pause. Pure sleep
    # — zero traffic during these 60s, so no router/ISP load spike.
    time.sleep(60)
    setup_s = round(time.time() - t_setup_start, 1)

    # 4) mock location + timezone
    lat = job.get("biz_lat", 0) or 0
    lng = job.get("biz_lng", 0) or 0
    mlat, mlng = randomize_location(lat, lng) if (lat and lng) else (0, 0)
    if mlat: mock_location(ser, mlat, mlng)
    tz = job.get("biz_timezone", "")
    if tz: set_timezone(ser, tz)

    # 5) dispatch to device-agent
    platform = job.get("platform","chatgpt").lower()
    prompt = job.get("prompt","")
    follow_up = job.get("follow_up","") or None
    backlinks = job.get("backlinks",[])
    bk_domain = extract_domain(backlinks[0]["url"]) if backlinks else ""

    t_job_start = time.time()
    http_post(agent_port, "/session", {
        "platform": platform, "prompt": prompt,
        "followUp": follow_up, "backlinkDomain": bk_domain,
    })
    r = {"status":"unknown"}
    for _ in range(50):
        time.sleep(8)
        r = http_post(agent_port, "/status")
        if r.get("status") in ("completed","error"): break
    dur = round(time.time() - t_job_start, 1)

    # 6) tear down gost + socksdroid (1-IP-per-job!)
    socksdroid_disconnect(ser)
    gost_stop(gost_proc, gost_cfg)

    row = _result_row(slot, job, spec, r, dur, setup_s, mlat=mlat, mlng=mlng, tz=tz)
    status_emoji = "OK" if row["status"]=="success" else "ERR"
    bk = "Y" if row["backlink_found"] else "N"
    print(f"[{job_global_idx}/{total}] {name} {platform} {status_emoji} bk={bk} | setup={setup_s}s run={dur}s | sid={sid}")
    return row

def _result_row(slot, job, spec, r, dur, setup_s, mlat=0, mlng=0, tz=""):
    name = ACTIVE[slot][0]
    backlinks = job.get("backlinks",[])
    bk_url = backlinks[0]["url"] if (r.get("backlink_clicked") and backlinks) else ""
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "wave_index": 0,
        "client_id": job.get("client_id",""), "client_name": job.get("client_name",""),
        "biz_name": job.get("biz_name",""), "search_address": job.get("biz_address",""),
        "campaign_id": job.get("campaign_id",""), "campaign_name": job.get("campaign_name",""),
        "keyword": job.get("keyword_text",""), "keyword_variant": job.get("keyword_variant", job.get("keyword_text","")),
        "prompt": job.get("prompt",""),
        "follow_up": job.get("follow_up","") or "", "has_follow_up": bool(job.get("follow_up")),
        "device_id": name, "platform": job.get("platform","").lower(),
        "status": "success" if r.get("status")=="completed" and not r.get("error") else "error",
        "duration_s": dur, "proxy_status": "CONNECTED",
        "proxy_username": spec["upstream_user"],
        "proxy_host": MAC_IP, "proxy_port": spec["port"],
        "base_latitude": job.get("biz_lat",0) or 0,
        "base_longitude": job.get("biz_lng",0) or 0,
        "mocked_latitude": mlat, "mocked_longitude": mlng, "mocked_timezone": tz,
        "backlinks_expected": len(backlinks),
        "backlink_injected": job.get("backlink_injected",False),
        "backlink_found": r.get("backlink_clicked",False),
        "backlink_url": bk_url,
        "failure_step": r.get("error",""), "error": r.get("error",""),
        "setup_s": setup_s,
    }

deferred_lock = threading.Lock()
deferred_jobs = []  # jobs from offline phones, picked up by surviving workers at end

def phone_worker(slot, jobs):
    name, ser = ACTIVE[slot]
    print(f"[{name}] starting, {len(jobs)} jobs queued")
    for j_idx, job in enumerate(jobs):
        # Live-check phone before each job
        if ser not in get_online_serials():
            print(f"[{name}] OFFLINE — sleeping 30s before re-check")
            time.sleep(30)
            if ser not in get_online_serials():
                print(f"[{name}] STILL OFFLINE — deferring remaining {len(jobs)-j_idx} jobs")
                with deferred_lock:
                    deferred_jobs.extend(jobs[j_idx:])
                return
        gidx = (j_idx * len(ACTIVE)) + slot + 1
        row = run_job_on_phone(slot, job, gidx, len(all_jobs))
        with csv_lock: results.append(row)
        save_csv()
    print(f"[{name}] done")

def drain_deferred():
    """After all workers finish their assigned queues, surviving online phones
    pick up deferred jobs (from offline phones) one at a time."""
    while True:
        with deferred_lock:
            if not deferred_jobs:
                return
            job = deferred_jobs.pop(0)
        # Find first online phone in ACTIVE
        online = get_online_serials()
        slot = next((i for i, (_, s) in enumerate(ACTIVE) if s in online), None)
        if slot is None:
            print(f"[deferred] no online phones, abandoning {1 + len(deferred_jobs)} jobs")
            with deferred_lock:
                deferred_jobs.insert(0, job)  # put it back
            return
        row = run_job_on_phone(slot, job, 0, len(all_jobs))
        with csv_lock: results.append(row)
        save_csv()

t_start = time.time()
threads = []
for slot, jobs in assignments.items():
    t = threading.Thread(target=phone_worker, args=(slot, jobs), daemon=False)
    t.start()
    threads.append(t)
for t in threads: t.join()

# After main workers done, drain any deferred jobs on surviving phones
if deferred_jobs:
    print(f"\n[deferred] draining {len(deferred_jobs)} jobs from offline phones")
    drain_deferred()

elapsed = round((time.time() - t_start) / 60, 1)
ok = sum(1 for r in results if r["status"]=="success")
err = len(results) - ok
bk = sum(1 for r in results if r["backlink_found"])
print(f"\nDone. {len(results)} jobs | OK:{ok} Fail:{err} Bk:{bk} | {elapsed}min | {out_path}")
