#!/usr/bin/env python3
"""Reassign a slice of a built daily plan's Perplexity jobs to Copilot.

A trial before retiring Perplexity outright. Perplexity is the best backlink producer
in the fleet (26%) and Copilot's daily backlink rate has never been measured, so swap a
measurable slice for ONE night and compare, rather than moving ~533 jobs onto an
unproven platform in a single step.

Deliberately a post-processing pass rather than a change to PLATFORMS in
build_daily_plan.py: that constant feeds three `% 3` round-robin sites, so widening it
is not a one-line edit. Rewriting the built plan leaves the rotation untouched, and
reverting means simply not running this.

Distinct from build_reassign_plan.py, which solves the opposite problem (spreading
Gemini jobs onto other platforms so no keyword is dropped) and has no notion of a slice
size or a target platform.

Backlink comparison only means something if the slice CARRIES backlinks, so jobs that
have one are taken first — an all-backlink-less slice would score 0% and prove nothing.

  COPILOT_SLICE=100 python3 slice_copilot_into_plan.py daily_plan_2026-09-02.json
"""
import json
import os
import sys

PLAN = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PLAN_PATH", "")
SLICE = int(os.environ.get("COPILOT_SLICE", "100"))
FROM = os.environ.get("COPILOT_SLICE_FROM", "Perplexity")
TO = "Copilot"

if not PLAN or not os.path.exists(PLAN):
    sys.exit(f"usage: COPILOT_SLICE=N slice_copilot_into_plan.py <plan.json> (got {PLAN!r})")

plan = json.load(open(PLAN))
waves = plan.get("waves") or []
jobs = [j for w in waves for j in w]

candidates = [j for j in jobs if (j.get("platform") or "") == FROM]
if not candidates:
    sys.exit(f"no {FROM} jobs in {PLAN} — nothing to slice")

# Backlink-carrying jobs first; then spread the rest across distinct campaigns so the
# slice isn't one client's entire book.
with_bl = [j for j in candidates if j.get("backlink_url")]
without = [j for j in candidates if not j.get("backlink_url")]
seen_campaign = set()
spread, leftover = [], []
for j in without:
    cid = j.get("campaign_id")
    (spread if cid not in seen_campaign else leftover).append(j)
    seen_campaign.add(cid)

picked = (with_bl + spread + leftover)[:SLICE]
for j in picked:
    j["platform"] = TO

bl = sum(1 for j in picked if j.get("backlink_url"))
campaigns = len({j.get("campaign_id") for j in picked})
json.dump(plan, open(PLAN, "w"))

counts = {}
for j in jobs:
    counts[j.get("platform")] = counts.get(j.get("platform"), 0) + 1
print(f"[copilot-slice] moved {len(picked)} {FROM} -> {TO} "
      f"({bl} carry a backlink, across {campaigns} campaigns)")
print("[copilot-slice] plan now: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
