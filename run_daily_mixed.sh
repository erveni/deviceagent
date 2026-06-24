#!/bin/bash
# Mixed daily — all 3 platforms (ChatGPT / Perplexity / Gemini) in ONE wave-based
# run across the fleet, instead of separate phases.
#
# How it works (GEMINI_INLINE=1):
#   - One shared job queue; each phone pulls the next job of ANY platform.
#   - ChatGPT / Perplexity  -> the app /session flow (GPS-mocked, as always).
#   - Gemini                -> inline CDP StreamGenerate save-capture; that
#     device's gost tunnel is zip-targeted so Gemini's IP-geo matches the biz.
#     Success = the answer was SAVED off the wire (rank parsed when present).
#   - Bonus: CP sessions reset Chrome between a phone's Gemini captures, keeping
#     each Gemini capture fresh (the freshness problem that hurt a Gemini-only run).
#
# Requires daily_plan_<DATE>.json to ALREADY include gemini platform jobs
# (build it with the withGemini plan builder). Output CSV gains response_text /
# rank_position / rank_total / has_rank columns for the gemini rows.
#
# Usage: ./run_daily_mixed.sh 2026-06-24
set -u
cd /Users/seolocalph/projects/device-agent
DATE="${1:?usage: run_daily_mixed.sh <DATE e.g. 2026-06-24>}"
export GEMINI_INLINE=1
exec ./run_daily_auto.sh "$DATE"
