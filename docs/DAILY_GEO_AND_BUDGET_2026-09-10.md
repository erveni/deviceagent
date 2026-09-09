# Daily location and spending guards

Typed daily uses campaign city/state for prompts, city-level GPS and timezone.
It no longer takes GPS/timezone from a business headquarters elsewhere.
Missing coordinates/timezone fail before phone dispatch; no zero/HQ fallback.

`daily_city_geo.json` contains156 reviewed city/state keys covering265 campaigns.
Coordinates are reference locations, not precise building coordinates. Source:
[OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed
under ODbL. Record-level OSM IDs and provenance are retained. The four reviewed
municipality/neighborhood names are in tools/daily_geo_reviewed_20260910.json.
Timezone polygons:timezonefinder8.3.0/timezonefinder-data1.2026.3.

Preparation is explicit and offline from Evomi. tools/prepare_daily_city_geo.py
performs a one-time single-threaded lookup below1request/second, caches misses
as well as matches, and never retries automatically. Respect the
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).
Daily runs do not make geocoding requests. New locations need reviewed cache entries.

Typed daily defaults:12000MB admission budget and9000MB balance floor, at most3
outer rounds, no inner retries, Copilot at most4 concurrent. devices108/125 excluded.
`DAILY_METER_LEDGER` preserves one baseline across retry rounds. Meter errors,
increases, budget exhaustion or floor crossing stop new admissions. Already-running
jobs finish: this is not a hard billing cap, and meter lag can cause overshoot.
The account meter cannot distinguish remote account consumers.

Release requires deployed API capability, successful measured phone smoke and
matching saved slot metadata. Local tests, pushing, and uploading frontend assets
alone do not mean the daily is running.
