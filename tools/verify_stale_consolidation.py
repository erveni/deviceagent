#!/usr/bin/env python3
"""Verify every consolidated row uses its exact missed bi-weekly slot."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path


def expected_date(keyword_id,platform,per_keyword,per_platform,keywords,run_date):
    prior=per_platform.get(f'{keyword_id}|{platform}') or per_keyword.get(str(keyword_id))
    if prior:return (dt.date.fromisoformat(prior)+dt.timedelta(days=14)).isoformat()
    created=(keywords.get(int(keyword_id),{}).get('createdAt') or '')[:10]
    return created or run_date


def verify(rows,per_keyword,per_platform,keywords,run_date):
    seen=set()
    for row in rows:
        pair=((row.get('campaign_id') or '').strip(),(row.get('platform') or '').lower().strip())
        if not pair[0] or not pair[1] or pair in seen:raise ValueError(f'duplicate/malformed pair: {pair}')
        seen.add(pair)
        keyword_id=int(pair[0])%10000
        expected=expected_date(keyword_id,pair[1],per_keyword,per_platform,keywords,run_date)
        if row.get('date')!=expected:raise ValueError(f'{pair} date={row.get("date")} expected={expected}')
        if (row.get('status') or '').lower()!='success':raise ValueError(f'{pair} is not validated success')
    if not rows:raise ValueError('consolidated stale deliverable is empty')
    return len(rows)


def main():
    if len(sys.argv)!=6:raise SystemExit('usage: verify_stale_consolidation.py RUN_DATE CSV KW_MAP PP_MAP KW_ADMIN')
    run_date,csv_path,kw_map,pp_map,kw_admin=sys.argv[1:]
    rows=list(csv.DictReader(open(csv_path)))
    count=verify(rows,json.load(open(kw_map)),json.load(open(pp_map)),
                 {x['id']:x for x in json.load(open(kw_admin))},run_date)
    print(f'verified {count} stale rows: per-platform prior date +14, or keyword createdAt')


if __name__=='__main__':main()
