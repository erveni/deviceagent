#!/usr/bin/env python3
"""Retry ranking pairs until every requested keyword/platform succeeds.

This wraps the direct runner for environments where the normal cost-release
wrapper cannot be used. It still relies on the runner's proxy/device guards;
successes are never replayed, and repeated no-progress rounds stop clearly.
"""
from __future__ import annotations
import argparse, csv, glob, json, os, subprocess, sys
from pathlib import Path

def successes(pattern: str):
    done = set()
    for path in glob.glob(pattern):
        try:
            for row in csv.DictReader(open(path, newline="")):
                if row.get("status") == "success":
                    done.add((row.get("keyword"), (row.get("platform") or "").lower()))
        except OSError:
            pass
    return done

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword-ids", required=True)
    ap.add_argument("--results-glob", required=True)
    ap.add_argument("--audit-csv", required=True)
    ap.add_argument("--max-rounds", type=int, default=12)
    ap.add_argument("--max-no-progress", type=int, default=3)
    ap.add_argument("--platforms", default="chatgpt,gemini,copilot")
    args = ap.parse_args()
    ids = json.load(open(args.keyword_ids))
    # The runner resolves these IDs from its catalog snapshot; this supervisor
    # uses the result rows as the durable identity and does not trust attempts.
    expected = None
    previous = -1; stagnant = 0
    for round_no in range(1, args.max_rounds + 1):
        before = successes(args.results_glob)
        print(f"[ranking-retry] round={round_no} successful_pairs={len(before)}", flush=True)
        env = dict(os.environ)
        env["KEYWORD_IDS_FILE"] = args.keyword_ids
        env["AUDIT_CSV"] = args.audit_csv
        env["EXCLUDE_SUCCESS"] = args.results_glob
        env["PLATFORMS"] = args.platforms
        proc = subprocess.run([sys.executable, "run_ranking.py"], env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(proc.stdout[-4000:], end="", flush=True)
        rc = proc.returncode
        after = successes(args.results_glob)
        gained = len(after - before)
        print(f"[ranking-retry] round={round_no} rc={rc} gained={gained} successful_pairs={len(after)}", flush=True)
        if "[retry] EXCLUDE_SUCCESS" in proc.stdout and "-> 0" in proc.stdout:
            print("[ranking-retry] complete: no unresolved pairs remain", flush=True)
            return 0
        if gained == 0:
            stagnant += 1
        else:
            stagnant = 0
        if len(after) == len(before) and stagnant >= args.max_no_progress:
            print("[ranking-retry] stopped: no progress across bounded rounds", flush=True)
            return 3
        previous = len(after)
    print("[ranking-retry] stopped: retry budget exhausted", flush=True)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
