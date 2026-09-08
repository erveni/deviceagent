"""One owned 180-second idle tunnel; no browser actions or ranking dispatch."""
import argparse
import contextlib
import io
import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.measure_evomi_targeting import balance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(exist_ok=False)
    os.environ.update(PROXY_PROVIDER='evomi', PROXY_HOST='core-residential.evomi.com',
                      PROXY_PORT='1000', PROXY_BASE_USER=os.environ['EVOMI_USER'],
                      PROXY_PASSWORD=os.environ['EVOMI_PASS'], ONLY_ONLINE='1',
                      EVOMI_CITY_FIRST='1', EVOMI_TIER_CACHE_TTL_S='0', EVOMI_DIRECT_ZIP='0',
                      USE_SNI_RELAY='0', GOST_COST_LEDGER=str(out / 'gost.jsonl'))
    sys.path.insert(0, '/Users/seolocalph/projects/aeo-appium')
    from gost_manager import GostManager, _summarize_gost_cost
    from run_with_proxy import DEVICES, socksdroid_connect, socksdroid_disconnect
    lock = Path('/tmp/fleet.lock')
    manager = None
    serial = None
    forwarded = None
    connected = False
    acquired = False
    initial = None
    previous_meter = None
    report = {'status': 'starting', 'hold_s': 180, 'budget_mb': 100,
              'limitations': ['Account-wide meter cannot exclude remote consumers.',
                              'Billed total includes proxy setup and 180-second idle hold.',
                              'Delayed billing may overshoot the 100 MB guard.',
                              'Terminal GOST counters omit unclosed connections.']}

    def emit(event, **fields):
        row = {'time': time.time(), 'event': event, **fields}
        print(json.dumps(row), flush=True)
        with (out / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(row) + '\n')

    def check_idle():
        blocked = {'gost', 'run_ranking.py', 'run_ranking_auto.sh', 'run_rolling_plan.py',
                   'run_daily_auto.sh', 'daily_full_auto.sh', '_chain_0906_agent.sh',
                   'solace_consumer.py', 'run_with_proxy.py', 'run_daily_plan.py'}
        rows = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True)
        own = manager.process.pid if manager and manager.process else None
        for line in rows.splitlines():
            pid, command = line.strip().split(None, 1)
            if int(pid) in (os.getpid(), own):
                continue
            try:
                argv = shlex.split(command)
            except ValueError:
                continue
            if not argv:
                continue
            executable = Path(argv[0]).name.lower()
            name = executable
            if executable.startswith('python') or executable in ('bash', 'sh', 'zsh'):
                # Do not match command text inside diagnostic shell -c arguments.
                if '-c' in argv[1:] or any(a in ('-lc', '-ic') for a in argv[1:]):
                    continue
                name = next((Path(a).name for a in argv[1:] if not a.startswith('-')), '')
            if name in blocked:
                raise RuntimeError('Other fleet/proxy process active, pid=' + pid)

    def meter(phase):
        nonlocal previous_meter
        value = balance()
        if not math.isfinite(value) or value < 10000:
            raise RuntimeError('Invalid balance or 10 GB reserve reached')
        if previous_meter is not None and value > previous_meter + .01:
            raise RuntimeError('Top-up/meter increase invalidates attribution')
        previous_meter = value
        emit('meter', phase=phase, balance_mb=value)
        if initial is not None and initial - value >= 100:
            raise RuntimeError('100 MB spend guard reached')
        return value

    def settle(phase):
        began = time.monotonic()
        stable_since = began
        last = None
        while time.monotonic() - began < 900:
            check_idle()
            value = meter(phase)
            now = time.monotonic()
            if last is None or abs(value - last) > .01:
                stable_since = now
            if now - began >= 300 and now - stable_since >= 120:
                return value
            last = value
            time.sleep(20)
        raise RuntimeError('Meter failed to settle within 900 seconds')

    def adb(*args):
        return subprocess.check_output(['adb', '-s', serial, *args], text=True,
                                       stderr=subprocess.DEVNULL, timeout=15)

    def interrupted(signum, frame):
        raise RuntimeError('Interrupted signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        check_idle()
        with lock.open('x') as stream:
            stream.write(f'{os.getpid()} idle-cost-20260908 {int(time.time())}\n')
        acquired = True
        initial = settle('before')
        report['before_mb'] = initial
        for device, candidate in DEVICES:
            if device in {'device-102', 'device-108', 'device-125'}:
                continue
            serial = candidate
            try:
                forwarded = int(adb('forward', 'tcp:0', 'tcp:8765').strip())
                with urllib.request.urlopen(f'http://127.0.0.1:{forwarded}/health', timeout=5) as response:
                    health = json.load(response)
                with urllib.request.urlopen(f'http://127.0.0.1:{forwarded}/result', timeout=5) as response:
                    result = json.load(response)
                if result.get('running') or health.get('running'):
                    raise RuntimeError('phone busy')
                report['device_id'] = device
                break
            except Exception:
                if forwarded:
                    adb('forward', '--remove', f'tcp:{forwarded}')
                    forwarded = None
        else:
            raise RuntimeError('No healthy idle eligible phone')
        check_idle()
        for command in [('keyevent', 'KEYCODE_WAKEUP'), ('keyevent', 'KEYCODE_MENU'),
                        ('swipe', '500', '1600', '500', '400', '300')]:
            adb('shell', 'input', *command)
        manager = GostManager([{'device_id': report['device_id'], 'country': 'us',
                                'zip': '10001', 'city': 'New York', 'region': 'new_york'}],
                              base_port=19881)
        setup_started = time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            manager.start()
            connected = True
            socksdroid_connect(serial, 19881)
        tun = adb('shell', 'ifconfig', 'tun0')
        if 'UP' not in tun or 'inet' not in tun:
            raise RuntimeError('Owned tunnel did not come up')
        reachable = adb('shell', '(nc -w 4 www.google.com 443 </dev/null >/dev/null 2>&1 || nc -w 4 chatgpt.com 443 </dev/null >/dev/null 2>&1) && echo OK')
        if 'OK' not in reachable:
            raise RuntimeError('Owned phone tunnel failed setup reachability probe')
        spec = manager.specs[0]
        report.update(selected_tier=spec.tier, requested_city=spec.city,
                      requested_zip=spec.zip_code, setup_reachability_ok=True)
        report['setup_elapsed_s'] = time.monotonic() - setup_started
        emit('idle-start', device_id=report['device_id'], setup_elapsed_s=report['setup_elapsed_s'])
        began = time.monotonic()
        next_meter = began
        while time.monotonic() - began < 180:
            check_idle()
            with open(manager._log_path, errors='replace') as stream:
                counts = _summarize_gost_cost(stream)
            emit('terminal-byte-snapshot', elapsed_s=round(time.monotonic()-began, 2), services=counts)
            if time.monotonic() >= next_meter:
                meter('idle')
                next_meter = time.monotonic() + 20
            time.sleep(5)
        report['idle_elapsed_s'] = time.monotonic() - began
        with contextlib.redirect_stdout(io.StringIO()):
            socksdroid_disconnect(serial)
            connected = False
            manager.stop()
        emit('idle-ended', elapsed_s=report['idle_elapsed_s'])
        end = settle('after')
        report.update(status='complete', after_mb=end, billed_mb=round(initial-end, 2))
    except Exception as error:
        report.update(status='invalid', error_type=type(error).__name__, error=str(error) if isinstance(error, RuntimeError) else 'See event phase')
    finally:
        cleanup_errors = []
        if connected:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    socksdroid_disconnect(serial)
            except Exception as error:
                cleanup_errors.append('disconnect:' + type(error).__name__)
        if manager:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    manager.stop()
            except Exception as error:
                cleanup_errors.append('gost-stop:' + type(error).__name__)
        if forwarded:
            try:
                adb('forward', '--remove', f'tcp:{forwarded}')
            except Exception as error:
                cleanup_errors.append('forward-remove:' + type(error).__name__)
        try:
            if acquired and lock.exists() and lock.read_text().split()[0] == str(os.getpid()):
                lock.unlink()
        except Exception as error:
            cleanup_errors.append('lock-release:' + type(error).__name__)
        if cleanup_errors:
            report.update(status='invalid-cleanup', cleanup_errors=cleanup_errors)
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        emit('finished', **report)
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
