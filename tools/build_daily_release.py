"""Build a new typed plan using deployed capability and in-memory credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',required=True);parser.add_argument('--plan',required=True)
    parser.add_argument('--legacy-plan')
    args=parser.parse_args()
    os.chdir(ROOT)
    secret=json.loads(subprocess.check_output(['aws','secretsmanager','get-secret-value',
        '--secret-id','aeo-admin/prod','--profile','aeo-admin','--region','us-east-1',
        '--query','SecretString','--output','text'],stderr=subprocess.PIPE))
    os.environ.update(DATE=args.date,PLAN_PATH=args.plan,EXECUTOR_TOKEN=secret['EXECUTOR_TOKEN'])
    os.environ.pop('DRY_RUN',None);os.environ.pop('DAILY_CATALOG_DIR',None)
    if args.legacy_plan:
        os.environ.update(DAILY_LEGACY_POLICY='credit-existing-toward-eight',DAILY_LEGACY_PLAN=args.legacy_plan)
    from build_daily_eight import main as build
    build()

if __name__=='__main__':main()
