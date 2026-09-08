"""Summarize one opt-in GOST trace; optional read-only, post-job logcat markers."""
import argparse
import bisect
import json
from pathlib import Path
import re
import subprocess
import time


def summarize(path, serial=None):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    valid = [r for r in rows if r['status'] == 'ok']
    if not valid or len({r['gost_pid'] for r in valid}) != 1:
        raise ValueError('Expected exactly one observed GOST process')
    def total(row):
        return sum(s['input_bytes'] + s['output_bytes'] for s in row['services'])
    if any(total(b) < total(a) for a, b in zip(valid, valid[1:])):
        raise ValueError('Cumulative counters decreased; attribution invalid')
    boundaries = [r for r in valid if r['phase'] != 'periodic']
    if not boundaries or boundaries[0]['time'] > valid[0]['time']:
        boundaries.insert(0, dict(valid[0], phase='first_observation'))
    intervals = [dict(phase=a['phase'], until=b['phase'],
                      seconds=round(b['time']-a['time'], 3),
                      local_mb=(total(b)-total(a))/1e6)
                 for a, b in zip(boundaries, boundaries[1:])]
    result = {'local_total_mb': total(valid[-1])/1e6,
              'first_observed_mb': total(valid[0])/1e6,
              'phase_intervals': intervals,
              'limitations': ['Local SOCKS traffic, not the Evomi billing meter.',
                              'Direct upstream preflight bypasses these counters.',
                              'Native marker intervals use preceding samples; up to sampling-interval uncertainty.']}
    if serial:
        # Read logcat only: no UI dump, navigation, screenshot or job submission.
        logs = subprocess.check_output(
            ['adb', '-s', serial, 'logcat', '-d', '-v', 'epoch', '-s', 'DeviceAgent:D', '*:S'],
            text=True, timeout=20)
        markers = []
        wanted = re.compile(r'── (?:RESET CHROME|CLOSE ALL CHROME TABS|CLEAR CHROME DATA|'
                            r'DISMISS CHROME FRE|NAVIGATE TO|DISMISS GEMINI POPUPS|INPUT TEXT|'
                            r'SUBMIT|WAIT FOR GENERATION|GET RESPONSE TEXT|EXTRACT RANKING)'
                            r'|Generation complete|Chrome reset done|Navigating to https://www.google.com')
        for line in logs.splitlines():
            match = re.match(r'\s*(\d+\.\d+)\s+.*?DeviceAgent:\s*(.*)', line)
            if not match:
                continue
            when, message = float(match[1]), match[2]
            if valid[0]['time'] <= when <= valid[-1]['time'] and wanted.search(message):
                # Keep phase names only, not user prompt contents.
                message = re.sub(r'(INPUT TEXT).*', r'\1', message)
                markers.append({'time': when, 'phase': message})
        if not markers:
            # Some installed builds omit Log.d; file logging remains available.
            before = time.time()
            clock = subprocess.check_output(
                ['adb', '-s', serial, 'shell', "date '+%s %H:%M:%S %z'"],
                text=True, timeout=10).strip().split()
            after = time.time()
            epoch, local_clock, offset = clock
            epoch = int(epoch)
            if abs(epoch-(before+after)/2) > 2:
                raise ValueError('Phone and host clocks differ; cannot align native file log')
            h, m, s = map(int, local_clock.split(':'))
            local_seconds = h*3600+m*60+s
            logs = subprocess.check_output(
                ['adb', '-s', serial, 'shell', 'tail', '-n', '250',
                 '/sdcard/Android/data/com.deviceagent/files/logs/agent.log'],
                text=True, timeout=20)
            for line in logs.splitlines():
                match = re.match(r'\[(\d\d):(\d\d):(\d\d\.\d+)\] (.*)', line)
                if not match:
                    continue
                h, m, s, message = match.groups()
                seconds = int(h)*3600+int(m)*60+float(s)
                when = epoch + ((seconds-local_seconds+43200) % 86400-43200)
                if valid[0]['time'] <= when <= valid[-1]['time'] and wanted.search(message):
                    markers.append({'time': when,
                                    'phase': re.sub(r'(INPUT TEXT).*', r'\1', message)})
            result['native_clock'] = {'source': 'agent_file_log', 'utc_offset': offset,
                                      'phone_epoch': epoch, 'host_check_epoch': (before+after)/2}
        times = [r['time'] for r in valid]
        for marker in markers:
            row = valid[max(0, bisect.bisect_right(times, marker['time'])-1)]
            marker.update(local_mb=total(row)/1e6,
                          sample_age_s=round(marker['time']-row['time'], 3))
        result['native_markers'] = markers
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ledger', type=Path)
    parser.add_argument('--serial')
    args = parser.parse_args()
    report = summarize(args.ledger, args.serial)
    output = args.ledger.with_name('phase_summary.json')
    if output.exists():
        raise SystemExit('Refusing to overwrite existing summary')
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
