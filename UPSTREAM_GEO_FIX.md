# Upstream geo-data fix list — AEOAdmin

Campaign `search_address` values whose ranking audits fail with `city, state required`,
AFTER the device-agent geo fixes (case-insensitive state, no-comma `City ST ZIP`, street
geocoding with a wrong-city safety guard). These CANNOT be auto-resolved safely — they need
a complete **street, city, ST ZIP** in AEOAdmin.

## A) Incomplete search_address — neighborhood/region only, no state/zip
_9 campaigns; ~45 keywords. Auto-geocoding these hits the wrong metro (e.g. 'South Congress' → New Haven CT), so it's blocked on purpose._


**Voice depot** (Mary and Russell Thornton)
- plan `390` (5 kw): `100 SE 2nd St,Brickell`
- plan `392` (5 kw): `401 E Jackson St,Downtown`
- plan `393` (5 kw): `823 Congress Ave,South Congress`
- plan `394` (5 kw): `200 E 42nd St,Midtown`
- plan `395` (5 kw): `5075 Westheimer Rd, Galleria`
- plan `396` (5 kw): `233 S Wacker Dr,River North`
- plan `397` (5 kw): `1801 California St, RiNo`
- plan `398` (5 kw): `2000 McKinneyAve, Uptown`
- plan `401` (5 kw): `135 W Central Blvd,Downtown`

## B) No search_address at all (run failures, plan absent from campaign_addr)
- plan `352` — Yellow Brick Road Prom and Formals . (Yellow Brick Road Prom and Formals .), 5 kw: **set a search_address**

## C) Excluded — not fixable / not applicable (skip in audits)
- plan `179` — ?: `123 Textas` (test / non-US / junk)
- plan `80` — Crown Industrial Roofing: `227 Queens Plate Drive Unit #3, Etobicoke, ON M9W 6Z7, Canada` (test / non-US / junk)
- plan `277` — DealerKey Auto LLC: `University Ave corridor, Freedom Blvd near I-15` (test / non-US / junk)
- plan `350` — ZZZ TEST AUDIT DO NOT CONTACT: `Testville, ZZ` (test / non-US / junk)
