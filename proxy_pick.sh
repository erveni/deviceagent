#!/bin/bash
# proxy_pick.sh — choose the live residential proxy and export PROXY_* env.
#
# Prefers DataImpulse (cheaper, city-geo, no MITM); falls back to Decodo the
# moment DataImpulse is unreachable or out of balance (407). Source this and call
# pick_proxy() before each run AND before each retry round, so if DataImpulse
# bandwidth hits zero mid-run the next round auto-switches to Decodo.
#
# Passwords come from env (DATAIMPULSE_PASS / DECODO_PASS) — set them in .env.dev
# (gitignored) and `set -a; source .env.dev; set +a` before sourcing this file.
# Never hardcode the passwords here (see .claude/rules/security.md).

pick_proxy() {
  local di_user="78e340233fcc27a26b14" di_pass="${DATAIMPULSE_PASS:?set DATAIMPULSE_PASS (e.g. in .env.dev)}"
  local dc_user="user-spmqebjuzf"      dc_pass="${DECODO_PASS:?set DECODO_PASS (e.g. in .env.dev)}"
  local di_code
  di_code=$(curl -x gw.dataimpulse.com:10000 --proxy-user "${di_user}__cr.us:${di_pass}" \
              -s -m 15 -o /dev/null -w "%{http_code}" https://ipinfo.io/json 2>/dev/null)
  if [ "$di_code" = "200" ]; then
    export PROXY_PROVIDER=dataimpulse PROXY_HOST=gw.dataimpulse.com PROXY_PORT=10000 \
           PROXY_USER="$di_user" PROXY_PASS="$di_pass" PROXY_TARGET=country-us USE_SNI_RELAY=0
    echo "[proxy-pick] DataImpulse OK (http=200) -> using DataImpulse"
  else
    local dc_code
    dc_code=$(curl -x gate.decodo.com:10001 \
                --proxy-user "${dc_user}-session-pk$$-sessionduration-10-country-us:${dc_pass}" \
                -s -m 15 -o /dev/null -w "%{http_code}" https://ipinfo.io/json 2>/dev/null)
    export PROXY_PROVIDER=decodo PROXY_HOST=gate.decodo.com PROXY_PORT=10001 \
           PROXY_USER="$dc_user" PROXY_PASS="$dc_pass" PROXY_TARGET=country-us USE_SNI_RELAY=0
    echo "[proxy-pick] DataImpulse down (http=${di_code:-0}) -> FALLBACK to Decodo (http=${dc_code:-?})"
  fi
}
