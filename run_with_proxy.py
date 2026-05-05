#!/usr/bin/env python3
"""Daily plan runner — rolling dispatch. Per-job proxy. CSV after every session."""

import json, sys, time, csv, os, subprocess, random, string, threading, math
from datetime import datetime, timezone
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque

PLAN_PATH = sys.argv[1] if len(sys.argv) > 1 else "/Users/seolocalph/projects/aeo-appium/daily_plan_2026-05-04.json"

GOST_BIN = "/opt/homebrew/bin/gost"
PROXY_HOST = "gate.decodo.com"
PROXY_PORT = 10001
PROXY_USER = "user-spmqebjuzf"
PROXY_PASS = "Klf0oAnRcz96Da=6fv"
DURATION = 30
BASE_GOST = 11001
MAC_IP = "192.168.0.102"

DEVICES = [
    ("device-101", "adb-R83L112EVWK-PydBnX._adb-tls-connect._tcp"),
    ("device-102", "adb-10HFBBFEBZ000RA-dvvJ3y._adb-tls-connect._tcp"),
    ("device-103", "adb-149145555W001028-XsQtPA (2)._adb-tls-connect._tcp"),
    ("device-104", "adb-149145555W002563-yWaJau (2)._adb-tls-connect._tcp"),
    ("device-105", "adb-149145555W002883-aGtZ5h (2)._adb-tls-connect._tcp"),
    ("device-106", "adb-149145555W005208-27c1FH (2)._adb-tls-connect._tcp"),
    ("device-107", "adb-149145555W006477-JjonPV (2)._adb-tls-connect._tcp"),
    ("device-108", "adb-149145555W006589-2W7yzb._adb-tls-connect._tcp"),
    ("device-109", "adb-149145555W006788-Vb9M0e (2)._adb-tls-connect._tcp"),
    ("device-110", "adb-1490455613010287-g9bnc8 (2)._adb-tls-connect._tcp"),
]

def run(cmd, timeout=30):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

def rsid(n=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def extract_domain(url):
    try: return urlparse(url).netloc
    except: return url

def randomize_location(lat, lng, r=5.0):
    rd_lat = r / 69.0
    rd_lng = r / (69.0 * math.cos(math.radians(lat)))
    a = random.uniform(0, 2*math.pi)
    d = random.uniform(0, 1)**0.5
    return (round(lat+d*rd_lat*math.sin(a),6), round(lng+d*rd_lng*math.cos(a),6))

def gost_start(specs):
    lines = ["services:"]
    for i, s in enumerate(specs):
        lines += [f'  - name: s{i}', f'    addr: ":{s["port"]}"',
                  f'    handler: {{type: socks5, chain: c{i}, auth: {{username: anon, password: anon}}}}',
                  f'    listener: {{type: tcp}}']
    lines.append("chains:")
    for i, s in enumerate(specs):
        lines += [f'  - name: c{i}', f'    hops:', f'      - name: h{i}', f'        nodes:',
                  f'          - name: d{i}', f'            addr: {PROXY_HOST}:{PROXY_PORT}',
                  f'            connector: {{type: socks5, auth: {{username: "{s["upstream_user"]}", password: "{PROXY_PASS}"}}}}',
                  f'            dialer: {{type: tcp}}']
    cfg = f"/tmp/gost_{os.getpid()}.yaml"
    with open(cfg, "w") as f: f.write("\n".join(lines)+"\n")
    proc = subprocess.Popen([GOST_BIN, "-C", cfg, "-D"], stdout=open(cfg+".log","w"), stderr=subprocess.STDOUT)
    time.sleep(2)
    if proc.poll() is not None: raise RuntimeError(f"gost died: {cfg}.log")
    return proc, cfg

def gost_stop(proc, cfg):
    if proc and proc.poll() is None: proc.terminate(); proc.wait(timeout=5)
    for p in (cfg, cfg+".log"):
        try: os.unlink(p)
        except: pass

def socksdroid_connect(serial, port):
    run(f"adb -s {serial} shell am force-stop net.typeblog.socks", 5)
    time.sleep(0.5)
    run(f"adb -s {serial} shell appops set net.typeblog.socks ACTIVATE_VPN allow", 5)
    run(f"adb -s {serial} shell am start -n net.typeblog.socks/.AdbStartActivity "
        f"-a net.typeblog.socks.ACTION_START_VPN --es SOCKSSERV \"{MAC_IP}\" --ei SOCKSPORT {port} "
        f"--es SOCKSUNAME \"anon\" --es SOCKSPASSWD \"anon\" --es SOCKSDNS \"8.8.8.8\" --es SOCKSROUTE \"all\"", 10)
    time.sleep(2)

def socksdroid_disconnect(serial):
    run(f"adb -s {serial} shell pm clear net.typeblog.socks", 10)
    time.sleep(1)

def wait_tunnel(serial):
    for _ in range(10):
        r = run(f"adb -s {serial} shell ifconfig tun0", 5)
        if "UP" in r.stdout and "inet" in r.stdout: return True
        time.sleep(2)
    return False

def mock_location(serial, lat, lng):
    if lat and lng:
        run(f"adb -s {serial} shell am start-foreground-service "
            f"-a com.blogspot.newapphorizons.fakegps.START "
            f"-e latitude {lat} -e longitude {lng}", 5)

def set_timezone(serial, tz):
    if tz:
        run(f"adb -s {serial} shell service call alarm 3 s16 \"{tz}\"", 5)

def http_post(port, path, body=None):
    import urllib.request
    url = f"http://localhost:{port}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type":"application/json"} if data else {}, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())
    except: return {"status":"error","error":"http fail"}

def session(device_idx, job, gost_spec):
    port = 8765 + device_idx
    platform = job.get("platform","chatgpt").lower()
    prompt = job.get("prompt","")
    follow_up = job.get("follow_up","") or None
    backlinks = job.get("backlinks",[])
    bk_domain = extract_domain(backlinks[0]["url"]) if backlinks else ""
    t0 = time.time()

    http_post(port, "/session", {"platform":platform,"prompt":prompt,"followUp":follow_up,"backlinkDomain":bk_domain})

    for _ in range(50):
        time.sleep(8)
        r = http_post(port, "/status")
        if r.get("status") in ("completed","error"): break

    dur = round(time.time()-t0, 1)
    base_lat = job.get("biz_lat",0) or 0
    base_lng = job.get("biz_lng",0) or 0
    mlat, mlng = randomize_location(base_lat, base_lng) if (base_lat and base_lng) else (0,0)
    tz = job.get("biz_timezone","")
    bk_url = backlinks[0]["url"] if (r.get("backlink_clicked") and backlinks) else ""

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "wave_index": 0,
        "client_id": job.get("client_id",""), "client_name": job.get("client_name",""),
        "biz_name": job.get("biz_name",""), "search_address": job.get("biz_address",""),
        "campaign_id": job.get("campaign_id",""), "campaign_name": job.get("campaign_name",""),
        "keyword": job.get("keyword_text",""), "prompt": prompt,
        "follow_up": follow_up or "", "has_follow_up": bool(follow_up),
        "device_id": DEVICES[device_idx][0], "platform": platform,
        "status": "success" if r.get("status")=="completed" and not r.get("error") else "error",
        "duration_s": dur, "proxy_status": "CONNECTED",
        "proxy_username": f"{PROXY_USER}-session-{gost_spec['sid']}-sessionduration-{DURATION}-country-us",
        "proxy_host": MAC_IP, "proxy_port": gost_spec["port"],
        "base_latitude": base_lat, "base_longitude": base_lng,
        "mocked_latitude": mlat, "mocked_longitude": mlng, "mocked_timezone": tz,
        "backlinks_expected": len(backlinks),
        "backlink_injected": job.get("backlink_injected",False),
        "backlink_found": r.get("backlink_clicked",False), "backlink_url": bk_url,
        "failure_step": r.get("error",""), "error": r.get("error",""),
    }

MAX_CONCURRENT = 10  # device-agent handles full concurrency without ADB bottleneck
STAGGER_SEC = 30     # delay between dispatching new jobs to avoid proxy burst
GOST_PORTS = list(range(11001, 11001 + MAX_CONCURRENT))  # port per concurrent job

def main():
    plan = json.load(open(PLAN_PATH))
    waves = plan["waves"]
    total = sum(len(w) for w in waves)
    out = os.path.splitext(PLAN_PATH)[0] + "_results.csv"

    # Flatten all jobs into a single queue with sequence numbers
    all_jobs = []
    seq = 0
    for wave in waves:
        for job in wave:
            seq += 1
            all_jobs.append((seq, job))
    print(f"Plan: {total} jobs across {len(waves)} waves — rolling dispatch (max {MAX_CONCURRENT} concurrent)")

    # Port forwards once
    run("adb forward --remove-all")
    for i, (_, ser) in enumerate(DEVICES):
        run(f"adb -s {ser} forward tcp:{8765+i} tcp:8765")

    # Load existing results if resuming
    results = []
    if os.path.exists(out):
        with open(out, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(row)
        print(f"Loaded {len(results)} existing results from {out}")

    grand_total = len(results) + total
    ok_cnt = sum(1 for r in results if r.get("status") == "success")
    bk_cnt = sum(1 for r in results if r.get("backlink_found") in ("True", True))
    t0 = time.time()
    csv_lock = threading.Lock()

    fns = ["timestamp","date","wave_index","client_id","client_name","biz_name",
           "search_address","campaign_id","campaign_name","keyword","prompt",
           "follow_up","has_follow_up","device_id","platform","status","duration_s",
           "proxy_status","proxy_username","proxy_host","proxy_port",
           "base_latitude","base_longitude","mocked_latitude","mocked_longitude",
           "mocked_timezone","backlinks_expected","backlink_injected",
           "backlink_found","backlink_url","failure_step","error"]

    def save_csv():
        with csv_lock:
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fns); w.writeheader(); w.writerows(results)

    # Rolling dispatch state
    job_queue = deque(all_jobs)
    device_pool = deque(range(len(DEVICES)))
    gost_port_pool = deque(GOST_PORTS)
    active_campaigns = set()  # campaign_ids currently running
    dispatch_seq = 0

    def run_one_job(device_idx, job, seq_num, gost_port):
        """Run a single job with its own proxy setup/teardown."""
        _, ser = DEVICES[device_idx]
        sid = rsid()
        spec = {"port": gost_port, "upstream_user": f"{PROXY_USER}-session-{sid}-sessionduration-{DURATION}-country-us", "sid": sid}
        gost_proc = gost_cfg = None
        try:
            gost_proc, gost_cfg = gost_start([spec])
            socksdroid_connect(ser, gost_port)
            if not wait_tunnel(ser):
                return error_result(job, device_idx, spec, seq_num, "tunnel failed")

            bl, bln = job.get("biz_lat", 0) or 0, job.get("biz_lng", 0) or 0
            if bl and bln:
                ml, mln = randomize_location(bl, bln)
                mock_location(ser, ml, mln)
            tz = job.get("biz_timezone", "")
            if tz:
                set_timezone(ser, tz)

            result = session(device_idx, job, spec)
            result["wave_index"] = seq_num
            return result
        except Exception as e:
            return error_result(job, device_idx, spec, seq_num, str(e))
        finally:
            try: socksdroid_disconnect(ser)
            except: pass
            if gost_proc:
                try: gost_stop(gost_proc, gost_cfg)
                except: pass

    def error_result(job, device_idx, spec, seq_num, error_msg):
        """Return an error result row when proxy setup fails."""
        dur = round(time.time() - t0, 1)
        return {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "wave_index": seq_num,
            "client_id": job.get("client_id", ""), "client_name": job.get("client_name", ""),
            "biz_name": job.get("biz_name", ""), "search_address": job.get("biz_address", ""),
            "campaign_id": job.get("campaign_id", ""), "campaign_name": job.get("campaign_name", ""),
            "keyword": job.get("keyword_text", ""), "prompt": job.get("prompt", ""),
            "follow_up": job.get("follow_up", "") or "", "has_follow_up": bool(job.get("follow_up", "")),
            "device_id": DEVICES[device_idx][0], "platform": job.get("platform", "chatgpt").lower(),
            "status": "error", "duration_s": dur, "proxy_status": "FAILED",
            "proxy_username": f"{PROXY_USER}-session-{spec['sid']}-sessionduration-{DURATION}-country-us",
            "proxy_host": MAC_IP, "proxy_port": spec["port"],
            "base_latitude": job.get("biz_lat", 0) or 0, "base_longitude": job.get("biz_lng", 0) or 0,
            "mocked_latitude": 0, "mocked_longitude": 0, "mocked_timezone": job.get("biz_timezone", ""),
            "backlinks_expected": len(job.get("backlinks", [])),
            "backlink_injected": job.get("backlink_injected", False),
            "backlink_found": False, "backlink_url": "",
            "failure_step": "proxy_setup", "error": error_msg,
        }

    def can_dispatch(job):
        cid = job.get("campaign_id", "")
        return not cid or cid not in active_campaigns

    def dispatch_next():
        nonlocal dispatch_seq
        if not job_queue or not device_pool or not gost_port_pool:
            return False
        for _ in range(len(job_queue)):
            seq_num, job = job_queue[0]
            if can_dispatch(job):
                job_queue.popleft()
                di = device_pool.popleft()
                gport = gost_port_pool.popleft()
                cid = job.get("campaign_id", "")
                if cid:
                    active_campaigns.add(cid)
                dispatch_seq += 1
                fut = executor.submit(run_one_job, di, job, seq_num, gport)
                futures[fut] = (di, cid, seq_num, gport)
                return True
            else:
                job_queue.rotate(-1)
        return False

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {}

        # Initial fill
        for _ in range(MAX_CONCURRENT):
            if not dispatch_next():
                break

        # Rolling: as each job completes, immediately dispatch next
        for fut in as_completed(futures):
            di, cid, seq_num, gport = futures.pop(fut)
            try:
                result = fut.result()
            except Exception as e:
                result = {"status": "error", "error": str(e), "device_id": DEVICES[di][0],
                          "platform": "?", "duration_s": 0, "backlink_found": False,
                          "failure_step": "executor", "wave_index": seq_num}

            # Return resources to pools
            device_pool.append(di)
            gost_port_pool.append(gport)
            if cid:
                active_campaigns.discard(cid)

            # Save immediately
            if result:
                results.append(result)
                is_ok = 1 if result["status"] == "success" else 0
                is_bk = 1 if result.get("backlink_found") else 0
                ok_cnt += is_ok
                bk_cnt += is_bk
                save_csv()
                elapsed = time.time() - t0
                rate = len(results) / elapsed if elapsed > 0 else 0
                eta = int((grand_total - len(results)) / rate / 60) if rate > 0 else 0
                print(f"[{len(results)}/{grand_total}] {result['device_id']} {result['platform']} {result['status']} bk={result['backlink_found']} | ok={ok_cnt} fail={len(results)-ok_cnt} bk_total={bk_cnt} | {result['duration_s']}s | ETA ~{eta}min")

            # Stagger then dispatch next
            if job_queue:
                time.sleep(STAGGER_SEC)
                dispatch_next()

    elapsed = time.time() - t0
    print(f"\nDone. {len(results)} jobs | OK:{ok_cnt} Fail:{len(results)-ok_cnt} Bk:{bk_cnt} | {elapsed/60:.0f}min | {out}")

if __name__ == "__main__":
    main()
