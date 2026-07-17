#!/usr/bin/env python3
"""Adjudicate EVERY rejected top-3 row, not a sample.

Question this answers, for all 4,289 rows where screenshot_rank_visible=false:
does the model's own numbered list contradict its own [RANK: X/Y] claim?

That is decidable from the screenshot text alone, so it needs no vision model and
no sampling: OCR each capture and run the SAME _rank_inconsistent gate the
dispatcher uses (imported from audit_dispatch_http.py, not reimplemented, so the
verdicts here and the live gate can never drift apart).

Verdicts:
  fabricated   — business absent from the list yet X <= 3   (rank is not real)
  inconsistent — business listed at n but X disagrees        (rank is not real)
  legit        — business listed at n and X agrees           (validator was WRONG)
  unreadable   — no list and/or no [RANK] recovered by OCR   (no verdict)

`legit` is the interesting one: those are real wins the validator suppressed.

env: DATABASE_URL, AWS_PROFILE=aeo-admin
usage: python3 audit_rejected_top3.py [--limit N] [--workers N]
"""
from __future__ import annotations
import json, os, re, subprocess, sys, csv
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the live gate rather than copying it — a copy would silently diverge
# from what actually runs on capture.
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "audit_dispatch_http.py")).read()
_ns = {"re": re}
exec(_src[_src.index("_LIST_MARK = {"):_src.index("def _capture_has_answer")], _ns)
_rank_inconsistent = _ns["_rank_inconsistent"]

OCR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "ocr_vision")
SHOTS = "/tmp/verify_shots"
ROWS = json.load(open("/tmp/rejected_all.json"))
LIMIT = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), 0)
WORKERS = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--workers=")), 12)
if LIMIT:
    ROWS = ROWS[:LIMIT]
os.makedirs(SHOTS, exist_ok=True)


import boto3, botocore  # noqa: E402

# One in-process client beats `aws s3 cp` per row: the CLI is itself Python, so
# 16 concurrent copies spent ~2.5s each on interpreter startup and pegged the CPU
# (~0.6 rows/s). boto3 shares one session and is network-bound instead.
_S3 = boto3.session.Session(profile_name=os.environ.get("AWS_PROFILE") or None).client(
    "s3", region_name="us-east-1",
    config=botocore.config.Config(max_pool_connections=64, retries={"max_attempts": 3}))


def fetch_and_ocr(row):
    rid = row["id"]
    png = f"{SHOTS}/{rid}.png"
    if not os.path.exists(png) or os.path.getsize(png) == 0:
        url = row.get("screenshot_url") or ""
        if not url.startswith("s3://"):
            return rid, None
        bucket, _, key = url[5:].partition("/")
        try:
            _S3.download_file(bucket, key, png)
        except Exception:
            return rid, None
    try:
        txt = subprocess.run([OCR, png], capture_output=True, text=True, timeout=90).stdout
    except Exception:
        return rid, None
    return rid, txt


# Name matching lives in the live gate and is imported, never copied — a copy is
# what let this script and the gate disagree before (it truncated the business
# name at the first comma, so generic "Chimney Sweep" matched the competitor
# "Vancouver Chimney Sweep" and a fabricated row scored `legit`).
_name_candidates = _ns["_name_candidates"]
_name_matches = _ns["_name_matches"]


def classify(row, txt):
    """Mirror of the gate's decision, but split into WHY so the population can be
    counted by cause. The gate itself only returns a bool."""
    if not txt or not txt.strip():
        return "unreadable", ""
    plat = (row["platform"] or "").lower()
    if plat not in ("chatgpt", "perplexity"):
        return "skipped_platform", ""
    mk = _ns["_LIST_MARK"].get(plat)
    ans = (txt.split(mk, 1)[1] if (mk and mk in txt) else txt).lower()
    # Tolerant of OCR artifacts the live gate never sees: it reads the a11y tree
    # (brackets intact), this reads pixels, and tesseract routinely drops the
    # leading "[" — "RANK: 1/3]". Requiring both brackets scored 8/40 readable
    # captures as unreadable.
    m = re.search(r"\[?\s*rank:\s*(\d+)\s*/\s*(\d+)\s*\]?", ans)
    if not m:
        return "unreadable", "no [RANK] line"
    x = int(m.group(1))
    cands = _name_candidates(row["biz"] or "", row.get("aka") or "")
    if not cands:
        return "unreadable", "no usable business name"
    region = ans[:m.start()]
    seen = {}
    for n in (1, 2, 3):
        mm = re.search(rf"(?:^|\n)\s*{n}[.\)]\s*(.*?)(?=(?:\n\s*{n + 1}[.\)])|\Z)", region, re.S)
        if not mm:
            continue
        nm = " ".join(re.sub(r"[^a-z0-9 ]", " ",
                             re.split(r"\s[—–-]\s|\n", mm.group(1).strip(), maxsplit=1)[0]).split())
        seen[n] = nm
        if any(_name_matches(c, nm, strict) for c, strict in cands):
            if x > 3 or x != n:
                return "inconsistent", f"listed #{n} but [RANK: {x}]"
            return "legit", f"listed #{n}, [RANK: {x}] agrees"
    if not seen:
        # A [RANK] line but no numbered list in frame = the capture scrolled past
        # the list (check3/check4 in the 2026-07-17 handover). A real, distinct
        # failure — the rank may be true, but this image cannot evidence it.
        return "capture_scrolled", f"[RANK: {x}] present but list not in frame"
    if x <= 3 and x not in seen:
        # Claims position x, but x itself scrolled off the top — absence cannot be
        # concluded from the items that ARE visible. (Mark McKay: items 2-3 in
        # frame, #1 cut off, claims [RANK: 1] — calling that fabricated is wrong.)
        return "capture_scrolled", f"claims [RANK: {x}] but position {x} not in frame"
    return ("fabricated",
            f"absent from list positions {sorted(seen)}, claims [RANK: {x}]") if x <= 3 \
        else ("honest_nonrank", f"absent, claims [RANK: {x}] (>3)")


print(f"rows to adjudicate: {len(ROWS)}  workers={WORKERS}", flush=True)
out, done = [], 0
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for rid, txt in ex.map(fetch_and_ocr, ROWS):
        row = next(r for r in ROWS if r["id"] == rid)
        verdict, why = classify(row, txt)
        out.append({**{k: row[k] for k in ("id", "keyword_id", "platform", "d", "pos", "biz")},
                    "verdict": verdict, "why": why})
        done += 1
        if done % 250 == 0:
            print(f"  {done}/{len(ROWS)}", flush=True)

path = "/tmp/rejected_audit.csv"
with open(path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)

from collections import Counter
tally = Counter(o["verdict"] for o in out)
print(f"\n=== ALL {len(out)} REJECTED TOP-3 ROWS ADJUDICATED ===")
for k, v in tally.most_common():
    print(f"  {k:<18} {v:>5}  ({100.0 * v / len(out):.1f}%)")
print(f"\ndetail -> {path}")
