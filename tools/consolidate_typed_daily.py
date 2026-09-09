"""Export typed successes by slot without rewriting timestamps or replaying legacy credits."""
import argparse
import csv
import glob
import json
from pathlib import Path
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
    args.output.mkdir(exist_ok=False)
    with (args.output/'typed-successes.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(selected)
    report=dict(date=date,complete=not missing,new_successes=len(selected),new_missing=len(missing),
                legacy_credits=len(plan.get('legacy_transition',{}).get('credits',[])),
                missing_keys=missing,legacy_rows_exported=0,timestamps_preserved=True)
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='missing_keys'}))

if __name__=='__main__':main()
