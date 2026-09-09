"""Attach offline polygon-derived timezones; preserve raw lookup evidence.

Install tools/requirements-daily-geo.txt into an isolated preparation environment.
Daily execution only needs the resulting small JSON, not these dependencies.
"""
import argparse
import json
from pathlib import Path
from timezonefinder import TimezoneFinder

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--reviewed',type=Path)
    args=parser.parse_args();data=json.loads(args.source.read_text());tf=TimezoneFinder()
    if args.reviewed:
        for key,item in json.loads(args.reviewed.read_text()).items():
            if key not in data or data[key]['status']!='unresolved':raise ValueError('Review must replace an unresolved key only')
            data[key]=item
    # Spacing variants refer to the identical city; never substitute another city.
    normalize=lambda s:''.join(c for c in s.casefold() if c.isalnum())
    good={normalize(k):v for k,v in data.items() if v.get('status')=='verified'}
    for key,item in list(data.items()):
        if item.get('status')!='verified' and normalize(key) in good:
            data[key]={**good[normalize(key)],'alias_of':normalize(key)}
        item=data[key]
        if item.get('status')=='verified':
            item['timezone']=tf.timezone_at_land(lat=item['latitude'],lng=item['longitude'])
            if not item['timezone']:raise ValueError('Timezone missing: '+key)
            item['timezone_source']='timezonefinder 8.3.0 / timezonefinder-data 1.2026.3'
    with args.output.open('x') as stream:json.dump(data,stream,indent=2)
    print(json.dumps(dict(total=len(data),unresolved=[k for k,v in data.items() if v.get('status')!='verified'])))

if __name__=='__main__':main()
