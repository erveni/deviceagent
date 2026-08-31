#!/usr/bin/env python3
"""Build the June-7 daily plan (fresh live catalog).

Rules (per user 2026-06-08):
  - 8 sessions max per CAMPAIGN/location (sample 8 keywords if more).
  - 12 sessions for priority locations: Black Car IQ Lindon (biz 1),
    AppsTango 3300 Triumph (biz 4), Leo Lapuerta 1919 La Branch (campaignName).
    To reach 12 with <12 keywords, repeat keywords on a platform not yet used.
  - Force-cover: specific locations must get a session on a named platform
    (silent-platform alerts), or a specific keyword must be included.
  - One platform per (kw) normally, round-robin; grouping is by campaignName so
    multi-location businesses (Leo) are capped/targeted per location.

DRY_RUN=1 prints the distribution + priority/force-cover checks, no API calls,
no plan written. Without DRY_RUN it calls /api/llm/build-session and writes
daily_plan_2026-06-08.json.
"""
from __future__ import annotations
import csv, glob, json, os, random, re, sys, urllib.request
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("SSL_CERT_FILE", __import__("certifi").where())
ADMIN = os.environ.get("ADMIN_BASE", "https://jjm59vpn3y.us-east-1.awsapprunner.com")
TOKEN = os.environ["EXECUTOR_TOKEN"]
# Tunable: the local Ollama build server is model-bound, not network-bound. Measured on
# qwen2.5:7b, 8 workers gives only 2.1x the throughput of 1 and pushes latency to ~50s,
# which crowds the default 60s call timeout.
BUILD_WORKERS = int(os.environ.get("BUILD_WORKERS", "8"))
BUILD_TIMEOUT_S = int(os.environ.get("BUILD_TIMEOUT_S", "60"))
H = {"X-Executor-Token": TOKEN}
DATE = os.environ.get("DATE", "2026-06-08")
PLAN_PATH = os.environ.get(
    "PLAN_PATH", f"/Users/seolocalph/projects/device-agent/daily_plan_{DATE}.json")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
PLATFORMS = ["ChatGPT", "Gemini", "Perplexity"]
CAP = 8
PRIORITY_TARGET = 12
random.seed(20260607)

EXCLUDED_BIZ_NAMES = {"Caspian Painting Co, Inc.", "Nez Perce Traditions Gift Shop",
                      "Smith's Enterprise"}

# priority locations -> 12 sessions. Match by business_id or campaignName substring.
def is_priority(biz_id, campaign_name):
    if biz_id in (1, 4):                       # Black Car IQ Lindon, AppsTango Triumph
        return True
    if "1919 La Branch" in (campaign_name or ""):  # Leo Lapuerta 1919
        return True
    return False

# force-cover: campaignName substrings -> platform that MUST appear.
FORCE_PLATFORM = [
    (("Calderon", "454 San Jose"), "ChatGPT"),
    (("Alpha Dental Excellence", "Langhorne"), "Perplexity"),
    (("Source Pest Control", "Temecula"), "ChatGPT"),
    (("Vellum Architecture", "Asheville"), "Perplexity"),
]
# force-cover: campaignName substrings -> keyword text that MUST be included.
# Force-include a specific keyword for a campaign (matched on exact keywordText).
# NOTE: "basement finishing atlanta" (Atlanta Basement Design Roswell, biz 42) was
# removed 2026-06-08 — that keyword WON (status=locked, isActive=False) and was
# replaced by new variants, so forcing it was a no-op. Re-add entries here only
# for keywords that are still active in the catalog.
FORCE_KEYWORD = [
]


def api(path):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(ADMIN + path, headers=H), timeout=120))


def active(o):
    return o.get("isActive") or o.get("status") == "active"


def match(name, subs):
    n = (name or "").lower()
    return all(s.lower() in n for s in subs)


print("fetching live catalog…", flush=True)
biz_by_id = {b["id"]: b for b in api("/api/businesses")}
kws = api("/api/keywords")
clients = api("/api/clients")
active_client_ids = {c["id"] for c in clients if active(c)}
excluded_biz_ids = {bid for bid, b in biz_by_id.items()
                    if (b.get("name") or b.get("businessName") or "") in EXCLUDED_BIZ_NAMES}
# Daily exclusion rule (per user 2026-07-22): a keyword is dropped from the daily
# ONLY when it is BOTH in a free-trial plan AND ranks top 1-3. Free-trial keywords
# that are NOT top-3 RUN; non-free-trial top-3 keywords RUN. Top-3 is keyed on
# (biz_name, keyword) with rank_position 1..3 from the ranking audit CSVs — the
# same field used to detect top-3 last session.
_excl_plan_file = os.environ.get("EXCLUDE_PLAN_IDS_FILE", "/tmp/exclude_plan_ids.json")
free_trial_plan_ids = set(json.load(open(_excl_plan_file))) if os.path.exists(_excl_plan_file) else set()

def _to_int(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None

_rank_glob = os.environ.get("RANK_CSVS", "rabbitmq_audit_results_2026-07-17_ranking_*.csv")
top3_keys = set()   # (biz_name_lower, keyword_lower)
for _rp in sorted(glob.glob(_rank_glob)):
    for _r in csv.DictReader(open(_rp, newline="")):
        _pos = _to_int(_r.get("rank_position"))
        if _pos is not None and 1 <= _pos <= 3:
            top3_keys.add(((_r.get("biz_name") or "").strip().lower(),
                           (_r.get("keyword") or "").strip().lower()))
print(f"free-trial plans: {len(free_trial_plan_ids)}; top-3 (biz,kw) keys: "
      f"{len(top3_keys)} from '{_rank_glob}'")

def is_free_trial_top3(k, b):
    """Exclude iff BOTH free-trial plan AND this (biz_name, keyword) ranks top 1-3."""
    if k.get("aeoPlanId") not in free_trial_plan_ids:
        return False
    bn = (b.get("name") or b.get("businessName") or "").strip().lower()
    kt = (k.get("keywordText") or "").strip().lower()
    return (bn, kt) in top3_keys

_n_ft_top3 = 0   # keywords dropped by the free-trial-AND-top-3 rule

# collect active keywords with their campaign/location
items = []   # dict(kw, biz, campaign)
for k in kws:
    if not active(k):
        continue
    bid = k.get("businessId")
    b = biz_by_id.get(bid)
    if not b or not active(b) or b.get("clientId") not in active_client_ids:
        continue
    if bid in excluded_biz_ids:
        continue
    if is_free_trial_top3(k, b):
        _n_ft_top3 += 1
        continue
    items.append({"kw": k, "biz": b, "bid": bid,
                  "campaign": k.get("campaignName") or f"biz{bid}"})
print(f"dropped {_n_ft_top3} keywords by free-trial-AND-top-3 rule")

# group by campaign/location. Key on (campaignName, businessId): dozens of distinct
# free-trial businesses share the generic campaignName "Free Trial" and must not
# collapse into one 8-session bucket. Same business, distinct campaign names (e.g.
# Leo's per-location campaigns) still separate correctly on the name component.
by_campaign = defaultdict(list)
for it in items:
    by_campaign[(it["campaign"], it["bid"])].append(it)
print(f"active keywords: {len(items)} across {len(by_campaign)} campaigns/locations")

# assign (kw, biz, platform) specs per campaign with cap/priority/force-cover
specs = []
report = []
for camp_off, ((camp, _gbid), its) in enumerate(by_campaign.items()):
    bid = its[0]["bid"]
    biz = its[0]["biz"]
    prio = is_priority(bid, camp)
    kws_here = list(its)
    random.shuffle(kws_here)
    used = defaultdict(set)            # kw_id -> {platform}
    chosen = []                        # (it, platform)

    # forced keyword present? (e.g. Atlanta "basement finishing atlanta")
    forced_kw = None
    for subs, kwtext in FORCE_KEYWORD:
        if match(camp, subs):
            forced_kw = kwtext.lower()
    # forced platform for this campaign?
    forced_plat = None
    for subs, plat in FORCE_PLATFORM:
        if match(camp, subs):
            forced_plat = plat

    target = PRIORITY_TARGET if prio else min(CAP, len(kws_here))

    # seed: ensure forced keyword is included first (on forced platform if any, else round-robin)
    pi = 0
    if forced_kw:
        fk = next((x for x in kws_here if x["kw"]["keywordText"].strip().lower() == forced_kw), None)
        if fk:
            plat = forced_plat or PLATFORMS[pi % 3]; pi += 1
            used[fk["kw"]["id"]].add(plat); chosen.append((fk, plat))
    # ensure forced platform appears at least once
    if forced_plat and not any(p == forced_plat for _, p in chosen):
        anykw = kws_here[0]
        used[anykw["kw"]["id"]].add(forced_plat); chosen.append((anykw, forced_plat))

    # fill to target: one platform per fresh keyword first, then repeat on new platforms.
    # Round-robin the platform across assignments so the campaign (and the day) splits
    # roughly evenly across ChatGPT/Gemini/Perplexity instead of piling onto avail[0].
    i = 0
    guard = 0
    while len(chosen) < target and guard < target * 8:
        guard += 1
        it = kws_here[i % len(kws_here)]
        i += 1
        avail = [p for p in PLATFORMS if p not in used[it["kw"]["id"]]]
        if not avail:
            continue
        plat = PLATFORMS[(len(chosen) + camp_off) % 3]
        if plat not in avail:
            plat = avail[0]
        used[it["kw"]["id"]].add(plat); chosen.append((it, plat))

    for it, plat in chosen:
        specs.append((it["kw"], it["biz"], plat))
    report.append((camp, bid, prio, len(kws_here), len(chosen), forced_plat, bool(forced_kw)))

print(f"\nTOTAL sessions planned: {len(specs)}")
print(f"campaigns at cap>8 (sampled): {sum(1 for r in report if not r[2] and r[3] > CAP)}")
print("platform split:", dict(Counter(p for _, _, p in specs)))

# checks
print("\n=== PRIORITY (should be 12) ===")
for camp, bid, prio, nk, nc, fp, fk in report:
    if prio:
        print(f"  [{nc}] biz{bid} {camp[:60]}")
print("\n=== FORCE-COVER ===")
for camp, bid, prio, nk, nc, fp, fk in report:
    if fp or fk:
        flags = []
        if fp:
            ok = any(p == fp and (kw.get('businessId') == bid)
                     for kw, b, p in specs if (b.get('name') or '') )  # loose
            flags.append(f"platform={fp}")
        if fk:
            flags.append("keyword-forced")
        print(f"  [{nc}] biz{bid} {camp[:55]} -> {', '.join(flags)}")

if DRY_RUN:
    print("\nDRY_RUN=1 — no API calls, no plan written.")
    # per-campaign sample of the biggest
    big = sorted(report, key=lambda r: -r[4])[:8]
    print("\nlargest campaigns:")
    for camp, bid, prio, nk, nc, fp, fk in big:
        print(f"  {nc} sessions (kw={nk}{' PRIORITY' if prio else ''}) {camp[:55]}")
    sys.exit(0)

# ---- enrich via build-session + write plan ----
def build_session(kw_id, platform):
    # Retry transient network/SSL blips: one failed call among ~1.6k must not abort
    # the whole build (ThreadPoolExecutor.map re-raises the first exception).
    import time
    body = json.dumps({"keyword_id": kw_id, "platform": platform.lower()}).encode()
    req = urllib.request.Request(f"{ADMIN}/api/llm/build-session", data=body,
                                 headers={**H, "Content-Type": "application/json"}, method="POST")
    for attempt in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=BUILD_TIMEOUT_S))
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 5:
                return None   # persistent failure: caller drops this one session
            time.sleep(2 * (attempt + 1))


def extract_zip(addr):
    # LAST 5-digit group — the zip sits at the address tail; the first group is
    # often the street number (e.g. "21312 Provincial Blvd, Katy TX 77450").
    zips = re.findall(r"\b(\d{5})\b", addr or "")
    return zips[-1] if zips else ""


def make_job(kw, biz, plat, sess):
    addr = biz.get("publishedAddress") or sess.get("searchAddress") or ""
    return {
        "client_id": sess.get("clientId") or biz.get("clientId"),
        "client_name": "",
        "campaign_id": sess.get("campaignId") or (biz["id"] * 10000 + kw["id"]),
        "campaign_name": kw.get("campaignName") or f"{biz.get('name','')} — {addr}".strip(" —"),
        "business_id": biz["id"], "keyword_id": kw["id"],
        "keyword_text": kw.get("keywordText") or "", "platform": plat,
        "biz_name": sess.get("bizName") or biz.get("name") or "",
        "biz_city": sess.get("city") or biz.get("city") or "",
        "biz_state": sess.get("state") or biz.get("state") or "",
        "biz_zip": sess.get("zip") or extract_zip(addr),
        "biz_lat": biz.get("latitude") or 0, "biz_lng": biz.get("longitude") or 0,
        "biz_timezone": biz.get("timezone") or "America/Los_Angeles",
        "biz_address": sess.get("searchAddress") or addr,
        "gmb_url": biz.get("gmbUrl") or biz.get("websiteUrl"),
        "backlinks": [{"url": sess["backlinkUrl"], "type": sess.get("backlinkType") or "", "domain": ""}]
                     if sess.get("backlinkUrl") else [],
        "prompt": sess.get("prompt") or "", "follow_up": sess.get("followUp") or "",
        "backlink_injected": bool(sess.get("backlinkInjected")),
        "backlink_url": sess.get("backlinkUrl"),
        "keyword_variant": sess.get("variantText") or kw.get("keywordText") or "",
        "variant_id": sess.get("variantId"),
    }


print(f"\nfetching {len(specs)} build-session prompts…", flush=True)
failed = []   # (keyword_id, platform) whose build-session persistently 500'd
def fetch(s):
    kw, biz, plat = s
    sess = build_session(kw["id"], plat)
    if sess is None:
        failed.append((kw["id"], plat))
        return None
    return make_job(kw, biz, plat, sess)
with ThreadPoolExecutor(max_workers=BUILD_WORKERS) as ex:
    jobs = [j for j in ex.map(fetch, specs) if j is not None]
if failed:
    print(f"WARN: dropped {len(failed)} sessions on persistent build-session failure: "
          f"{failed[:20]}{'…' if len(failed) > 20 else ''}")

# wave-pack (10/wave, no same client_id or campaign_id within a wave)
random.shuffle(jobs)
waves, rest = [], list(jobs)
while rest:
    wave, uc, ug, leftover = [], set(), set(), []
    for j in rest:
        if len(wave) < 10 and j["client_id"] not in uc and j["campaign_id"] not in ug:
            wave.append(j); uc.add(j["client_id"]); ug.add(j["campaign_id"])
        else:
            leftover.append(j)
    waves.append(wave); rest = leftover

json.dump({"generated_at": None, "total_jobs": len(jobs), "_source": "build_jun07_plan.py",
           "waves": waves}, open(PLAN_PATH, "w"), indent=1)
print(f"wrote {PLAN_PATH}: {len(jobs)} jobs, {len(waves)} waves")
print("empty prompts:", sum(1 for j in jobs if not (j.get('prompt') or '').strip()))
