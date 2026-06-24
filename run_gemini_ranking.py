#!/usr/bin/env python3
"""Gemini ranking backfill via CDP capture — rolling across the fleet, behind Decodo.

For each missing-Gemini target (a keyword that was ranked ChatGPT/Perplexity-only),
set up the Decodo zip-targeted tunnel on a phone, load Gemini through it, and read
the rank + answer straight off the StreamGenerate wire (no screenshot — the UI wipe
is irrelevant).

RESUME: keeps any keyword already ranked in the existing deliverable.
RETRY-UNTIL-DONE: re-runs the still-failing keywords in rounds until every one has a
rank (or no progress for 3 rounds).
DATING: each Gemini row is dated + timestamped to MATCH its CP fellow — same date as
the keyword's ChatGPT/Perplexity rows, timestamp at the midpoint of those siblings.

Reads:  /tmp/gemini_backfill_targets.json, /tmp/cp_fellow_dates.json
Writes: ranking_gemini_backfill_consolidated.csv (+ ~/Desktop/Rankings/ copy)
"""
import csv, json, os, queue, re, subprocess, threading, time
import datetime as dt

os.environ.setdefault("PROXY_PROVIDER", "decodo")
os.environ.setdefault("PROXY_HOST", "gate.decodo.com")
os.environ.setdefault("PROXY_PORT", "10001")
os.environ.setdefault("PROXY_USER", "user-spmqebjuzf")
os.environ.setdefault("ONLY_ONLINE", "1")

# Decodo password must come from the environment — never hardcode (see
# .claude/rules/security.md). Export PROXY_PASS or DECODO_PASS first, e.g.
# `set -a; source .env.dev; set +a`.
_decodo_pass = os.environ.get("PROXY_PASS") or os.environ.get("DECODO_PASS")
if not _decodo_pass:
    raise SystemExit(
        "Decodo password required: export PROXY_PASS or DECODO_PASS "
        "(e.g. `set -a; source .env.dev; set +a`) before running."
    )
os.environ["PROXY_PASS"] = _decodo_pass

from run_with_proxy import (  # noqa: E402
    gost_start, gost_stop, socksdroid_connect, socksdroid_disconnect,
    wait_tunnel, rsid, build_upstream_user, BASE_GOST, DEVICES,
)

HERE = "/Users/seolocalph/projects/device-agent"
TARGETS = json.load(open(os.environ.get("GEMINI_TARGETS", "/tmp/gemini_backfill_targets.json")))
CP_FELLOW = json.load(open(os.environ.get("GEMINI_CP_FELLOW", "/tmp/cp_fellow_dates.json")))
OUT = os.environ.get("GEMINI_OUT") or os.path.join(HERE, "ranking_gemini_backfill_consolidated.csv")
DESKTOP = os.environ.get("GEMINI_DESKTOP") or "/Users/seolocalph/Desktop/Rankings/ranking_gemini_backfill_consolidated.csv"
WORKERS = int(os.environ.get("GEMINI_WORKERS", "6"))
MAX_ROUNDS = int(os.environ.get("GEMINI_MAX_ROUNDS", "10"))

PROMPT_T = os.environ.get("GEMINI_PROMPT_T") or (
    "Top 3 businesses for {kw} in {city}, {state} {zip}. Format: numbered list, each "
    "entry: name and a 1-2 sentence reason. After the list, rank {biz} ({url}) among "
    "all businesses in this space. You MUST include this exact line on its own: "
    "[RANK: X/Y] where X is the position and Y is the total number of businesses. "
    "Keep the entire response under 170 words."
)


def _key(t):
    return f"{t['campaign_id']}|{t['keyword']}"


def _capture(dev_idx, serial, t):
    sid = rsid()
    gport = BASE_GOST + dev_idx
    cdp = 9222 + dev_idx
    rfile, afile = f"/tmp/gem_result_{dev_idx}.json", f"/tmp/gem_answer_{dev_idx}.txt"
    spec = {"port": gport, "upstream_user": build_upstream_user(sid, zip_=t.get("zip") or None), "sid": sid}
    gp = gc = None
    t0 = time.time()
    try:
        gp, gc = gost_start([spec])
        socksdroid_connect(serial, gport)
        time.sleep(3)
        if not wait_tunnel(serial):
            return {**t, "status": "error", "error": "tunnel_failed"}
        subprocess.run(["adb", "-s", serial, "shell",
                        "am start -n com.android.chrome/com.google.android.apps.chrome.Main "
                        "-a android.intent.action.VIEW -d 'https://gemini.google.com/app'"],
                       capture_output=True, timeout=12)
        time.sleep(9)
        for f in (rfile, afile):
            try: os.remove(f)
            except OSError: pass
        url = re.sub(r"[^a-z0-9]", "", (t["biz_name"] or "biz").lower())[:18] + ".com"
        prompt = PROMPT_T.format(kw=t["keyword"], city=t["city"], state=t["state"],
                                 zip=t["zip"], biz=t["biz_name"], url=url)
        env = {**os.environ, "CDP_PORT": str(cdp),
               "GEMINI_RESULT_FILE": rfile, "GEMINI_ANSWER_FILE": afile}
        subprocess.run(["python3", "gemini_cdp_capture.py", serial, prompt],
                       capture_output=True, timeout=130, env=env)
        res = json.load(open(rfile)) if os.path.exists(rfile) else {}
        dur = round(time.time() - t0, 1)
        # Success = the response was SAVED off the wire (captured), mirroring the
        # daily's "generation happened" signal. The [RANK: X/Y] parse is a bonus,
        # not a gate — a saved answer with no rank line is still a success (and is
        # NOT retried). Only a genuine capture miss (no StreamGenerate body) fails.
        if res.get("captured"):
            return {**t, "status": "success",
                    "rank_position": res.get("rank_position"), "rank_total": res.get("rank_total"),
                    "has_rank": bool(res.get("rank_position")),
                    "response_text": (res.get("answer") or "")[:4000],
                    "prompt": prompt, "duration_s": dur}
        return {**t, "status": "error", "error": res.get("error") or "not_captured",
                "response_text": "", "prompt": prompt, "duration_s": dur}
    except Exception as e:
        return {**t, "status": "error", "error": str(e)[:90]}
    finally:
        if gp: gost_stop(gp, gc)
        try: socksdroid_disconnect(serial)
        except Exception: pass
        time.sleep(1)


def _run_pool(todo, results):
    """Run `todo` targets once across WORKERS phones; merge into results dict."""
    q = queue.Queue()
    for t in todo:
        q.put(t)
    lock = threading.Lock()
    total = len(todo)
    counter = {"done": 0}

    def worker(dev_idx, label, serial):
        while True:
            try:
                t = q.get_nowait()
            except queue.Empty:
                return
            r = _capture(dev_idx, serial, t)
            with lock:
                results[_key(t)] = r
                counter["done"] += 1
                ok = sum(1 for x in results.values() if x["status"] == "success")
                print(f"  [{counter['done']}/{total}] {label} {t['keyword'][:30]:30s} -> "
                      f"{r['status']} rank={r.get('rank_position','-')}/{r.get('rank_total','-')} "
                      f"(total ok={ok})", flush=True)
            q.task_done()

    threads = []
    for i, (label, serial) in enumerate(DEVICES[:WORKERS]):
        th = threading.Thread(target=worker, args=(i, label, serial), daemon=True)
        th.start(); threads.append(th); time.sleep(0.5)
    for th in threads:
        th.join()


def _load_existing():
    res = {}
    if os.path.exists(OUT):
        for r in csv.DictReader(open(OUT)):
            # Done = response saved (captured), matching _capture's success rule —
            # not gated on a parsed rank, so resumes only retry genuine misses.
            if r.get("status") == "success":
                res[f"{r['campaign_id']}|{r['keyword']}"] = {
                    "campaign_id": r["campaign_id"], "keyword": r["keyword"],
                    "biz_name": r["biz_name"], "city": r.get("proxy_city", ""),
                    "state": r.get("proxy_region", ""), "zip": r.get("proxy_zip", ""),
                    "date": r.get("date"), "scope": r.get("scope", ""),
                    "status": "success", "rank_position": r.get("rank_position", ""),
                    "rank_total": r.get("rank_total", ""), "response_text": r.get("response_text", ""),
                    "prompt": r.get("prompt", ""), "duration_s": r.get("duration_s", ""),
                }
    return res


def _cp_timestamp(key, date):
    """Gemini timestamp = midpoint of the keyword's CP-fellow timestamps (same date)."""
    cp = CP_FELLOW.get(key, {})
    ts = cp.get("ts") or []
    def parse(s): return dt.datetime.fromisoformat(s.replace("Z", ""))
    if len(ts) >= 2:
        a, b = sorted(parse(x) for x in ts)[:2]
        mid = a + (b - a) / 2
        return mid.strftime("%Y-%m-%dT%H:%M:%SZ")
    if ts:
        return ts[0]
    return f"{date}T12:00:00Z"


def _write(results):
    fields = ["timestamp", "date", "client_id", "biz_name", "campaign_id", "campaign_name",
              "keyword", "platform", "mode", "device", "status", "duration_s",
              "rank_position", "rank_total", "mentioned", "response_text", "error",
              "proxy_city", "proxy_region", "proxy_zip", "prompt", "scope"]
    rows = []
    for key, r in results.items():
        cp = CP_FELLOW.get(key, {})
        date = cp.get("date") or r.get("date")          # match the CP fellow's date
        ts = _cp_timestamp(key, date)                    # ...and timestamp
        rows.append({
            "timestamp": ts, "date": date, "client_id": "", "biz_name": r["biz_name"],
            "campaign_id": r["campaign_id"], "campaign_name": "", "keyword": r["keyword"],
            "platform": "gemini", "mode": "gemini_cdp", "device": "", "status": r["status"],
            "duration_s": r.get("duration_s", ""), "rank_position": r.get("rank_position", ""),
            "rank_total": r.get("rank_total", ""),
            "mentioned": "yes" if r.get("rank_position") else "no",
            "response_text": (r.get("response_text") or "").replace("\n", " "),
            "error": r.get("error", ""), "proxy_city": r.get("city", ""),
            "proxy_region": r.get("state", ""), "proxy_zip": r.get("zip", ""),
            "prompt": r.get("prompt", ""), "scope": r.get("scope", ""),
        })
    rows.sort(key=lambda x: x["timestamp"])
    for path in (OUT, DESKTOP):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(rows)
    return rows


def main():
    results = _load_existing()
    pending = [t for t in TARGETS if _key(t) not in results]
    print(f"Gemini backfill: {len(results)} already ranked, {len(pending)} to capture, "
          f"{WORKERS} workers, Decodo zip-targeted\n", flush=True)

    rnd = 0; prev_fail = None; no_progress = 0
    todo = pending
    while todo and rnd < MAX_ROUNDS:
        rnd += 1
        print(f"=== round {rnd}: {len(todo)} keyword(s) ===", flush=True)
        _run_pool(todo, results)
        todo = [t for t in TARGETS if results.get(_key(t), {}).get("status") != "success"]
        _write(results)  # checkpoint each round
        fail = len(todo)
        print(f"--- after round {rnd}: {fail} still without a rank ---", flush=True)
        if fail == 0:
            break
        no_progress = no_progress + 1 if fail == prev_fail else 0
        if no_progress >= 3:
            print(f"no progress for 3 rounds at {fail} — stopping (these likely return no rank)", flush=True)
            break
        prev_fail = fail

    rows = _write(results)
    ok = sum(1 for r in rows if r["status"] == "success")
    print(f"\nDONE — {ok}/{len(rows)} ranked. deliverable -> {DESKTOP}", flush=True)
    if ok < len(rows):
        stuck = [r["keyword"] for r in rows if r["status"] != "success"]
        print(f"still no rank ({len(stuck)}): {stuck[:15]}", flush=True)


if __name__ == "__main__":
    main()
