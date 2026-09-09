"""Offline, exact city/state GPS lookup for typed daily. Never use HQ fallback."""
import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo


def location_key(city, state):
    return ' '.join(city.split()).casefold() + '|' + state.strip().upper()


def coordinates(city, state, cache=None):
    if cache is None:
        path=Path(os.environ.get('DAILY_GEO_CACHE', 'daily_city_geo.json'))
        if not path.exists():raise ValueError('Verified daily GPS cache missing; prepare it before building')
        cache=json.loads(path.read_text())
    item=cache.get(location_key(city,state))
    if not item or item.get('status')!='verified':
        raise ValueError(f'No verified campaign GPS for {city}, {state}; refusing headquarters fallback')
    lat,lon=float(item['latitude']),float(item['longitude'])
    if not all(map(math.isfinite,(lat,lon))) or not -90<=lat<=90 or not -180<=lon<=180 or (lat==0 and lon==0):
        raise ValueError('Invalid campaign coordinates')
    timezone=item.get('timezone')
    if not timezone:raise ValueError('Verified campaign timezone missing')
    ZoneInfo(timezone)
    return lat,lon,timezone
