"""Select three real outstanding daily slots without inventing test duplicates."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from daily_prompt_plan import validate_typed_plan

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();plan=json.loads(args.plan.read_text());validate_typed_plan(plan)
    jobs=[j for w in plan['waves'] for j in w]
    candidates=[j for j in jobs if 'yokl' in j.get('biz_name','').lower()]
    selected=[]
    for platform in ('chatgpt','gemini','copilot'):
        matches=[j for j in candidates if j['platform']==platform]
        if not matches:raise ValueError('No outstanding YOKL slot for '+platform)
        selected.append(matches[0])
    smoke=dict(daily_protocol='eight-v1',target_date=plan['target_date'],is_remaining=True,
               total_jobs=3,_source=str(args.plan),waves=[selected])
    validate_typed_plan(smoke)
    with args.output.open('x') as stream:json.dump(smoke,stream,indent=2)
    print(json.dumps([dict(platform=j['platform'],type=j['prompt_type'],slot=j['daily_slot_id'],
                           keyword=j['keyword_text']) for j in selected],indent=2))

if __name__=='__main__':main()
