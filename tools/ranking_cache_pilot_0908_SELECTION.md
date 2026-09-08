# Bounded Gemini cache pilot, 2026-09-08

Authorized: ten distinct Gemini ranking jobs, one phone (104), one attempt each,
no full-queue restart. Test APK 82 must be restored to original 79 afterwards.
Stop paid work at 19:52 Asia/Manila; meter settlement ends by 19:57:30, then rollback.
Spend guard 150 MB (delayed provider billing can overshoot).

| Keyword ID | Business | City/state |
|---|---|---|
| 553 | Top Choice Roofing, LLC | Cullman, AL |
| 573 | Canyon Springs Dental | Surprise, AZ |
| 538 | TNT Design & Build | Carlsbad, CA |
| 589 | KD Buys Houses | East Hartford, CT |
| 564 | Green Cooling Solutions | Lakewood Ranch, FL |
| 340 | Mack Engineering | Dunwoody, GA |
| 617 | Bayer Heating & Cooling | Energy, IL |
| 357 | Nurture Nest Play Therapy | Danville, KY |
| 372 | NJ Mold Pros | Manasquan, NJ |
| 399 | AI Advanced Inspections | Chattanooga, TN |

Selection: active IDs in /tmp/kw_admin.json, business/location mapping from
aeo-appium/clients_audit_targets.json, prior Gemini successes in September 4/6/7
CSV files for the stale September 2 set. Deliberately geographically diverse,
but selected for historical completion: NOT a random stale-set estimate.

Direct-network smoke precedes the measured run and can warm HTTP cache. This
tests repeated warm-cache jobs, NOT cold-start cost. All jobs are Gemini; cache
survival across ordinary daily or other-platform full clears is NOT tested.
Account-wide Evomi billed difference includes failed/incomplete pilot attempts;
local GOST counters and browser encoded-byte/cache-hit evidence are separate
accounting layers, not additional billable charges. A deadline-truncated pilot
must be reported as partial, with remaining IDs retained and no extrapolated
fleet savings claim.
