"""Export typed successes by slot with deterministic daily timestamp spreading."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import glob
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from daily_prompt_plan import result_key,validate_typed_plan

def collect(plan,rows):
    validate_typed_plan(plan)
    jobs=[j for w in plan['waves'] for j in w];expected={result_key(j) for j in jobs}
    selected={}
    for row in rows:
        key=result_key(row)
        if row.get('status')=='success' and row.get('date')==plan['target_date'] and key in expected:
            selected.setdefault(key,row)
    return list(selected.values()),sorted(expected-set(selected))


def randomize_daily_rows(rows, run_date):
    """Scatter campaigns through 08:00-17:59Z, reproducibly for one date.

    This restores the June/early-July consolidation policy: shuffle the selected
    success rows before assigning evenly spread timestamps with bounded jitter,
    then emit them in chronological order. Work on copies so collection remains
    side-effect free for validation and retry accounting.
    """
    result = [dict(row) for row in rows]
    rng = random.Random(int(run_date.replace("-", "")))
    rng.shuffle(result)
    parsed = datetime.fromisoformat(run_date).replace(tzinfo=timezone.utc)
    start = parsed.replace(hour=8)
    end = parsed.replace(hour=17, minute=59)
    span = (end - start).total_seconds()
    step = span / max(len(result) - 1, 1)
    for index, row in enumerate(result):
        base = start + timedelta(seconds=step * index)
        jitter = rng.uniform(-step * 0.6, step * 0.6)
        stamped = min(max(base + timedelta(seconds=jitter), start), end)
        row["timestamp"] = stamped.strftime("%Y-%m-%dT%H:%M:%SZ")
        row["date"] = run_date
    result.sort(key=lambda row: row["timestamp"])
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();plan=json.loads(args.plan.read_text());date=plan['target_date']
    rows=[];fields=[]
    for name in sorted(glob.glob(str(args.plan.parent/f'daily_plan_{date}*results*.csv'))):
        with open(name,newline='') as stream:
            reader=csv.DictReader(stream)
            fields.extend(f for f in (reader.fieldnames or []) if f not in fields)
            rows.extend(reader)
    selected,missing=collect(plan,rows)
    selected=randomize_daily_rows(selected,date)
    args.output.mkdir(exist_ok=False)
    with (args.output/'typed-successes.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(selected)
    report=dict(date=date,complete=not missing,new_successes=len(selected),new_missing=len(missing),
                legacy_credits=len(plan.get('legacy_transition',{}).get('credits',[])),
                missing_keys=missing,legacy_rows_exported=0,timestamps_preserved=False,
                timestamp_policy='deterministic-shuffle-jitter-08:00-17:59Z')
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='missing_keys'}))

if __name__=='__main__':main()
