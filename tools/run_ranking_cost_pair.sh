#!/bin/bash
# Run explicitly; never starts or resumes the stale queue.
# Usage: bash tools/run_ranking_cost_pair.sh FIXED_KEYWORDS.json NEW_OUTPUT_DIR
set -eu
cd /Users/seolocalph/projects/device-agent
[[ $# == 2 ]] || { echo "Usage: $0 FIXED_KEYWORDS.json NEW_OUTPUT_DIR" >&2; exit 2; }
[[ -f "$1" ]] || { echo "Missing keyword manifest" >&2; exit 2; }
[[ ! -e "$2" ]] || { echo "Output directory must not exist" >&2; exit 2; }
mkdir -- "$2"
exec python3 - "$1" "$2" <<'PY'
import csv
import datetime
import json
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import threading
import time

root = Path.cwd()
sys.path.insert(0, str(root))
from tools.measure_evomi_targeting import balance
manifest = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
keywords = json.loads(manifest.read_text())
single = os.environ.get('COST_DRIVER') == 'reframe_single'
pilot = os.environ.get('COST_DRIVER') == 'cache_pilot'
one_phone = single or pilot
job_count = 1 if single else 10
if not isinstance(keywords, list) or len(keywords) != job_count or len(set(map(str, keywords))) != job_count:
    raise SystemExit(f'Manifest must contain exactly {job_count} distinct keyword IDs')
if any(type(k) is not int or k <= 0 for k in keywords):
    raise SystemExit('Keyword IDs must be positive JSON integers, matching the catalog')
# run_ranking.py synthesizes campaign_id as businessId * 10000 + keywordId;
# audit_dispatch_http preserves it verbatim in CSV. It is NOT keywordId alone.
catalog = {k['id']: k for k in json.loads(Path('/tmp/kw_admin.json').read_text())}
if any(k not in catalog for k in keywords):
    raise SystemExit('Manifest keyword missing from runner catalog')
expected_pairs = {(str(catalog[k]['businessId'] * 10000 + k), 'gemini') for k in keywords}
if len(expected_pairs) != job_count:
    raise SystemExit('Synthesized campaign IDs collide; choose an unambiguous sample')
fixed = out / 'keywords.json'
fixed.write_text(json.dumps(keywords) + '\n')
date = '2026-09-02'
shared_log = Path('/private/tmp/ranking_auto_' + date + '.log')
poll_s, settle_s, settle_timeout = 20, 120, 900
budget_mb, leg_timeout = (100, 10 * 60) if single else (1000, 45 * 60)
if pilot:
    budget_mb, leg_timeout = 150, 30 * 60
hard_deadline = None
if pilot:
    try:
        parsed_deadline = datetime.datetime.fromisoformat(os.environ['COST_DEADLINE_UTC'].replace('Z', '+00:00'))
        if parsed_deadline.utcoffset() != datetime.timedelta(0):
            raise ValueError('deadline must be UTC')
        hard_deadline = parsed_deadline.timestamp()
    except (KeyError, ValueError):
        raise SystemExit('cache_pilot requires an explicit timezone-qualified COST_DEADLINE_UTC')
finishing_partial = False
pilot_serial = None
pilot_phone_stopped = False
pilot_cancel_lock = threading.Lock()
spend_baseline = os.environ.get('COST_SPEND_BASELINE_MB') if single else None
spend_baseline = float(spend_baseline) if spend_baseline is not None else None
if spend_baseline is not None and (not math.isfinite(spend_baseline) or spend_baseline < 0):
    raise SystemExit('Invalid cumulative spend baseline')
driver = os.environ.get('COST_DRIVER', 'city')
if driver not in ('city', 'generation_timeout', 'gemini_app_screenshot', 'warmup', 'reframe_single', 'cache_pilot'):
    raise SystemExit('Unsupported COST_DRIVER')
initial = None
active = None
owned = {}
last_meter = None
report = {'status': 'starting', 'keywords': keywords, 'legs': [], 'driver': driver,
          'jobs_per_leg': job_count, 'single_attempt': one_phone,
          'hard_deadline_utc': os.environ.get('COST_DEADLINE_UTC') if pilot else None,
          'cumulative_spend_baseline_mb': spend_baseline,
          'budget_mb': budget_mb, 'leg_timeout_s': leg_timeout,
          'limitations': ['Evomi is account-wide; remote consumers are undetectable.',
                         f'Meter lag means the spend guard can overshoot {budget_mb} MB.',
                         'Matched serial legs do not eliminate time/order effects.',
                         'Keywords were previously successful; this is not a random estimate of the full stale set.',
                         'GOST ledger is partial local traffic accounting, not directly comparable to billed MB.']}
workload_names = {'daily_full_auto.sh', 'run_daily_auto.sh', 'run_rolling_plan.py',
                  'run_ranking_auto.sh', 'run_ranking.py', '_chain_0906_agent.sh',
                  'solace_consumer.py', 'run_with_proxy.py', 'run_daily_plan.py',
                  'measure_ranking_cost.sh', 'measure_idle_proxy.py', 'gost'}

def workload_name(command):
    """Recognize executable/script argv, never text inside shell diagnostics."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv:
        return None
    executable = os.path.basename(argv[0]).lower()
    if executable in workload_names:
        return executable
    shell = executable in {'bash', 'sh', 'zsh', 'dash', 'ksh'}
    python = re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', executable) is not None
    if not (shell or python):
        return None
    args = iter(argv[1:])
    for arg in args:
        if arg == '--':
            arg = next(args, '')
            return os.path.basename(arg) if os.path.basename(arg) in workload_names else None
        if arg == '-' or arg == '-c' or (shell and arg.startswith('-') and 'c' in arg[1:]):
            return None
        if python and arg == '-m':
            return None
        if (python and arg in {'-W', '-X'}) or (shell and arg in {'-o', '-O'}):
            next(args, None)
            continue
        if arg.startswith('-'):
            continue
        return os.path.basename(arg) if os.path.basename(arg) in workload_names else None
    return None

def log(message):
    line = datetime.datetime.now(datetime.timezone.utc).isoformat() + ' ' + message
    print(line, flush=True)
    with (out / 'events.log').open('a') as stream:
        stream.write(line + '\n')

def save():
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

def processes():
    result = subprocess.run(['ps', '-axo', 'pid=,ppid=,lstart=,command='],
                            capture_output=True, text=True, check=True, timeout=10)
    rows = {}
    for line in result.stdout.splitlines():
        parts = line.split(None, 7)
        if len(parts) == 8:
            rows[int(parts[0])] = (int(parts[1]), ' '.join(parts[2:7]), parts[7])
    return rows

def remember(rows):
    if active is None:
        return
    family = {active.pid} | {pid for pid, identity in list(owned.items())
                            if pid in rows and rows[pid][1] == identity}
    while True:
        expanded = family | {pid for pid, row in rows.items() if row[0] in family}
        if expanded == family:
            break
        family = expanded
    for pid in family:
        if pid in rows:
            owned[pid] = rows[pid][1]

def unrelated(rows):
    remember(rows)
    return [(pid, row[2]) for pid, row in rows.items()
            if workload_name(row[2]) and not (pid in owned and owned[pid] == row[1])]

def stop_owned():
    # Snapshot lineage and birth times; never pkill by name or kill other jobs.
    rows = processes()
    remember(rows)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        rows = processes()
        for pid, identity in list(owned.items()):
            if pid in rows and rows[pid][1] == identity:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
        if sig == signal.SIGTERM:
            time.sleep(5)

def meter(phase):
    global last_meter
    try:
        value = balance()
        if not math.isfinite(value) or value < 0:
            raise ValueError()
    except ValueError:
        raise RuntimeError('Invalid Evomi meter response')
    with (out / 'meter.jsonl').open('a') as stream:
        stream.write(json.dumps({'time': time.time(), 'phase': phase,
                                 'balance_mb': value}) + '\n')
    if last_meter is not None and value > last_meter + 0.01:
        raise RuntimeError('Balance increased during measurement; top-up or meter correction invalidates attribution')
    last_meter = value
    anchor = spend_baseline if spend_baseline is not None else initial
    if spend_baseline is not None and value > spend_baseline + .01:
        raise RuntimeError('Cumulative spend baseline predates a top-up; refusing attribution')
    if not finishing_partial and anchor is not None and anchor - value >= budget_mb:
        raise RuntimeError(f'Whole-sample {budget_mb} MB spend guard reached')
    if value < 10000:
        raise RuntimeError('Daily reserve: account balance below 10000 MB')
    return value

def check_idle():
    check_deadline()
    busy = unrelated(processes())
    if busy:
        raise RuntimeError('Contaminated by unrelated workload: ' + repr(busy))

def check_deadline():
    if pilot and not finishing_partial and time.time() >= hard_deadline:
        raise RuntimeError('Cache pilot hard UTC deadline reached')


def deadline_stop():
    # Independent of a blocked meter read: only this supervisor's descendants.
    if active is not None:
        try:
            stop_pilot_phone()
        finally:
            stop_owned()


def stop_pilot_phone():
    """Cancel our asynchronous device-104 job before meter settlement."""
    global pilot_phone_stopped
    if not pilot or not pilot_serial or active is None:
        return
    with pilot_cancel_lock:
        if pilot_phone_stopped:
            return
        rows = processes()
        remember(rows)
        lock = Path('/tmp/fleet.lock')
        if lock.exists():
            try:
                holder = int(lock.read_text().split()[0])
                if holder in rows and holder not in owned:
                    report['phone_cancel_error'] = 'different live fleet owner; no phone commands sent'
                    return
            except (ValueError, OSError, IndexError):
                report['phone_cancel_error'] = 'unverifiable fleet owner; no phone commands sent'
                return
        if '149145555W002883' not in pilot_serial:
            raise RuntimeError('Refusing cancellation of an unexpected phone')
        for package in ('com.deviceagent', 'com.android.chrome', 'net.typeblog.socks'):
            subprocess.run(['adb', '-s', pilot_serial, 'shell', 'am', 'force-stop', package],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        pilot_phone_stopped = True
        report['owned_phone_cancelled'] = 'device-104; wrapper must restore APK/accessibility'


def settled(phase, before=None, max_seconds=None):
    began = time.monotonic()
    readings = []
    while time.monotonic() - began <= (settle_timeout if max_seconds is None else max_seconds):
        if pilot and time.time() >= hard_deadline + 330:
            raise RuntimeError('Global pilot settlement deadline reached')
        check_idle()
        value = meter(phase)
        readings.append(value)
        minimum_age = 300 if before is not None or phase == 'initial' else settle_s
        if time.monotonic() - began >= minimum_age and len(readings) >= 7:
            stable = max(readings[-7:]) - min(readings[-7:]) <= 0.01
            if stable and (before is None or before - value >= 0.01):
                return value
        log(phase + ': awaiting settled meter, balance=' + str(value))
        time.sleep(min(poll_s, max(0, hard_deadline+330-time.time())) if pilot else poll_s)
    raise RuntimeError(phase + ': meter did not settle with observable deduction')

def interrupted(signum, frame):
    raise RuntimeError('Interrupted by signal ' + str(signum))

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
deadline_timer = None
if pilot:
    deadline_timer = threading.Timer(max(0, hard_deadline-time.time()), deadline_stop)
    deadline_timer.daemon = True
    deadline_timer.start()
try:
    check_deadline()
    prerequisite = os.environ.get('COST_PREREQUISITE_REPORT')
    if prerequisite:
        report['status'] = 'waiting-for-idle-measurement'
        report['prerequisite_report'] = prerequisite
        save()
        deadline = time.monotonic() + 45 * 60
        while not Path(prerequisite).exists():
            check_deadline()
            if time.monotonic() >= deadline:
                raise RuntimeError('Idle measurement report did not arrive within 45 minutes; no ranking jobs started')
            log('Waiting for completed idle measurement; no phone/proxy actions')
            time.sleep(30)
        prior = json.loads(Path(prerequisite).read_text())
        if prior.get('status') != 'complete':
            raise RuntimeError('Idle measurement did not complete validly; no ranking jobs started')
    report['status'] = 'waiting-for-daily'
    save()
    log('Waiting for daily and other fleet workloads to finish; none will be stopped')
    while unrelated(processes()):
        check_deadline()
        time.sleep(30)
        log('Still waiting for fleet workloads')
    prior_baseline = os.environ.get('COST_SETTLED_BASELINE_REPORT') if one_phone else None
    if prior_baseline:
        prior_path = Path(prior_baseline)
        prior_report = json.loads(prior_path.read_text())
        prior_legs = prior_report.get('legs', [])
        readings = [json.loads(line) for line in prior_path.with_name('meter.jsonl').read_text().splitlines()][-7:]
        if (prior_report.get('status') != 'complete' or not prior_legs
                or len(readings) != 7 or not 0 <= time.time() - readings[-1]['time'] <= 900
                or any(not math.isfinite(r['balance_mb']) or not math.isfinite(r['time']) for r in readings)
                or any(a['time'] >= b['time'] for a,b in zip(readings,readings[1:]))
                or abs(readings[-1]['balance_mb'] - prior_legs[-1]['after_mb']) > .01
                or readings[-1]['time'] - readings[0]['time'] < 120
                or any(r.get('phase') != 'candidate-after' for r in readings)
                or max(r['balance_mb'] for r in readings) - min(r['balance_mb'] for r in readings) > .01):
            raise RuntimeError('Prior settled baseline evidence is stale or invalid')
        check_idle()
        initial = meter('initial-recheck')
        if abs(initial - prior_legs[-1]['after_mb']) > .01:
            raise RuntimeError('Balance changed since prior settled measurement; refusing reuse')
        report['settled_baseline_reused_from'] = str(prior_path)
        log('Rechecked unchanged baseline from completed measurement; no redundant settling wait')
    else:
        initial = settled('initial')
    legs = [('candidate', '1')] if one_phone else [('control', '0'), ('candidate', '1')]
    for name, city_first in legs:
        if driver in ('generation_timeout', 'gemini_app_screenshot', 'warmup'):
            city_first = '1'
        check_idle()
        legdir = out / name
        legdir.mkdir()
        before = meter(name + '-before-recheck') if prior_baseline else settled(name + '-before')
        if prior_baseline and abs(before - initial) > .01:
            raise RuntimeError('Reused baseline changed before launch')
        if report['legs'] and abs(report['legs'][-1]['after_mb'] - before) > 0.01:
            raise RuntimeError('Meter changed between legs; late charges or other traffic invalidate comparison')
        # CLAUDE.md: locked phones mimic browser reset faults. Wake reachable
        # production phones before a test; preserve serials containing spaces.
        adb_list = subprocess.check_output(['adb', 'devices'], text=True, timeout=10)
        if pilot:
            pilot_serials = [line.split('\t')[0] for line in adb_list.splitlines()[1:]
                             if '149145555W002883' in line and line.endswith('\tdevice')]
            if len(pilot_serials) != 1:
                raise RuntimeError('Pilot requires exactly one reachable device-104 serial')
            pilot_serial = pilot_serials[0]
        for line in adb_list.splitlines()[1:]:
            check_idle()
            serial, sep, state = line.partition('\t')
            if one_phone and '149145555W002883' not in serial:
                continue
            if sep and state.strip() == 'device' and '1490455572008742' not in serial:
                for command in [('keyevent', 'KEYCODE_WAKEUP'), ('keyevent', 'KEYCODE_MENU'),
                                ('swipe', '500', '1600', '500', '400', '300')]:
                    check_idle()
                    subprocess.run(['adb', '-s', serial, 'shell', 'input', *command],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        offset = shared_log.stat().st_size if shared_log.exists() else 0
        env = os.environ.copy()
        env.update(PROXY_PROVIDER='evomi', KEYWORD_IDS_FILE=str(fixed),
                   AUDIT_CSV=str(legdir / 'results.csv'), PLATFORMS='gemini',
                   DEVICE_EXCLUDE='device-102,device-108,device-125', WORKERS_CAP='3',
                   MAX_JOBS=str(job_count), RANK_RETRY_ROUNDS='0', FORCE_RERANK='1', SKIP_BASE='0',
                   EVOMI_CITY_FIRST=city_first, EVOMI_DIRECT_ZIP='0',
                   EVOMI_TIER_CACHE_TTL_S='0', AEO_SKIP_PREFLIGHT='0',
                   AEO_TUNNEL_ATTEMPTS='15', AEO_ROTATE_ON_INPUT_FAILED='1',
                   AEO_ROTATE_ON_GENERATION_TIMEOUT='1', RANK_GEMINI_RANK_TEXT_ONLY='0',
                   RANK_GEMINI_APP_SCREENSHOT='0',
                   RANK_WARMUP_S='60',
                   RANK_SINGLE_ATTEMPT='0', RANK_GEMINI_SAME_ANSWER_REFRAME='0',
                   RANK_GEMINI_CACHE_TRIAL='0',
                   OCR_VALIDATE_SCREENSHOT='1', GEMINI_CDP='0', RANK_PHASE_TRACE='1',
                   GOST_COST_LEDGER=str(legdir / 'gost.jsonl'), COPILOT_MAX_PARALLEL='4')
        if one_phone:
            env.update(WORKERS_CAP='1', RANK_SINGLE_ATTEMPT='1', RANK_GEMINI_SAME_ANSWER_REFRAME='1',
                       DEVICE_EXCLUDE=','.join(f'device-{n}' for n in range(101,126) if n != 104))
        if pilot or os.environ.get('COST_PHASE_TELEMETRY') == '1':
            env['GOST_PHASE_LEDGER'] = str(legdir / 'gost_phases.jsonl')
        if pilot:
            env['RANK_CACHE_PILOT'] = '1'
        if pilot or os.environ.get('COST_CACHE_TRIAL') == '1':
            if not one_phone:
                raise RuntimeError('Cache trial is restricted to one job on device-104')
            env['RANK_GEMINI_CACHE_TRIAL'] = '1'
        if driver == 'generation_timeout' and name == 'candidate':
            env['AEO_ROTATE_ON_GENERATION_TIMEOUT'] = '0'
        if driver == 'gemini_app_screenshot' and name == 'candidate':
            env['RANK_GEMINI_APP_SCREENSHOT'] = '1'
        if driver == 'warmup' and name == 'candidate':
            env['RANK_WARMUP_S'] = '3'
        env.pop('EXCLUDE_SUCCESS', None)
        env.pop('DRY_RUN', None)
        (legdir / 'settings.json').write_text(json.dumps(
            {k: env[k] for k in ['EVOMI_CITY_FIRST', 'MAX_JOBS', 'RANK_RETRY_ROUNDS',
                                 'AEO_TUNNEL_ATTEMPTS', 'DEVICE_EXCLUDE',
                                 'AEO_ROTATE_ON_GENERATION_TIMEOUT',
                                 'RANK_GEMINI_APP_SCREENSHOT',
                                 'RANK_WARMUP_S',
                                 'RANK_SINGLE_ATTEMPT', 'RANK_GEMINI_SAME_ANSWER_REFRAME',
                                 'RANK_GEMINI_RANK_TEXT_ONLY']}, indent=2))
        if env.get('RANK_GEMINI_CACHE_TRIAL') == '1':
            report['cache_trial'] = True
        leg = {'name': name, 'before_mb': before, 'status': 'running'}
        report['status'] = name + '-running'
        report['legs'].append(leg)
        save()
        started = time.monotonic()
        log(f'Starting {name} bounded {job_count}-job Gemini sample')
        check_idle()
        with (legdir / 'launcher.log').open('w') as stream:
            active = subprocess.Popen(['bash', 'run_ranking_auto.sh', date, 'stale'],
                                      env=env, stdout=stream, stderr=subprocess.STDOUT,
                                      start_new_session=True)
            check_deadline()
            try:
                while active.poll() is None:
                    check_idle()
                    meter(name + '-running')
                    if time.monotonic() - started >= leg_timeout:
                        raise RuntimeError(name + f': {leg_timeout // 60}-minute leg limit reached')
                    time.sleep(poll_s)
                if active.returncode:
                    raise RuntimeError(name + ': launcher exit ' + str(active.returncode))
            finally:
                if shared_log.exists():
                    with shared_log.open('rb') as source:
                        source.seek(offset)
                        (legdir / 'ranking.log').write_bytes(source.read())
        # Catch and stop any own proxy/watcher descendants left after launcher exit.
        stop_owned()
        active = None
        after = settled(name + '-after', before, max_seconds=330 if pilot else None)
        rows = [row for path in legdir.glob('results*.csv')
                for row in csv.DictReader(path.open())]
        def pair(row):
            return (str(row.get('campaign_id') or '').strip(),
                    str(row.get('platform') or '').strip().lower())
        actual_pairs = {pair(row) for row in rows}
        complete = len(rows) == job_count and actual_pairs == expected_pairs
        successes = {pair(r) for r in rows if r.get('status', '').strip().lower() == 'success'}
        used = before - after
        leg.update(after_mb=after, used_mb=used, completed_rows=len(rows),
                   successful_pairs=len(successes),
                   mb_per_scheduled_job=used / job_count,
                   mb_per_success=used / len(successes) if successes else None,
                   expected_pairs=sorted(expected_pairs), actual_pairs=sorted(actual_pairs),
                   status='valid' if complete else 'invalid-incomplete')
        save()
        if not complete:
            raise RuntimeError(name + ': expected exactly one row per manifest campaign/Gemini pair')
        log(name + ': used ' + str(round(used, 2)) + ' MB; successes=' + str(len(successes)))
    report['status'] = 'complete'
except Exception as error:
    report['status'] = 'invalid'
    report['error'] = str(error)
    log(str(error))
    if active is not None:
        if pilot:
            try:
                stop_pilot_phone()
            except Exception as cancellation_error:
                report['phone_cancel_error'] = type(cancellation_error).__name__
        stop_owned()
        active = None
    if pilot:
        finishing_partial = True
        if deadline_timer:
            deadline_timer.cancel()
        report['status'] = 'partial'
        partial_dir = out / 'candidate'
        partial_rows = [row for path in partial_dir.glob('results*.csv')
                        for row in csv.DictReader(path.open())]
        completed = {str(row.get('campaign_id', '')).strip() for row in partial_rows}
        completed_ids = [k for k in keywords if str(catalog[k]['businessId']*10000+k) in completed]
        report.update(completed_keyword_ids=completed_ids,
                      remaining_keyword_ids=[k for k in keywords if k not in completed_ids],
                      completed_jobs=len(completed_ids), remaining_jobs=job_count-len(completed_ids),
                      success_rows=sum(row.get('status') == 'success' for row in partial_rows),
                      error_rows=sum(row.get('status') != 'success' for row in partial_rows))
        if report['legs']:
            report['legs'][-1].update(status='partial', completed_rows=len(partial_rows),
                                     successful_pairs=report['success_rows'])
            try:
                partial_after = settled('candidate-after', report['legs'][-1]['before_mb'],
                                        max_seconds=max(0, min(330, hard_deadline+330-time.time())))
                report['legs'][-1].update(status='partial', after_mb=partial_after,
                    used_mb=report['legs'][-1]['before_mb']-partial_after)
                report['partial_cost_settled'] = True
            except Exception as settling_error:
                report['partial_cost_settled'] = False
                report['settlement_error'] = str(settling_error)
finally:
    if deadline_timer:
        deadline_timer.cancel()
    save()
if report['status'] != 'complete':
    sys.exit(1)
PY
