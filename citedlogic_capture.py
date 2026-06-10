#!/usr/bin/env python3
"""CitedLogic device-farm capture runner — reuses the AEO device-agent audit path.

For each MASTER-jobs.csv row: put the device at the EXACT (lat,lng), run promptText
on the engine, capture screenshot + verbatim answer text, and upload two files to
s3://aeo-rank-screenshots/ — the PNG to `screenshotKey`, a JSON to `rawKey`.
`{DATE}` -> today in UTC. Idempotent (skips rows already uploaded) + retry-to-complete.

Engines:
  chatgpt / gemini / perplexity -> dispatch_audit_job (we keep screenshot + response
    text; the rank it extracts is IGNORED — CitedLogic does its own analysis).
  google-maps -> NOT YET IMPLEMENTED (needs a Maps map-pack flow) -> skipped + logged.

Location: exact GPS via the new mock_lat/mock_lng hook in audit_dispatch_http.
NOTE: AI engines also geolocate by IP — for true metro-local results pair this with a
metro proxy (see handover). This runner currently sets GPS only.

Usage:
  DRY_RUN=1 python3 citedlogic_capture.py                 # plan only, no phones/S3
  DATE=2026-06-10 WORKERS=6 python3 citedlogic_capture.py # run + upload to S3
  CL_LOCAL_ONLY=1 ... python3 citedlogic_capture.py       # run, write files locally, NO S3
"""
from __future__ import annotations
import csv, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

sys.path.insert(0, "/Users/seolocalph/projects/device-agent")
from audit_dispatch_http import dispatch_audit_job, _STATE_GOOD_ZIP, _FALLBACK_GOOD_ZIP  # noqa: E402


def metro_state(metro):
    """'atlanta-ga' -> 'GA'. The CSV has no zip, but the metro name carries the state,
    and we have exact coords — so GPS = coords (exact), proxy = state-good zip (same-region
    IP so the engine doesn't reject geo-mismatch). coords->city-zip is a future refinement."""
    return (metro or "").rsplit("-", 1)[-1].upper()

CSV_PATH = os.environ.get("CL_CSV", "/Users/seolocalph/Downloads/citedlogic-MASTER-jobs.csv")
BUCKET = os.environ.get("CL_BUCKET", "aeo-rank-screenshots")
AWS_PROFILE = os.environ.get("CL_AWS_PROFILE", "aeo-admin")
# {DATE} = today in UTC. Override with DATE=YYYY-MM-DD (recommended until the Mac
# clock/UTC skew is resolved — see handover).
DATE = os.environ.get("DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
WORKERS = int(os.environ.get("WORKERS", "6"))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
AI_ENGINES = {"chatgpt", "gemini", "perplexity"}
# Engines the phone can capture today: the 3 AI chats + the Google Maps map-pack.
CAPTURE_ENGINES = AI_ENGINES | {"google-maps"}
DEVICE_CLASS = os.environ.get("CL_DEVICE", "androidfarm-mac1")
SYNTH_ID_BASE = 99_000_000  # keep synthetic keyword_ids clear of the real catalog
# Local verification mode: skip S3 entirely and write JSON + screenshot under
# CL_LOCAL_DIR (mirroring the S3 key path) so a run can be inspected on the Mac
# before anything is uploaded. Set CL_LOCAL_ONLY=1 to enable.
LOCAL_ONLY = os.environ.get("CL_LOCAL_ONLY", "0") == "1"
LOCAL_DIR = os.environ.get(
    "CL_LOCAL_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "citedlogic_local"),
)


def sub(s):
    return (s or "").replace("{DATE}", DATE)


def load_jobs():
    out = []
    for i, r in enumerate(csv.DictReader(open(CSV_PATH))):
        out.append({
            "row": i,
            "jobId": sub(r["jobId"]),
            "engine": r["engine"].strip().lower(),
            "metro": r.get("metro", ""),
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
            "promptText": r["promptText"],
            "screenshotKey": sub(r["screenshotKey"]),
            "rawKey": sub(r["rawKey"]),
        })
    return out


def s3_exists(key):
    r = subprocess.run(["aws", "s3api", "head-object", "--bucket", BUCKET, "--key", key,
                        "--profile", AWS_PROFILE], capture_output=True, text=True)
    return r.returncode == 0


def s3_put(local, key, ctype):
    return subprocess.run(["aws", "s3", "cp", local, f"s3://{BUCKET}/{key}",
                           "--content-type", ctype, "--profile", AWS_PROFILE],
                          capture_output=True, text=True).returncode == 0


def _local_path(key):
    return os.path.join(LOCAL_DIR, key)


def already_done(j):
    if LOCAL_ONLY:
        return os.path.exists(_local_path(j["screenshotKey"])) and os.path.exists(_local_path(j["rawKey"]))
    return s3_exists(j["screenshotKey"]) and s3_exists(j["rawKey"])


def capture_ai(j):
    """Run one AI-engine row on a phone, return (screenshot_path, answer_text, present)."""
    kid = SYNTH_ID_BASE + j["row"]
    st = metro_state(j["metro"])
    zc = _STATE_GOOD_ZIP.get(st, _FALLBACK_GOOD_ZIP)   # proxy region from coords/metro
    job = {
        "client_id": 0, "keyword_id": kid, "campaign_id": str(kid),
        "biz_name": "", "biz_url": "", "city": j["metro"], "state": st, "zip": zc,
        "keyword": j["promptText"],
        "mock_lat": j["lat"], "mock_lng": j["lng"],   # EXACT device GPS from the coords
        "mode": "citedlogic_capture",
        "targetDate": f"{DATE}T18:00:00-07:00",
    }
    # capture_prompt → phone runs type=capture and types promptText VERBATIM
    # (no audit template, no business). Proxy/GPS/retry/OCR machinery is reused.
    row = dispatch_audit_job(job, platform=j["engine"], csv_path=None,
                             capture_prompt=j["promptText"])
    shot = row.get("screenshot") or ""
    answer = (row.get("response_text") or "").strip()
    status = (row.get("status") or "").lower()
    present = bool(answer) or status in ("success", "no_rank")
    return shot, answer, present, status


# UI-chrome lines (exact match, case-insensitive) that are never part of the
# answer — buttons, tabs, and disclaimers the accessibility scrape picks up.
_CHROME_LINES = {
    "new", "+ new", "share", "open in app", "answer", "links", "images", "places",
    "sources", "steps", "follow-ups", "related", "good response", "bad response",
    "ask a follow-up", "upload & tools", "conversation with gemini",
    "gemini is ai and can make mistakes.", "ask gemini", "search", "copy",
    "regenerate", "share & export", "view all",
    # ChatGPT chrome
    "chatgpt", "skip to content", "model selector", "log in", "sign up",
    "get better results", "share your precise location", "turn on", "no thanks",
    "ask anything", "chatgpt can make mistakes. check important info.",
    "you said", "tools", "use precise location", "stop generating", "send",
}
# The answer begins right AFTER the start marker and ends right BEFORE any end
# marker. chatgpt's answer follows the (doubled) prompt bubble — handled via the
# doubled-prompt strip below rather than a fixed marker.
_START_MARKERS = {"gemini": "gemini said"}
_END_MARKERS = {
    "gemini": ("good response", "bad response", "gemini is ai and can make mistakes.",
               "ask gemini", "upload & tools"),
    "perplexity": ("follow-ups", "ask a follow-up"),
    "chatgpt": ("get better results", "ask anything"),
}


def _clean_answer_text(raw, engine, prompt):
    """Strip app UI chrome + the echoed prompt from the raw a11y scrape, leaving the
    verbatim answer. Conservative: falls back to raw if it would empty the text."""
    if not raw:
        return raw
    eng = (engine or "").lower()
    start = _START_MARKERS.get(eng)
    ends = _END_MARKERS.get(eng, ())
    pl = (prompt or "").strip().lower()
    started = start is None
    out = []
    for ln in (line.strip() for line in raw.splitlines()):
        low = ln.lower()
        if not started:
            if low == start:
                started = True
            continue
        if ends and low in ends:
            break
        if not ln or low in _CHROME_LINES or low == pl or low == f"you said {pl}":
            continue
        # ChatGPT echoes the prompt bubble doubled ("best med spa near me" ×2) —
        # drop any line that is just the prompt repeated.
        if pl and low.replace(pl, "").strip() == "":
            continue
        out.append(ln)
    return "\n".join(out).strip() or raw


def upload(j, shot, answer, present):
    payload = {
        "jobId": j["jobId"], "engine": j["engine"], "lat": j["lat"], "lng": j["lng"],
        "promptText": j["promptText"],
        "capturedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "device": DEVICE_CLASS, "answerPresent": present,
        "answerText": _clean_answer_text(answer, j["engine"], j["promptText"]),
        "answerTextRaw": answer,  # full scrape preserved (citations, sources, etc.)
        "screenshotKey": j["screenshotKey"],
    }
    if LOCAL_ONLY:
        return _save_local(j, shot, payload)
    tmp = f"/tmp/cl_{j['row']}.json"
    json.dump(payload, open(tmp, "w"))
    ok_json = s3_put(tmp, j["rawKey"], "application/json")
    ok_png = True
    if shot and os.path.exists(shot):
        ok_png = s3_put(shot, j["screenshotKey"], "image/png")
    else:
        ok_png = False  # no screenshot captured -> incomplete
    return ok_png and ok_json


def _save_local(j, shot, payload):
    """Write JSON + screenshot under LOCAL_DIR (mirroring the S3 key path) instead
    of uploading. Returns True only when BOTH land, matching the S3 path's contract."""
    json_path = _local_path(j["rawKey"])
    png_path = _local_path(j["screenshotKey"])
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)
    if shot and os.path.exists(shot):
        shutil.copyfile(shot, png_path)
        return True
    return False  # no screenshot captured -> incomplete


def run_one(j):
    try:
        if already_done(j):
            return ("skip", j, "already done (local)" if LOCAL_ONLY else "already in S3")
        if j["engine"] not in CAPTURE_ENGINES:
            return ("gmaps_todo", j, f"engine {j['engine']} not capturable")
        shot, answer, present, status = capture_ai(j)
        if not shot:
            return ("err", j, f"no screenshot (status={status})")
        if not upload(j, shot, answer, present):
            return ("err", j, "local save failed" if LOCAL_ONLY else "s3 upload failed")
        where = _local_path(j["rawKey"]) if LOCAL_ONLY else j["rawKey"]
        return ("ok", j, f"status={status} answer={len(answer)}chars -> {where}")
    except Exception as e:
        return ("err", j, f"{type(e).__name__}: {e}")


def main():
    jobs = load_jobs()
    from collections import Counter
    eng = Counter(j["engine"] for j in jobs)
    targets = [j for j in jobs if j["engine"] in CAPTURE_ENGINES]
    skipped = [j for j in jobs if j["engine"] not in CAPTURE_ENGINES]
    print(f"CitedLogic capture | DATE={DATE} | {len(jobs)} rows | engines={dict(eng)}")
    print(f"  capturable rows (3 AI + google-maps): {len(targets)}")
    if skipped:
        print(f"  skipped rows (unknown engine)       : {len(skipped)}")
    sink = f"LOCAL-ONLY -> {LOCAL_DIR}/ (NO S3)" if LOCAL_ONLY else f"bucket=s3://{BUCKET}/"
    print(f"  {sink}  workers={WORKERS}  device={DEVICE_CLASS}")
    print(f"  sample key: {jobs[0]['screenshotKey']}")
    if DRY_RUN:
        print("\nDRY_RUN=1 — no phones, no S3. Exiting.")
        return
    counts = Counter()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(run_one, j): j for j in targets}
        for n, fut in enumerate(as_completed(futs), 1):
            kind, j, msg = fut.result()
            counts[kind] += 1
            if kind == "err" or n % 10 == 0 or n == len(targets):
                print(f"  [{n}/{len(targets)}] {kind:9s} {j['engine']:11s} {j['metro']:12s} {msg}", flush=True)
    print(f"\nDONE in {(time.time()-t0)/60:.1f}m — {dict(counts)}")


if __name__ == "__main__":
    main()
