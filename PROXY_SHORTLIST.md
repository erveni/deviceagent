# Proxy Shortlist — "Like Decodo, Cheaper"

**Date:** 2026-08-14 · **Goal:** residential/ISP proxy with **US city/ZIP targeting + SOCKS5 + sticky (hold one IP ≥150s)**, **cheaper than Decodo**. Prices as-of 2026-08-14, from official pages + reputable trackers.

**Number to beat (Decodo):** $4/GB PAYG · **$2.75/GB** self-serve 100 GB · ~$2/GB only at enterprise. Decodo does US zip + SOCKS5 + 30-min sticky.

> Residential city/ZIP accuracy is pool-dependent industry-wide (~55–80%), and "sticky" on residential is best-effort (home IPs can drop). **Validate zip accuracy + SOCKS5 + 150s hold on a few trial GB before switching production.**

---

## A. Confirmed match (city + ZIP + SOCKS5 + sticky) AND cheaper — ranked by realistic $/GB

| # | Provider | Realistic $/GB | ZIP | Sticky max | Free trial | Notes |
|---|---|---:|---|---|---|---|
| 1 | **Evomi** | **$0.49** flat | yes (extra bandwidth) | 24h | 1-day free | Cheapest w/ zip. ~7× under Decodo. ZIP filter bills extra bw — model it. |
| 2 | **abcproxy** | ~$0.77 (real-world ~$2) | yes* | 30 min (24h per-IP) | no | Very cheap, but site blocks scrapers → **verify zip+SOCKS5 on a live test**. |
| 3 | **Nodemaven** | **$2.20** flat | **yes (confirmed)** | 24h | paid ($3.50/750MB) | **Cleanest fully-verified match** on official pages. Safe "just works" pick. |
| 4 | **Rayobyte** | $3.50 → **$2.00 @50GB+** | **yes (explicit `-zip-` param)** | 24h | **yes, free** | Best-documented + free trial → **easiest to validate**. |
| 5 | **Webshare** | $3.50 → $1.40 @~3TB | **yes (confirmed)** | 30m–24h | free tier | Cheap only at multi-TB; free tier good for a pilot. |
| 6 | **Infatica** | $4 PAYG → $2.90 @241GB | **yes (confirmed)** | 60 min | 7-day $4 | Only beats Decodo at 241GB+ volume. |

\* claimed by vendor, not independently confirmable (site blocked) — verify live.

## B. City-only (no ZIP) but very cheap — fine for **daily engagement**, not zip-exact ranking

| Provider | $/GB | SOCKS5 | Sticky | Notes |
|---|---:|---|---|---|
| **Geonode** | **$0.79 → $0.27** | yes | 3 min–24h | Cheapest overall. City is finest grain (no zip). Great for daily. |
| **DataImpulse** (current) | $1.00 | yes | our sticky-port | Reportedly *does* offer zip as a paid add-on (~$2/GB, format unconfirmed) — **worth a support question**; if real, we may not need Decodo. |

## C. Avoid — safety / reliability

| Provider | Why |
|---|---|
| **NetNut** | **FBI-seized Jul 2026** (Popa botnet, ~2M hijacked devices). Do not use. |
| **PIA S5** | Cheap + zip + SOCKS5, but caught in Jan 2026 Google/IPIDEA botnet takedown; successor unstable. |
| **922 S5** | Official domains don't resolve; only reseller mirror data. Verify entity first. |

## D. Fail our criteria

SOAX (zip only on $1.5k/mo tier) · Massive ($4.90/GB, SOCKS5 TCP-only) · Ping/Byteful (zip unconfirmed) · Thordata (no zip, no SOCKS5) · IPRoyal ($5.25/GB) · PacketStream & Proxy-Cheap (geo country-only/unconfirmed) · Live Proxies (HTTP-only B2C) · Nimbleway (no SOCKS5).

---

## Recommendation

1. **Trial 3, cheapest-confirmed-first:** **Evomi ($0.49)**, **Rayobyte** (free trial, explicit zip param), **Nodemaven ($2.20, cleanest match)**. Buy a few GB, run our ranking capture on real keywords, check: zip/city accuracy, SOCKS5 works, one IP holds ≥150s.
2. **Likely outcome:** if Evomi's zip accuracy holds → switch (≈7× cheaper than Decodo). If not → Rayobyte/Nodemaven at ~$2/GB, still cheaper + fully confirmed.
3. **Daily engagement:** Geonode ($0.79, city-only) or keep DataImpulse ($1) — zip not needed there.
4. **Integration effort:** small — adding a provider is the same username-scheme branch in `gost_manager.py` we just did for DataImpulse (sticky port + geo params).

**Bottom line:** yes, cheaper-than-Decodo with zip exists. Evomi is the headline ($0.49/GB); Rayobyte/Nodemaven are the safe ~$2/GB confirmed picks. Validate on trial GB before cutting over.
