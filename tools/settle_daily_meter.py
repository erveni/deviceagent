"""Read-only final settlement for an already stopped daily sample/run."""
import argparse
import csv
import json
from pathlib import Path
from measure_evomi_targeting import idle,settle

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger',type=Path);parser.add_argument('plan',type=Path)
    parser.add_argument('output',type=Path);args=parser.parse_args()
    if args.output.exists():raise ValueError('Output already exists')
    if not idle():raise ValueError('Local proxy workload still active')
    before=json.loads(args.ledger.read_text().splitlines()[0])['balance_mb']
    after=settle(before=before)
    plan=json.loads(args.plan.read_text());jobs=[j for w in plan['waves'] for j in w]
    rows=[r for p in args.plan.parent.glob(args.plan.stem+'_results*.csv') for r in csv.DictReader(p.open())]
    success={r['daily_slot_id'] for r in rows if r.get('status')=='success'}
    used=before-after
    report=dict(status='settled',before_mb=before,after_mb=after,used_mb=used,
                scheduled=len(jobs),rows=len(rows),successes=len(success),
                mb_per_job=used/len(jobs),mb_per_success=used/len(success) if success else None,
                limitation='Account-wide meter; cannot exclude remote consumers; small smoke is not a forecast')
    with args.output.open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
