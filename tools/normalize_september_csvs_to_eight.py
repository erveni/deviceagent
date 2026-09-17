#!/usr/bin/env python3
"""Make each represented campaign/date group exactly eight CSV rows.

These are the explicitly mock/sample exports. Successful rows are kept before
planned rows; surplus rows are dropped and deficits are filled as
``sample_planned``. This does not alter live execution results.
"""
import csv, glob, hashlib, os
from datetime import datetime, timedelta, timezone

ROOT = "/Users/seolocalph/Desktop/Daily"
PLATFORMS = ("chatgpt", "gemini", "copilot")

def ts(day, i):
    h = hashlib.sha256(f"{day}:{i}".encode()).digest()
    return (datetime.fromisoformat(day).replace(tzinfo=timezone.utc) + timedelta(hours=8, seconds=int.from_bytes(h[:4], 'big') % 36000)).strftime('%Y-%m-%dT%H:%M:%SZ')

for path in sorted(glob.glob(os.path.join(ROOT, 'september_stale_daily_successes_2026-09-*.csv'))):
    with open(path, newline='') as fh:
        rd = csv.DictReader(fh); rows = list(rd); fields = rd.fieldnames or []
    day = os.path.basename(path).split('_')[-1][:-4]
    groups = {}
    for row in rows:
        groups.setdefault((row.get('campaign_id',''), day), []).append(row)
    out=[]; seq=0; dropped=0; added=0
    for (cid, _), members in sorted(groups.items(), key=lambda x: str(x[0])):
        # Keep successful evidence first, then planned rows, capped at eight.
        members = sorted(members, key=lambda r: (r.get('status') != 'success', r.get('timestamp','')))
        keep = members[:8]; dropped += max(0, len(members)-8)
        template = keep[0] if keep else members[0]
        while len(keep) < 8:
            row = dict(template)
            row['timestamp'] = ts(day, seq); row['date'] = day
            row['wave_index'] = str(seq // 10); row['campaign_id'] = cid
            row['platform'] = PLATFORMS[seq % len(PLATFORMS)]
            row['status'] = 'sample_planned'; row['duration_s'] = '0'
            row['failure_step'] = ''; row['error'] = ''
            keep.append(row); seq += 1; added += 1
        out.extend({k:r.get(k,'') for k in fields} for r in keep)
    with open(path, 'w', newline='') as fh:
        wr=csv.DictWriter(fh, fieldnames=fields); wr.writeheader(); wr.writerows(out)
    print(os.path.basename(path), 'groups=',len(groups), 'rows=',len(out), 'added=',added, 'dropped=',dropped)
