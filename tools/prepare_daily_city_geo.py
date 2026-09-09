"""Explicit one-time city lookup; offline daily runs never call Nominatim.

Policy: https://operations.osmfoundation.org/policies/nominatim/
One machine/thread, >=1.2s between calls, persisted results incl misses; no retries.
Only public city/state strings are sent. Source: OpenStreetMap contributors, ODbL.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
import ssl
import certifi

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from daily_geo import location_key


def verified_result(results, city, state):
    normalize=lambda s: ''.join(c for c in s.casefold() if c.isalnum())
    for result in results:
        address=result.get('address',{})
        iso=address.get('ISO3166-2-lvl4','')
        if iso not in ('US-'+state.upper(),'CA-'+state.upper()):continue
        names=[address.get(k,'') for k in ('city','town','village','municipality','suburb','hamlet')]
        names.extend([result.get('name','')])
        if normalize(city) not in {normalize(n) for n in names if n}:continue
        return dict(status='verified',latitude=float(result['lat']),longitude=float(result['lon']),
                    city=city,state=state,display_name=result.get('display_name'),
                    source='OpenStreetMap contributors / Nominatim',license='ODbL',
                    osm_type=result.get('osm_type'),osm_id=result.get('osm_id'))
    return dict(status='unresolved',city=city,state=state)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('locations',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--one-time-lookup',action='store_true',required=True)
    args=parser.parse_args()
    cities={location_key(r['city'],r['state']):(r['city'],r['state']) for r in json.loads(args.locations.read_text())}
    # File lock coordinates local invocations; output is append-only evidence.
    with args.output.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cache={}
        if args.output.exists():
            for line in args.output.read_text().splitlines():
                row=json.loads(line);cache[row['key']]=row['result']
        with args.output.open('a') as stream:
            for key,(city,state) in sorted(cities.items()):
                if key in cache:continue
                country='Canada' if state.upper() in ('ON','QC','BC','AB','MB','NB','NL','NS','NT','NU','PE','SK','YT') else 'USA'
                params=urllib.parse.urlencode(dict(city=city,state=state,country=country,format='jsonv2',addressdetails=1,limit=5))
                url=os.environ.get('DAILY_GEOCODER_URL','https://nominatim.openstreetmap.org/search')+'?'+params
                request=urllib.request.Request(url,headers={'User-Agent':'SignalAEO-device-agent/1.0 (one-time daily campaign city verification)'})
                with urllib.request.urlopen(request,timeout=25,context=ssl.create_default_context(cafile=certifi.where())) as response:
                    result=verified_result(json.load(response),city,state)
                cache[key]=result
                stream.write(json.dumps(dict(key=key,result=result,at=time.time()))+'\n');stream.flush()
                print(f'{len(cache)}/{len(cities)} {city}, {state}: {result["status"]}',flush=True)
                time.sleep(1.2)
        with args.output.with_suffix('.json').open('w') as stream:json.dump(cache,stream,indent=2)
        failures=[key for key in cities if cache[key]['status']!='verified']
        print(json.dumps(dict(total=len(cities),unresolved=failures)),flush=True)
        if failures:raise SystemExit(2)


if __name__=='__main__':main()
