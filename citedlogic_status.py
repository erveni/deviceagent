#!/usr/bin/env python3
"""CitedLogic capture progress — counts what's uploaded to S3 for a given {DATE}.

Mirrors the daily/ranking progress idea, but the source of truth is S3 (the
deliverable target). One `aws s3 ls --recursive` over index/<DATE>/, then counts
PNG + JSON pairs against the 500-row MASTER list, broken down by engine.

  DATE=2026-06-10 python3 citedlogic_status.py            # one-shot
  watch -n30 'DATE=2026-06-10 python3 citedlogic_status.py'   # poll
"""
import csv, os, subprocess, sys
from collections import Counter
from datetime import datetime, timezone

BUCKET = os.environ.get("CL_BUCKET", "aeo-rank-screenshots")
PROFILE = os.environ.get("CL_AWS_PROFILE", "aeo-admin")
DATE = os.environ.get("DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
CSV_PATH = os.environ.get("CL_CSV", "/Users/seolocal3/Downloads/citedlogic-MASTER-jobs.csv")


def expected():
    eng = Counter()
    n = 0
    for r in csv.DictReader(open(CSV_PATH)):
        eng[r["engine"].strip().lower()] += 1
        n += 1
    return n, eng


def s3_keys():
    r = subprocess.run(["aws", "s3", "ls", f"s3://{BUCKET}/index/{DATE}/", "--recursive",
                        "--profile", PROFILE], capture_output=True, text=True)
    return [ln.split()[-1] for ln in r.stdout.splitlines() if ln.strip()]


def main():
    total, eng_exp = expected()
    keys = s3_keys()
    png = {k for k in keys if k.endswith(".png")}
    js = {k for k in keys if k.endswith(".raw.json")}
    # a row is "complete" when BOTH its png and json exist (shared stem)
    stems_png = {k[:-4] for k in png}                      # strip .png
    stems_js = {k[:-9] for k in js}                        # strip .raw.json
    done = stems_png & stems_js
    eng_done = Counter(s.rsplit("/", 1)[-1] for s in done)  # last path seg = engine

    print(f"CitedLogic capture — DATE={DATE}  bucket=s3://{BUCKET}/index/{DATE}/")
    print(f"  COMPLETE (png+json): {len(done)}/{total}   ({100*len(done)//total if total else 0}%)")
    print(f"  png only / json only: {len(stems_png - stems_js)} / {len(stems_js - stems_png)}")
    print("  by engine (done/expected):")
    for e in sorted(eng_exp):
        print(f"    {e:12s} {eng_done.get(e,0)}/{eng_exp[e]}")
    if not keys:
        print("  (nothing uploaded yet for this DATE)")


if __name__ == "__main__":
    main()
