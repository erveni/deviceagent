#!/bin/bash
# User-authorized YOKL first, then resume only unfinished Sep09 daily jobs.
set -u
cd /Users/seolocalph/projects/device-agent
python3 -u tools/direct_audit_smoke.py --yokl-priority \
  --output ranking_yokl_20260909/direct \
  --metered-output ranking_yokl_20260909/metered
rank_rc=$?
echo "YOKL wrapper exit=$rank_rc"
# A failed rollback blocks resuming phones. Never ignore the finally receipt.
python3 - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('ranking_yokl_20260909/direct/report.json').read_text())
h=r.get('restored_health',{})
assert not r.get('restore_error') and h.get('versionCode')==79 and h.get('accessibility') is True
assert r.get('restored_no_tun0') is True
PY
if [ "$?" -ne 0 ]; then
  echo 'STOP: rollback needs inspection; daily remains paused'
  exit 1
fi
echo 'YOKL paid pass ended; restoring daily from saved successes (SKIP_BASE=1)'
SKIP_BASE=1 PROXY_PROVIDER=evomi bash daily_full_auto.sh 2026-09-09
exit "$rank_rc"
