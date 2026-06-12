# Signal SEO — Session Handover (2026-06-11)

**Repo/branch:** `device-agent` @ `feature/superproxy-dispatch` · backend `seo-keyword-research` @ `feat/heatmap-and-website-scraper`

Signal SEO = measure local Google rankings for clients daily, then diagnose what to fix so
they climb. **Hard boundary (from the architecture, unchanged): MEASUREMENT + recommendations
only. No CTR / click manipulation — the fleet never clicks or interacts with a result.**

---

## Headline: the captcha blocker is solved

On-phone Google scraping via Decodo **residential** hits reCAPTCHA on a large share of the
shared/burned IP pool — **not fixable in code** (it's IP reputation, not browser/behavior; the
real phone is already the stealthiest possible client). The architecture already anticipated
this: *"For bulk volume, buy licensed data (SerpApi/DataForSEO). No stealth/evasion stack."*

**Resolution:** bulk daily rank measurement now goes through a **SERP API** (Serper.dev — 2,500
free credits, then $0.30/1K; returns organic + local pack + geo). Captcha-free, ~1–2s/query,
no phone. **Proven:** maeschildcare.com = organic **#5** for "bilingual childcare san francisco"
(SF); full daily orchestrator run `3 done, 0 failed`.

The phone fleet keeps its real roles: **authentic low-volume spot-checks + screenshot proof +
the AI engines (ChatGPT/Gemini/Perplexity, which have no API).**

---

## What changed this session

**New — `serp_api_source.py`** — provider-agnostic SERP-API source. Maps the provider response
to the SAME SerpApi shape the on-phone parse emits, so `serpapi_to_ingest` + the report engine
are unchanged. `make_dispatch_query(location)` returns a `process_run`-compatible dispatch_query.
Providers behind one switch (Serper now; Scrape.do/DataForSEO/Decodo-SERP drop in).

**`serp_fleet_worker.py`**
- New `--proxy serper` (+ `--serp-api-key` / `--serp-provider`): no phone, no tunnel, no captcha;
  straight to `process_run`. Backend computes rank from `organic_results` vs `business_domain`.
- `target_domain` now threaded to the device on the gost path (was hardcoded `None`, so every
  on-phone rank came back null even when the business ranked).
- **gost-path tunnel fixes** (these made "site can't be reached" go away):
  - Honor `$MAC_IP` in `_setup_gost` (socksdroid dials the live Mac).
  - **Residential now runs through the SNI relay too** (`relay → local gost → Decodo by
    hostname`). SocksDroid can only IP-CONNECT, which Decodo 522-rejects; the relay re-dials by
    hostname. Old residential branch went gost-direct → 522 on every page.

**`run_with_proxy.py`** — restored commit `4a196f3`'s `_detect_mac_lan_ip()` (a local edit had
clobbered `MAC_IP` back to a stale hardcoded literal). `resolve_proxy_ip` now uses
`--socks5-hostname` (was `--socks5` → 522).

**`signal_seo_daily.py`** — `SIGNAL_SOURCE` env (**DEFAULT `serper`**) switches SERP-API vs
on-phone `gost`. Fixed rank-reading to use the backend's `prompt.organic_position` /
`local_position` (was reading the on-device-only `serp.target.organic_rank` → always showed "—").

**`.env.dev`** (gitignored) — added `SERP_API_KEY` + `SERP_PROVIDER=serper`.

---

## How to run it daily

```bash
set -a; source .env.dev; set +a
ADMIN_TOKEN=test EXECUTOR_TOKEN=test SIGNAL_BASE=http://localhost:8900 \
  python3 signal_seo_daily.py clients.json
```
Backend must be up: `seo-keyword-research` FastAPI on :8900. Cron/launchd once a day for
unattended runs. `clients.json` = the only input (business name, domain, location, keywords).

On-phone spot-check (fallback): `--proxy gost --gateway residential --device-idx 5 --serial
"<(2) mDNS serial>"`. See `seo-proxy-decodo-setup` memory for the 3 tunnel failure modes.

---

## The improvement loop (how rankings actually move)

`MEASURE (daily) → DIAGNOSE (action report) → ACT (the fixes) → RE-MEASURE (trend proves it)`

The report engine (`/serp-runs/{id}/report`) already outputs prioritized levers per surface,
e.g. for maeschildcare: **local_pack** → Google Business Profile (primary category, complete
NAP, business-name keywords) + grow native reviews; **organic** → on-page content targeting the
query + internal/inbound links. `/serp-trends?business=` tracks visibility over time for client
reports. This is where ranking improvement comes from — legitimate, durable, client-safe.

---

## Next steps

1. Build real `clients.json` (5–15 keywords/client, city+state location).
2. Schedule the daily cron (backend must stay up).
3. Work the action report per client (GBP, reviews, content, links).
4. Commit this session's code (currently uncommitted on `feature/superproxy-dispatch`).
5. Optional: add a Decodo/DataForSEO provider to `serp_api_source.py` for scale/redundancy.

Related memory: `captcha-solved-serp-api`, `seo-proxy-decodo-setup`.
