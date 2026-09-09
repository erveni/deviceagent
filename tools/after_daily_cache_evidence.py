"""One-shot, deadline-bounded wait for a completed daily, then one supervised test.

No fleet commands or provider requests while waiting. Existing output prevents a
second run after launchd reload/reboot. Never stops daily or resumes stale ranking.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = {'daily_full_auto.sh', 'build_daily_plan.py', 'run_daily_auto.sh',
             'run_rolling_plan.py', 'run_ranking_auto.sh', 'run_ranking.py',
             '_chain_0906_agent.sh', 'solace_consumer.py', 'run_with_proxy.py',
             'run_daily_plan.py', 'measure_ranking_cost.sh', 'measure_idle_proxy.py',
             'direct_audit_smoke.py', 'direct_ui_probe.py', 'gost'}


def workload_parser():
    # Reuse the existing argv-aware, tested parser; never execute supervisor main.
    source = (ROOT / 'tools/run_ranking_cost_pair.sh').read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'workload_name')
    ns = dict(os=os, re=re, shlex=shlex, workload_names=WORKLOADS)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'workload-parser-only', 'exec'), ns)
    return ns['workload_name']


def fingerprint():
    paths = [ROOT / 'audit_dispatch_http.py', ROOT / 'run_ranking_auto.sh', ROOT / 'run_ranking.py',
             ROOT / 'app/build/outputs/apk/debug/app-debug.apk',
             ROOT / 'direct_ui_20260908_apk/device104-original-v79.apk']
    paths += list((ROOT / 'tools').glob('*.py')) + list((ROOT / 'tools').glob('*.sh'))
    paths += list((ROOT / 'device_agent_proxy').glob('*.py'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--daily-date', required=True)
    p.add_argument('--deadline-utc', required=True)
    args = p.parse_args()
    daily_date = datetime.strptime(args.daily_date, '%Y-%m-%d').date().isoformat()
    deadline = datetime.fromisoformat(args.deadline_utc.replace('Z', '+00:00'))
    if deadline.utcoffset() != timezone.utc.utcoffset(None):
        p.error('Deadline must specify UTC')
    out = Path(args.output).resolve()
    out.mkdir(exist_ok=False)  # Durable no-repeat guard, including crash/reboot.
    state = {'status': 'waiting-for-daily', 'daily_date': daily_date,
             'deadline_utc': args.deadline_utc, 'maximum_paid_jobs': 1,
             'daily_modified': False, 'full_ranking_resumed': False}

    def save():
        state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
        (out / 'state.json').write_text(json.dumps(state, indent=2))

    try:
        pinned = fingerprint()
        (out / 'code_fingerprint.json').write_text(json.dumps(pinned, indent=2))
        recognize = workload_parser()
        quiet_since = None
        while True:
            # Leave two hours for direct check, delayed meter and rollback.
            if time.time() >= deadline.timestamp() - 7200:
                raise RuntimeError('Start window expired; no phone/proxy test started')
            rows = subprocess.check_output(['ps', '-axo', 'command='], text=True, timeout=10).splitlines()
            blockers = sorted({name for row in rows if (name := recognize(row))})
            log = Path(f'/private/tmp/dailyfull_{daily_date}.log')
            finished = log.exists() and bool(re.search(
                rf'^\[dailyfull {re.escape(daily_date)} [^\]]+\] ALL DONE\b', log.read_text(), re.M))
            locked = Path('/tmp/fleet.lock').exists()
            state.update(blockers=blockers, daily_all_done=finished, fleet_lock_present=locked)
            save()
            if finished and not blockers and not locked:
                if quiet_since is None:
                    quiet_since = time.monotonic()
                if time.monotonic() - quiet_since >= 60:
                    break
            else:
                quiet_since = None
            print(f"Waiting: daily_done={finished}, workloads={blockers}, fleet_lock={locked}", flush=True)
            time.sleep(30)
        if fingerprint() != pinned:
            raise RuntimeError('Candidate or test source changed while queued; refusing unreviewed code')
        state['status'] = 'direct-then-one-metered-job'
        save()
        command = [sys.executable, '-u', str(ROOT / 'tools/direct_audit_smoke.py'),
                   '--cache-trial', '--cache-evidence', '--output', str(out / 'direct'),
                   '--metered-output', str(out / 'metered')]
        # No inherited experiment switches or stale meter baselines.
        env = {k: v for k, v in os.environ.items() if not k.startswith(('COST_', 'RANK_'))}
        with (out / 'test.log').open('x') as stream:
            done = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        state['exit_code'] = done.returncode
        wrapper = json.loads((out / 'direct/report.json').read_text())
        restored = wrapper.get('restored_health', {})
        state['rollback_verified'] = (restored.get('versionCode') == 79 and
            restored.get('accessibility') is True and wrapper.get('restored_no_tun0') is True
            and not wrapper.get('restore_error'))
        meter_path = out / 'metered/report.json'
        if meter_path.exists():
            meter = json.loads(meter_path.read_text())
            state['measurement_status'] = meter.get('status')
            state['automatic_successes'] = sum(leg.get('successful_pairs', 0) for leg in meter.get('legs', []))
            state['used_mb'] = sum(leg.get('used_mb', 0) for leg in meter.get('legs', []))
            state['measurement_report'] = str(meter_path)
        state['status'] = ('finished-needs-visual-review' if done.returncode == 0 and state['rollback_verified']
                           else 'failed-inspect-reports')
        if state.get('automatic_successes') != 1 or state.get('measurement_status') != 'complete':
            state['status'] = 'failed-inspect-reports'
        # Neither process completion nor meter completion implies a valid capture.
        state['savings_claim'] = False
        save()
    except Exception as error:
        state.update(status='stopped', error=str(error))
        save()
        raise


if __name__ == '__main__':
    main()
