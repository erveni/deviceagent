#!/bin/bash
# Jun-23 daily, all 3 platforms in one run — GEMINI FIRST, then CP daily.
#   Phase 1: Gemini via the save-response CDP engine (zip-targeted). Success =
#            the answer was captured off the StreamGenerate wire before the UI wipe.
#   Phase 2: ChatGPT + Perplexity via the normal daily (run_jun23.sh) — UNCHANGED,
#            BUT only after Phase 1 is verified to have saved >=1 response.
# Sequential, NOT parallel: both phases drive the same phones over the same
# gost/socksdroid ports (BASE_GOST+idx) — they must not overlap.
set -u
cd /Users/seolocalph/projects/device-agent
LOG=/private/tmp/run_jun23_combined.log
GEM_CSV="$PWD/ranking_gemini_jun23.csv"
log(){ echo "[jun23-combined] $(date '+%F %T') $*" | tee -a "$LOG"; }

set -a; source .env.dev; set +a   # provides DECODO_PASS (+ certs)

# ── Phase 1: Gemini save-response capture (275 keywords) ──
# Decodo creds must override the stale PROXY_* in .env.dev (run_gemini_ranking uses
# setdefault, so an existing env value would win) — set them explicitly here.
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS in .env.dev}" \
       USE_SNI_RELAY=0 PROXY_TARGET=country-us
log "PHASE 1 START: Gemini save-response capture (275 kw, 10 workers, zip-targeted)…"
GEMINI_TARGETS=/tmp/gemini_backfill_targets.json \
GEMINI_CP_FELLOW=/tmp/cp_fellow_dates.json \
GEMINI_OUT="$GEM_CSV" \
GEMINI_DESKTOP="$HOME/Desktop/Daily/jun23_gemini_ranking_2026-06-23.csv" \
GEMINI_WORKERS=10 GEMINI_MAX_ROUNDS=8 \
python3 run_gemini_ranking.py >>"$LOG" 2>&1
log "PHASE 1 DONE."

# ── Verification gate: Gemini must have saved >=1 response before the daily ──
SAVED=$(python3 -c "
import csv,sys
try:
    rows=list(csv.DictReader(open('$GEM_CSV')))
except FileNotFoundError:
    print(0); sys.exit()
print(sum(1 for r in rows if r.get('status')=='success' and (r.get('response_text') or '').strip()))
" 2>/dev/null || echo 0)
log "VERIFY: Gemini saved responses = $SAVED"
if [ "${SAVED:-0}" -lt 1 ]; then
  log "HALT: Gemini saved 0 responses — NOT running the daily. Investigate before proceeding."
  exit 1
fi

# ── Phase 2: ChatGPT + Perplexity (the daily, exactly as before) ──
log "PHASE 2 START: ChatGPT + Perplexity daily (run_jun23.sh)…"
./run_jun23.sh >>"$LOG" 2>&1
log "PHASE 2 DONE. Jun-23 complete (Gemini saved responses + CP daily)."
log "  Gemini deliverable: ~/Desktop/Daily/jun23_gemini_ranking_2026-06-23.csv"
log "  CP deliverable:     ~/Desktop/Daily/jun23_daily_ALL_SUCCESS_consolidated.csv"
