"""Durable typed daily: bounded dispatch, slot consolidation, idempotent API import.

Does not restart ranking or other dates. Failed/partial runs remain explicit.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from daily_prompt_plan import validate_typed_plan

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('plan',type=Path)
    p.add_argument('output',type=Path);p.add_argument('--smoke-report',type=Path,required=True)
    args=p.parse_args();os.chdir(ROOT)
    plan_path=args.plan.resolve();plan=json.loads(plan_path.read_text());validate_typed_plan(plan)
    smoke=json.loads(args.smoke_report.read_text())
    if smoke.get('status')!='settled' or smoke.get('scheduled')!=3 or smoke.get('successes')!=3:
        raise ValueError('A settled three-platform smoke is required')
    if not 0<smoke.get('used_mb',0)<=100:raise ValueError('Smoke exceeded measured sample budget')
    out=args.output.resolve();out.mkdir(exist_ok=False);delivery=out/'delivery'
    env=os.environ.copy();date=plan['target_date']
    env.update(DAILY_PLAN_PATH=str(plan_path),DAILY_REMAIN_PATH=str(ROOT/f'daily_plan_{date}.eight-remaining.json'),
        DAILY_RUN_LABEL='eight-release',DAILY_DELIVERY_DIR=str(delivery),PROXY_PROVIDER='evomi',
        MAX_PARALLEL='8',DAILY_MAX_ROUNDS='3',DAILY_BUDGET_MB='8500',DAILY_BALANCE_FLOOR_MB='9000',
        DAILY_METER_LEDGER=str(out/'meter.jsonl'),DAILY_ADMISSION_DEADLINE_EPOCH=str(time.time()+8*3600),
        DEVICE_EXCLUDE='device-102,device-105,device-107,device-108,device-111,device-112,device-114,device-115,device-124,device-125')
    # Immutable Bash snapshots prevent mid-run source edits changing its parse.
    for name in ('daily_full_auto.sh','run_daily_auto.sh'):
        (out/name).write_bytes((ROOT/name).read_bytes())
        subprocess.run(['bash','-n',str(out/name)],check=True)
    env['DAILY_AUTO_SCRIPT']=str(out/'run_daily_auto.sh')
    report=dict(status='running',date=date,plan=str(plan_path),budget_mb=8500,floor_mb=9000,
                started_at=time.time(),smoke_report=str(args.smoke_report.resolve()))
    def save():(out/'report.json').write_text(json.dumps(report,indent=2))
    save()
    try:
        with (out/'launcher.log').open('x') as log:
            run=subprocess.run(['bash',str(out/'daily_full_auto.sh'),date],env=env,stdout=log,stderr=subprocess.STDOUT)
        report['runner_exit']=run.returncode
        summary=json.loads((delivery/'report.json').read_text());report['delivery']=summary
        if summary['new_successes']:
            backend=Path('/Users/seolocalph/projects/AEOAdmin-daily-eight')
            secret=json.loads(subprocess.check_output(['aws','secretsmanager','get-secret-value','--secret-id','aeo-admin/prod',
                '--profile','aeo-admin','--region','us-east-1','--query','SecretString','--output','text'],stderr=subprocess.PIPE))
            import_env={**os.environ,'API_BASE':'https://jjm59vpn3y.us-east-1.awsapprunner.com',
                        'EXECUTOR_TOKEN':secret['EXECUTOR_TOKEN'],'DATABASE_URL':secret['DATABASE_URL']}
            with (out/'import.log').open('x') as log:
                imported=subprocess.run(['node',str(backend/'scripts/import-daily-sessions-api.mjs'),str(delivery/'typed-successes.csv')],
                    cwd=backend,env=import_env,stdout=log,stderr=subprocess.STDOUT)
            report['import_exit']=imported.returncode
            if imported.returncode:raise RuntimeError('Daily API import incomplete; inspect import.log')
        report['status']='complete' if run.returncode==0 and summary['complete'] else 'partial-stopped'
    except Exception as error:
        report.update(status='error',error=str(error));raise
    finally:
        report['finished_at']=time.time();save()
    print(json.dumps(report),flush=True)
    if report['status']!='complete':raise SystemExit(3)

if __name__=='__main__':main()
