"""Recover account-meter evidence after a stopped test; never dispatch a job."""
import argparse
import csv
import json
import time
from pathlib import Path

from measure_evomi_targeting import balance, idle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample', type=Path)
    args = parser.parse_args()
    source = json.loads((args.sample / 'report.json').read_text())
    if len(source['legs']) != 1 or source['status'] != 'invalid':
        raise SystemExit('Expected one interrupted measurement leg')
    before = source['legs'][0]['before_mb']
    output = args.sample / 'recovered_settlement.json'
    readings = []
    started = time.monotonic()
    # Exclusive creation preserves the original report and prevents overwrites.
    with output.open('x') as stream:
        result = dict(status='settling', before_mb=before, readings=readings,
                      original_error=source.get('error'),
                      limitation='Account-wide meter; remote consumers cannot be excluded')
        try:
            while time.monotonic() - started <= 900:
                if not idle():
                    raise RuntimeError('Competing local workload; attribution invalid')
                value = balance()
                readings.append(dict(time=time.time(), balance_mb=value))
                print(json.dumps(readings[-1]), flush=True)
                if value > before + .01 or (len(readings) > 1 and value > readings[-2]['balance_mb'] + .01):
                    raise RuntimeError('Top-up/correction during measurement')
                if time.monotonic() - started >= 300 and len(readings) >= 7:
                    recent = [r['balance_mb'] for r in readings[-7:]]
                    if max(recent) - min(recent) <= .01:
                        rows = [row for path in (args.sample / 'candidate').glob('results*.csv')
                                for row in csv.DictReader(path.open())]
                        success = sum(r.get('status') == 'success' for r in rows)
                        result.update(status='settled', after_mb=value,
                                      used_mb=before-value, completed_rows=len(rows),
                                      success_rows=success,
                                      mb_per_success=(before-value)/success if success else None)
                        break
                time.sleep(20)
            else:
                raise RuntimeError('Meter did not settle')
        except Exception as error:
            result.update(status='invalid', error=str(error))
            raise
        finally:
            json.dump(result, stream, indent=2)
    print(json.dumps({k:v for k,v in result.items() if k != 'readings'}), flush=True)


if __name__ == '__main__':
    main()
