#!/bin/bash
# Mixed daily — all 3 platforms (ChatGPT / Perplexity / Gemini) in ONE run via the
# proven wave runner (run_with_proxy.py) with GEMINI_INLINE=1, wrapped in the
# REMAIN retry loop until 100% (or no-progress for 4 rounds).
#
#   - ChatGPT / Perplexity -> app /session flow (GPS-mocked), as always.
#   - Gemini               -> inline CDP StreamGenerate save-capture, that device's
#     tunnel zip-/country-targeted via geo_target (parses real zip from address,
#     country-ca for Canadian biz). Success = response SAVED off the wire.
#
# Requires daily_plan_<DATE>.json to include gemini jobs (build_daily_plan.py does).
# Usage: ./run_daily_mixed.sh 2026-06-24
set -u
cd /Users/seolocalph/projects/device-agent
DATE="${1:?usage: run_daily_mixed.sh <DATE e.g. 2026-06-24>}"
PLAN="daily_plan_${DATE}.json"
REMAIN="daily_plan_${DATE}_REMAIN.json"
LOG="/private/tmp/daily_mixed_${DATE}.log"
log(){ echo "[mixed ${DATE}] $(date '+%F %T') $*" | tee -a "$LOG"; }

export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")
export EXECUTOR_TOKEN=$(aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin).get('EXECUTOR_TOKEN',''))")
set -a; source .env.dev; set +a
# Decodo creds explicit (override stale .env.dev PROXY_*); GEMINI_INLINE on.
export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
       PROXY_USER=user-spmqebjuzf PROXY_PASS="${DECODO_PASS:?set DECODO_PASS in .env.dev}" \
       USE_SNI_RELAY=0 PROXY_TARGET=country-us
export ONLY_ONLINE=1 GEMINI_INLINE=1

[ -f "$PLAN" ] || { log "FATAL: $PLAN missing"; exit 1; }
ND=$(adb devices | awk -F'\t' 'NR>1 && $2=="device"{c++} END{print c+0}')
log "BASE run: $(python3 -c "import json;print(json.load(open('$PLAN'))['total_jobs'])") jobs, ND=$ND phones, all 3 platforms (gemini inline)…"
python3 -u run_with_proxy.py "$PLAN" >>"$LOG" 2>&1

prev=-1; stable=0; cnt=0
for round in $(seq 1 60); do
  cnt=$(python3 _build_remaining.py "$DATE" 2>>"$LOG")
  log "retry $round remaining=$cnt"
  [ "${cnt:-0}" -eq 0 ] && { log "ALL SUCCESS — 100%"; break; }
  [ "$cnt" -eq "$prev" ] && stable=$((stable+1)) || stable=0
  [ "$stable" -ge 4 ] && { log "NO PROGRESS 4 rounds at $cnt — stopping for review"; break; }
  prev=$cnt
  # _build_remaining emits ONE oversized wave; run_with_proxy is wave-based, so
  # re-pack into ND-sized waves (no same client/campaign within a wave).
  python3 - "$REMAIN" "$ND" <<'PY' 2>>"$LOG"
import json, sys
p = json.load(open(sys.argv[1])); nd = max(1, int(sys.argv[2]))
flat = [j for w in p["waves"] for j in w]
waves, rest = [], list(flat)
while rest:
    wave, uc, ug, left = [], set(), set(), []
    for j in rest:
        if len(wave) < nd and j.get("client_id") not in uc and j.get("campaign_id") not in ug:
            wave.append(j); uc.add(j.get("client_id")); ug.add(j.get("campaign_id"))
        else:
            left.append(j)
    waves.append(wave); rest = left
p["waves"] = waves
json.dump(p, open(sys.argv[1], "w"), indent=1)
PY
  pkill -f "gost -C"; sleep 1
  log "retry $round running $cnt jobs…"
  python3 -u run_with_proxy.py "$REMAIN" >>"$LOG" 2>&1
done
log "FINISHED remaining=$cnt"

# Consolidate every results CSV -> one deliverable (latest success per key wins).
python3 - "$DATE" <<'PY' 2>>"$LOG"
import csv, glob, json, os, sys
date = sys.argv[1]
rows = {}
for f in sorted(glob.glob(f"daily_plan_{date}*results*.csv")):
    for r in csv.DictReader(open(f)):
        k = (r.get("platform"), r.get("client_id"), r.get("campaign_id"), r.get("biz_name"), r.get("keyword"))
        if k not in rows or (r.get("status") == "success" and rows[k].get("status") != "success"):
            rows[k] = r
out = os.path.expanduser(f"~/Desktop/Daily/jun{date[-2:]}_daily_mixed_consolidated.csv")
os.makedirs(os.path.dirname(out), exist_ok=True)
allrows = list(rows.values())
fields = list({c for r in allrows for c in r})
import collections
order = ["timestamp","date","platform","status","biz_name","keyword","rank_position","rank_total","response_text"]
fields = order + [c for c in fields if c not in order]
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(allrows)
ok = sum(1 for r in allrows if r.get("status") == "success")
g = [r for r in allrows if r.get("platform") == "gemini"]
gok = sum(1 for r in g if r.get("status") == "success")
print(f"consolidated {len(allrows)} rows, {ok} success -> {out}")
print(f"  gemini: {gok}/{len(g)} saved")
PY
log "consolidated -> ~/Desktop/Daily/jun${DATE: -2}_daily_mixed_consolidated.csv"
