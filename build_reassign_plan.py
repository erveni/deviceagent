#!/usr/bin/env python3
"""Reassign Gemini daily jobs to ChatGPT/Perplexity instead of dropping them.

Gemini logged-out ranking is unreliable (server wipes the anonymous chat), so we
don't run Gemini in the daily right now. But each daily keyword is assigned to
ONE platform, so simply deleting Gemini jobs DROPS every Gemini-only keyword.
This rebuilds the plan so those keywords still run — on a working platform:

  - keep every ChatGPT / Perplexity job as-is
  - for each Gemini job, reassign it to a CP platform the keyword doesn't already
    have (alternating for balance); if it already has both, drop it (no dup)

Result: the SAME keyword set, none lost, zero Gemini.

Usage: python3 build_reassign_plan.py <DATE>      # e.g. 2026-06-15
Reads daily_plan_<DATE>_withGemini.json (creates it from the current plan once),
writes the corrected daily_plan_<DATE>.json.
"""
import json, os, shutil, sys
from collections import Counter, defaultdict

CP = ("chatgpt", "perplexity")


def key(j):
    return (j.get("campaign_id"), j.get("keyword_id"), j.get("biz_name"))


def main():
    date = sys.argv[1]
    src = f"daily_plan_{date}.json"
    bak = f"daily_plan_{date}_withGemini.json"
    if not os.path.exists(bak):
        shutil.copy(src, bak)            # one-time pristine backup (with Gemini)
    plan = json.load(open(bak))          # always rebuild from the pristine backup
    jobs = [j for w in plan["waves"] for j in w]

    by_kw = defaultdict(list)
    for j in jobs:
        by_kw[key(j)].append(j)

    out, alt, dropped = [], 0, 0
    for _, js in by_kw.items():
        non_gem = [j for j in js if j.get("platform", "").lower() != "gemini"]
        gem = [j for j in js if j.get("platform", "").lower() == "gemini"]
        out.extend(non_gem)
        have = {j.get("platform", "").lower() for j in non_gem}
        for gj in gem:
            cand = [p for p in CP if p not in have]
            if not cand:
                dropped += 1                       # already on both CP platforms
                continue
            pick = cand[alt % len(cand)] if len(cand) == 2 else cand[0]
            if len(cand) == 2:
                alt += 1
            nj = dict(gj)
            nj["platform"] = pick
            out.append(nj)
            have.add(pick)

    waves = [out[i:i + 10] for i in range(0, len(out), 10)] or [[]]
    plan["waves"] = waves
    plan["total_jobs"] = len(out)
    plan["_source"] = (plan.get("_source", "") + " | gemini-reassigned-to-cp").strip(" |")
    json.dump(plan, open(src, "w"))

    covered = len({key(j) for j in out})
    print(f"{date}: {len(out)} jobs  split={dict(Counter(j['platform'] for j in out))}  "
          f"unique_keywords_covered={covered}  gemini_dropped(already-on-both)={dropped}")


if __name__ == "__main__":
    main()
