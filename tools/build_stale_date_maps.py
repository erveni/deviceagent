#!/usr/bin/env python3
"""Build durable pre-run ranking-date maps for stale consolidation."""
import argparse
import json
from pathlib import Path


def build(records, run_date):
    per_keyword={};per_platform={}
    values=records if isinstance(records,list) else list(records.values())
    for row in values:
        keyword=row.get('keywordId');platform=(row.get('platform') or '').lower().strip()
        day=(row.get('date') or '')[:10]
        if keyword is None or not day or day>=run_date:
            continue
        key=str(keyword);per_keyword[key]=max(per_keyword.get(key,''),day)
        if platform:
            pair=f'{key}|{platform}'
            per_platform[pair]=max(per_platform.get(pair,''),day)
    return per_keyword,per_platform


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run_date');parser.add_argument('records',type=Path)
    parser.add_argument('keyword_output',type=Path);parser.add_argument('platform_output',type=Path)
    args=parser.parse_args()
    per_keyword,per_platform=build(json.loads(args.records.read_text()),args.run_date)
    if not per_keyword or not per_platform:raise SystemExit('Refusing empty stale-date maps')
    args.keyword_output.write_text(json.dumps(per_keyword,sort_keys=True)+'\n')
    args.platform_output.write_text(json.dumps(per_platform,sort_keys=True)+'\n')
    print(f'stale-date maps: keyword={len(per_keyword)} platform={len(per_platform)}')


if __name__=='__main__':main()
