#!/bin/bash
# Build-only local api-server lifecycle for the daily build's Ollama fallback.
#
# The daily build enriches every session via /api/llm/build-session, which calls
# DeepSeek. DeepSeek runs out of balance (402) roughly daily and starves the build.
# The api-server now supports an Ollama fallback (OLLAMA_FALLBACK_MODEL), so routing
# the build through a LOCAL api-server instance gives DeepSeek-first + Ollama-on-402.
#
# Safety: this instance is BUILD-ONLY. TRIAL_SWEEP_MINUTES=0 disables the trial->paid
# sweep and AUTO_ROTATION_ENABLED is left unset, so the instance runs no background
# jobs against prod (no double Stripe charges, no duplicate emails). It only serves
# build-session. The env file (prod secrets) is written 0600 and scrubbed on stop.
#
# source this file, then: start_build_server && export ADMIN_BASE=http://localhost:$BUILD_SERVER_PORT ; ... ; stop_build_server

BUILD_SERVER_PORT="${BUILD_SERVER_PORT:-8788}"
BUILD_SERVER_DIR="/Users/seolocalph/projects/AEOAdmin/artifacts/api-server"
BUILD_SERVER_ENV="/tmp/aeo_build_server_$$.env"
BUILD_SERVER_PID=""

# Returns 0 and leaves the server healthy on $BUILD_SERVER_PORT, or 1 on any failure
# (caller then falls back to the deployed ADMIN endpoint — best effort, never fatal).
start_build_server() {
  command -v node >/dev/null 2>&1 || { echo "[build-server] no node — skip"; return 1; }
  [ -f "$BUILD_SERVER_DIR/dist/index.mjs" ] || { echo "[build-server] no dist — skip"; return 1; }
  # Ollama is the whole point of the fallback; if it's down, the local server offers
  # no advantage over the deployed one — skip and let the caller use the deployed API.
  curl -s --max-time 5 "http://localhost:11434/api/tags" >/dev/null 2>&1 || { echo "[build-server] ollama down — skip"; return 1; }

  # free a stale listener on the port
  local stale; stale=$(lsof -ti tcp:"$BUILD_SERVER_PORT" 2>/dev/null)
  [ -n "$stale" ] && kill "$stale" 2>/dev/null && sleep 1

  # write env from the AWS secret + build-only overrides
  aws secretsmanager get-secret-value --secret-id aeo-admin/prod --profile aeo-admin --region us-east-1 --query SecretString --output text 2>/dev/null | \
    ENV_OUT="$BUILD_SERVER_ENV" PORT="$BUILD_SERVER_PORT" python3 -c "
import sys, json, os
d = json.load(sys.stdin)
with open(os.environ['ENV_OUT'], 'w') as f:
    for k, v in d.items():
        f.write(f'{k}={v}\n')
    f.write(f'PORT={os.environ[\"PORT\"]}\n')
    f.write('OLLAMA_FALLBACK_MODEL=qwen2.5:7b\n')
    f.write('TRIAL_SWEEP_MINUTES=0\n')   # disable trial->paid sweep (no prod side effects)
    f.write('NODE_ENV=development\n')
" || { echo "[build-server] secret fetch failed — skip"; return 1; }
  chmod 600 "$BUILD_SERVER_ENV"
  grep -q "^DATABASE_URL=" "$BUILD_SERVER_ENV" || { echo "[build-server] bad env — skip"; rm -f "$BUILD_SERVER_ENV"; return 1; }

  node --env-file="$BUILD_SERVER_ENV" --enable-source-maps "$BUILD_SERVER_DIR/dist/index.mjs" \
    >/tmp/aeo_build_server.log 2>&1 &
  BUILD_SERVER_PID=$!

  # poll health up to ~40s
  local i
  for i in $(seq 1 40); do
    if ! kill -0 "$BUILD_SERVER_PID" 2>/dev/null; then echo "[build-server] died on startup — skip"; rm -f "$BUILD_SERVER_ENV"; return 1; fi
    if curl -s --max-time 3 -o /dev/null "http://localhost:$BUILD_SERVER_PORT/api/llm/prompt-templates" -H "X-Executor-Token: ${TOK:-x}" 2>/dev/null; then
      echo "[build-server] up on :$BUILD_SERVER_PORT (pid $BUILD_SERVER_PID, DeepSeek-first + Ollama fallback)"; return 0
    fi
    sleep 1
  done
  echo "[build-server] never became healthy — skip"; stop_build_server; return 1
}

stop_build_server() {
  [ -n "$BUILD_SERVER_PID" ] && kill "$BUILD_SERVER_PID" 2>/dev/null
  sleep 1
  [ -n "$BUILD_SERVER_PID" ] && kill -0 "$BUILD_SERVER_PID" 2>/dev/null && kill -9 "$BUILD_SERVER_PID" 2>/dev/null
  rm -f "$BUILD_SERVER_ENV"
  BUILD_SERVER_PID=""
  echo "[build-server] stopped + env scrubbed"
}
