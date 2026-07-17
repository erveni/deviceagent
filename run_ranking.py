"""May 25 RANKING runner — standalone, no broker.

Drives 299 ranking jobs (154 INITIAL_RANKING + 145 RANKING, 3 biz excluded)
through audit_dispatch_http.dispatch_audit_job — the same HTTP polling path
the rolling consumer uses. Pure Python, no scheduler/orchestrator/broker.

Each worker:
  - takes next JobRecord
  - calls build_audit_dispatch_job(jr)            (no API calls)
  - calls dispatch_audit_job(audit_job, platform) (acquires phone, gost,
                                                  POST /session, polls /status,
                                                  writes CSV row, cleans up)
  - loops to next job

Output: rabbitmq_audit_results_2026-05-27.csv (same schema/path the consumer
would have written to).

Usage:
  DRY_RUN=1 python3 run_may27_ranking_standalone.py    # show counts only
  python3 run_may27_ranking_standalone.py              # execute (10 phones)
"""
from __future__ import annotations
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# device-agent imports — same modules the rolling consumer uses
sys.path.insert(0, "/Users/seolocalph/projects/device-agent")
from audit_dispatch_http import build_audit_dispatch_job, dispatch_audit_job
from run_with_proxy import DEVICES

import datetime as _dt
ANCHOR_DATE = os.environ.get("DATE", "2026-06-08")
CUTOFF = (_dt.date.fromisoformat(ANCHOR_DATE) - _dt.timedelta(days=14)).isoformat()
TARGET_DATE_ISO = f"{ANCHOR_DATE}T18:00:00-07:00"
SOURCE_TAG = os.environ.get("SOURCE_TAG", f"ranking_{ANCHOR_DATE}")
EXCLUDED_BIZ_NAMES = {
    "Caspian Painting Co, Inc.",
    "Nez Perce Traditions Gift Shop",
    "Smith's Enterprise",
}
PLATFORMS = tuple(
    p.strip() for p in os.environ.get("PLATFORMS", "chatgpt,gemini,perplexity").split(",") if p.strip()
)
CSV_PATH = os.environ.get(
    "AUDIT_CSV",
    f"/Users/seolocalph/projects/device-agent/rabbitmq_audit_results_{ANCHOR_DATE}_full.csv",
)
WORKERS = int(os.environ.get("WORKERS", str(len(DEVICES))))  # default = phone count
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
# Tunnel warmup gate: run one canary job per phone first and abort the batch if
# fewer than WARMUP_MIN_FRAC of phones get a live tunnel (avoids grinding the
# whole batch against dead tunnels). WARMUP_GATE=0 disables.
WARMUP_GATE = os.environ.get("WARMUP_GATE", "1") == "1"
WARMUP_MIN_FRAC = float(os.environ.get("WARMUP_MIN_FRAC", "0.5"))

# Load catalog (refresh via /tmp/fetch_catalog_full.py if missing)
biz_by_id = {b["id"]: b for b in json.load(open("/tmp/biz_admin.json"))}
kws       = json.load(open("/tmp/kw_admin.json"))
rr        = json.load(open("/tmp/rr_admin.json"))
# Campaign search_address is the authoritative geo source — a business may run
# campaigns in several locations, so geo must resolve per-campaign (aeo_plan_id),
# not per-business. Built from the DB (the client-aeo-plans API route is RBAC-gated).
# Maps aeo_plan_id (str) -> search_address; empty/absent file = business-only fallback.
CAMPAIGN_ADDR = ({str(k): v for k, v in json.load(open("/tmp/campaign_addr.json")).items()}
                 if os.path.exists("/tmp/campaign_addr.json") else {})
# Local geo override — keyword id (str) -> "City, ST". Last-resort geo for campaigns
# whose target location exists ONLY in the keyword text (NULL search_address AND no
# business address, e.g. Voice depot metros, Yellow Brick). Neighborhood-only keywords
# are pre-mapped to their parent metro here so we don't geocode a bare locality (the
# _geocode wrong-city guard would reject that). Tracked in-repo; drop an entry once
# AEOAdmin backfills client_aeo_plans.search_address for it.
_KW_GEO_OVERRIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "kw_geo_override.json")
KW_GEO_OVERRIDE = ({str(k): v for k, v in json.load(open(_KW_GEO_OVERRIDE_PATH)).items()
                    if not str(k).startswith("_")}
                   if os.path.exists(_KW_GEO_OVERRIDE_PATH) else {})

excluded_biz_ids = {
    bid for bid, b in biz_by_id.items()
    if (b.get("name") or b.get("businessName") or "") in EXCLUDED_BIZ_NAMES
}
print(f"excluded biz ids: {sorted(excluded_biz_ids)}")

def is_active(o: dict) -> bool:
    return o.get("isActive") or o.get("status") == "active"

# Strict filter: kw active AND biz active AND client active
clients = json.load(open("/tmp/clients_admin.json"))
active_client_ids = {c["id"] for c in clients if is_active(c)}
active_biz_ids = {b["id"] for b in biz_by_id.values() if is_active(b) and b.get("clientId") in active_client_ids}
print(f"active clients: {len(active_client_ids)}/{len(clients)}")
print(f"active biz: {len(active_biz_ids)}/{len(biz_by_id)} (under active clients)")

active_kws = [k for k in kws
              if is_active(k)
              and k.get("businessId") in active_biz_ids
              and k.get("businessId") not in excluded_biz_ids
              and k["id"] not in (55, 58)]  # Leo Lapuerta phantom
print(f"active keywords (strict + post-exclude): {len(active_kws)}")

# Compute latest SUCCESSFUL ranking date per (kw_id, platform).
# success-only: an error rr-row must NOT mark a pair as "recently ranked"
# (a failed ranking still needs to be re-run). This is the +1-more-correct
# method noted in the handover vs counting all statuses.
latest = {}
for r in rr:
    if (r.get("status") or "").lower() != "success":
        continue
    kid = r.get("keywordId")
    plat = (r.get("platform") or "").lower()
    if not kid or plat not in PLATFORMS:
        continue
    d = r.get("date") or (r.get("createdAt") or "")[:10]
    if not d:
        continue
    cur = latest.get((kid, plat))
    if not cur or d > cur:
        latest[(kid, plat)] = d

# Restrict to the 14 STALE CLIENTS (admin bi-weekly bucket): a client whose
# MOST-RECENT successful audit across all its (kw,platform) is <= CUTOFF.
_client_latest = {}
for _k in active_kws:
    _b = biz_by_id.get(_k.get("businessId"))
    if not _b:
        continue
    _cid = _b.get("clientId")
    for _p in PLATFORMS:
        _d = latest.get((_k["id"], _p))
        if _d and _d > _client_latest.get(_cid, ""):
            _client_latest[_cid] = _d
STALE_CLIENT_IDS = {cid for cid, d in _client_latest.items() if d <= CUTOFF}
if os.environ.get("SMOKE_CLIENT"):
    STALE_CLIENT_IDS = {int(os.environ["SMOKE_CLIENT"])}
    print(f"[smoke] restricting to client {os.environ['SMOKE_CLIENT']}")
if os.environ.get("CLIENT_IDS"):
    # Explicit client set (e.g. new clients needing INITIAL_RANKING) — bypass the
    # staleness gate so never-ranked clients still fire.
    STALE_CLIENT_IDS = {int(x) for x in os.environ["CLIENT_IDS"].split(",") if x.strip()}
    print(f"[client-ids] restricting to {sorted(STALE_CLIENT_IDS)}")
print(f"stale clients (most-recent audit <= {CUTOFF}): {len(STALE_CLIENT_IDS)} -> {sorted(STALE_CLIENT_IDS)}")
if os.environ.get("KEYWORD_IDS_FILE"):
    import json as _json
    _kid = set(_json.load(open(os.environ["KEYWORD_IDS_FILE"])))
    active_kws = [k for k in active_kws if k["id"] in _kid]
    STALE_CLIENT_IDS = {biz_by_id[k["businessId"]].get("clientId") for k in active_kws if k.get("businessId") in biz_by_id}
    print(f"[kw-ids] targeting {len(active_kws)} specific keywords across {len(STALE_CLIENT_IDS)} clients (INITIAL_RANKING)")


# Build target list: INITIAL_RANKING for never_ranked, RANKING for ≤ cutoff
job_specs = []  # (kw, biz, platform_lower, job_type)
n_initial = n_ranking = n_fresh = 0
for k in active_kws:
    b = biz_by_id.get(k.get("businessId"))
    if not b:
        continue
    if b.get("clientId") not in STALE_CLIENT_IDS:
        continue
    for p in PLATFORMS:
        last = latest.get((k["id"], p))
        if last is None:
            job_specs.append((k, b, p, "INITIAL_RANKING"))
            n_initial += 1
        elif last <= CUTOFF:
            job_specs.append((k, b, p, "RANKING"))
            n_ranking += 1
        else:
            n_fresh += 1

print(f"\nplan summary:")
print(f"  INITIAL_RANKING (never_ranked):   {n_initial}")
print(f"  RANKING (last on/before {CUTOFF}): {n_ranking}")
print(f"  fresh (skip):                     {n_fresh}")
print(f"  total to run:                     {len(job_specs)}")
print(f"\nworkers (parallel phones): {WORKERS}")
print(f"csv path:                  {CSV_PATH}")
print(f"target date:               {TARGET_DATE_ISO}")


import re as _re_addr
import urllib.parse as _url_parse

# \s* (not \s+) before the zip: some addresses glue the state to the zip with no
# space, e.g. "New York, NY10118" / "Memphis, TN38103" (Citedlogic) — those must
# still parse to (city, ST, zip), else city/state come back empty and the phone
# rejects the audit ("city, state required").
_ADDR_RE = _re_addr.compile(r",\s*([^,]+?),\s*([A-Za-z]{2})\s*(\d{5})(?:-\d{4})?")


def _parse_address(addr: str) -> tuple[str, str, str]:
    """Extract (city, state, zip) from 'street, city, ST 12345' tail.
    86% of biz in catalog have null city/state — must fall back to address parse."""
    if not addr:
        return ("", "", "")
    m = _ADDR_RE.search(addr)
    if not m:
        return ("", "", "")
    st = m.group(2).strip().upper()
    return (m.group(1).strip(), st, m.group(3).strip()) if st in _VALID_ST else ("", "", "")


# (?![A-Za-z]) not \b: \b fails to end the state code when a zip is glued on
# ("NY10118" — no word boundary between Y and 1). Negative-lookahead for a letter
# lets "NY" match whether followed by a digit, space, or end.
_CITY_ST_RE = _re_addr.compile(r"([A-Za-z][A-Za-z .'\-]+),\s*([A-Za-z]{2})(?![A-Za-z])")

# Full US state/territory name -> 2-letter code. Free-trial campaign addresses often
# use the loose 'City, FullStateName' form (e.g. 'Brooklyn, New York') with no zip and
# no 2-letter code, which _CITY_ST_RE can't match — map the name so geo still resolves.
_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "washington dc": "DC", "washington d.c.": "DC",
}
# Valid 2-letter codes — case-insensitive parsing can match junk 2-letter tokens
# (e.g. "of"), so accept a parsed state only when it is a real US code.
_VALID_ST = frozenset(_STATE_NAME_TO_CODE.values())
# 'City, Full State Name' — anchored on the KNOWN state names so the second group
# only matches a real state. A generic \w+ second group greedily matched the wrong
# comma pair ("495 Fred Taylor Road, Siletz" instead of "Siletz, Oregon") and never
# reached the real state; anchoring on the state alternation fixes that.
_STATE_NAMES_ALT = "|".join(
    _re_addr.escape(_n) for _n in sorted(_STATE_NAME_TO_CODE, key=len, reverse=True))
_CITY_STATENAME_RE = _re_addr.compile(
    r"([A-Za-z][A-Za-z .'\-]+?),\s*(" + _STATE_NAMES_ALT + r")(?![A-Za-z])",
    _re_addr.IGNORECASE)


def _parse_loc(addr: str) -> tuple[str, str, str]:
    """Resolve (city, state, zip) from a campaign/business address string.
    Handles the full 'street, city, ST 12345' form, the looser 'City, ST' forms,
    AND 'City, FullStateName' (e.g. 'Brooklyn, New York') by mapping the full state
    name to its code. City+state alone is enough — the audit maps state -> zip."""
    if not addr:
        return ("", "", "")
    city, state, zc = _parse_address(addr)
    if state:
        return (city, state, zc)
    cleaned = _re_addr.sub(r"\(.*?\)", "", addr).strip()
    matches = _CITY_ST_RE.findall(cleaned)
    for c, s in reversed(matches):
        s = s.strip().upper()
        if s in _VALID_ST:
            return (c.strip(), s, "")
    # Fall back to 'City, FullStateName' → map the name to a 2-letter code.
    for c, s in _CITY_STATENAME_RE.findall(cleaned):
        code = _STATE_NAME_TO_CODE.get(s.strip().lower())
        if code:
            return (c.strip(), code, "")
    # 'City ST 12345' with no comma before the state ('Los Angeles CA 90028',
    # 'Richmond Tx 77406') — complete data the comma-based regexes miss. State+zip
    # are correct even if the city span picks up the street; the zip drives geo.
    m2 = _re_addr.search(r"([A-Za-z][A-Za-z .'\-]+?)\s+([A-Za-z]{2})\s+(\d{5})(?:-\d{4})?\b", cleaned)
    if m2 and m2.group(2).strip().upper() in _VALID_ST:
        return (m2.group(1).strip(), m2.group(2).strip().upper(), m2.group(3))
    return ("", "", "")


def _synth_gmb_url(biz_name: str, addr: str) -> str:
    """Per aeo-appium/CLAUDE.md: if biz has no GMB record, synthesize a Google Maps
    search URL — audit prompt needs *some* URL or geo-validation fails."""
    q = f"{biz_name} {addr}".strip()
    return f"https://www.google.com/maps/search/{_url_parse.quote_plus(q)}"


_GEO_CACHE: dict[str, tuple[str, str, str]] = {}


def _geocode(addr: str) -> tuple[str, str, str]:
    """Resolve a free-form street address to (city, state_code, zip) via Nominatim
    (OpenStreetMap) — fallback for search_addresses that omit state/zip (street +
    neighborhood, e.g. Voice depot's "100 SE 2nd St,Brickell" -> Miami, FL). Cached;
    obeys Nominatim's 1 req/s policy; fail-safe -> ('','','') so a geocode miss just
    leaves the row as the existing 'required' error, never worse."""
    key = " ".join((addr or "").split()).lower()
    if not key:
        return ("", "", "")
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    import urllib.request as _r, time as _t
    out = ("", "", "")
    try:
        # search_addresses often glue tokens ("St,Brickell", "PeakDr", "CamelbackRd")
        # — add a space after commas and split camelCase so Nominatim can match.
        norm = _re_addr.sub(r",(\S)", r", \1", addr)
        norm = _re_addr.sub(r"([a-z])([A-Z])", r"\1 \2", norm)
        q = _url_parse.quote_plus(norm + ", USA")
        url = (f"https://nominatim.openstreetmap.org/search?q={q}"
               "&format=json&addressdetails=1&limit=1&countrycodes=us")
        req = _r.Request(url, headers={"User-Agent": "device-agent-geo/1.0 (ranking-audit)"})
        data = json.load(_r.urlopen(req, timeout=15))
        _t.sleep(1.1)
        if data:
            a = data[0].get("address", {})
            city = (a.get("city") or a.get("town") or a.get("village")
                    or a.get("suburb") or a.get("neighbourhood") or a.get("county") or "")
            st = _STATE_NAME_TO_CODE.get((a.get("state") or "").strip().lower(), "")
            # Safety: the address's own locality token (last comma segment, e.g.
            # "Beverly Hills"/"South Congress") MUST appear in the geocoded result,
            # else Nominatim matched the wrong metro ("823 Congress Ave, South
            # Congress" -> New Haven CT). Reject -> the row stays a 'required' error
            # (a visible gap) instead of a silent wrong-city audit.
            token = " ".join(_re_addr.sub(r"[^a-z0-9 ]", " ", norm.rsplit(",", 1)[-1].lower()).split())
            comps = " ".join(str(a.get(k, "")) for k in
                             ("city", "town", "village", "suburb", "neighbourhood", "county", "state")).lower()
            if st and city and token and token in comps:
                out = (city, st, a.get("postcode", "") or "")
    except Exception:
        out = ("", "", "")
    _GEO_CACHE[key] = out
    return out


def make_job_record(kw: dict, biz: dict, platform: str, job_type: str, job_id: int) -> dict:
    """Match the JobRecord shape build_audit_dispatch_job expects."""
    # Campaign search_address is authoritative (per-campaign / multi-location);
    # fall back to the business address only when the campaign has none.
    camp_addr = CAMPAIGN_ADDR.get(str(kw.get("aeoPlanId") or "")) or ""
    # Keyword-level geo override wins over the business address (which for national
    # multi-metro campaigns is just an unrelated HQ) but never over a real per-campaign
    # search_address.
    kw_override = KW_GEO_OVERRIDE.get(str(kw.get("id") or "")) or ""
    address_line1 = camp_addr or kw_override or biz.get("publishedAddress") or biz.get("address") or ""
    # Multi-location businesses (e.g. Citedlogic) carry the per-location address ONLY
    # in the campaignName tail ("Biz — <street>, <city>, <ST><zip>") with null
    # business city/state. Parse that tail when no structured address exists, else
    # city/state are empty and the phone rejects the audit.
    if not address_line1:
        _cn = kw.get("campaignName") or ""
        if "—" in _cn:
            address_line1 = _cn.split("—", 1)[1].strip()
    biz_name_eff = biz.get("name") or biz.get("businessName") or ""
    city_p, state_p, zip_p = _parse_loc(address_line1)
    # Street geocode fallback: search_addresses that omit state/zip (street +
    # neighborhood) don't parse — geocode the full street to city+state. Leave the
    # zip empty so the dispatcher's _city_to_zip resolves + randomizes it in-city.
    if not state_p and address_line1:
        _gc, _gs, _gz = _geocode(address_line1)
        if _gs:
            city_p, state_p, zip_p = (_gc or city_p), _gs, ""
    # Curated keyword-override fallback: the search_address was a bare street+neighborhood
    # ("2000 McKinneyAve, Uptown") that neither parsed nor geocoded (the wrong-city guard
    # rejects a lone locality). Use this keyword's pre-mapped parent metro rather than error.
    if not state_p and kw_override:
        _oc, _os, _oz = _parse_loc(kw_override)
        if _os:
            city_p, state_p, zip_p = _oc, _os, ""
    biz_url = biz.get("gmbUrl") or biz.get("websiteUrl") or _synth_gmb_url(biz_name_eff, address_line1)
    return {
        "id": job_id,
        "status": "PENDING",
        "type": job_type,
        "targetDate": TARGET_DATE_ISO,
        "retryAttempts": 1,
        "platform": platform,
        "campaign": {
            "id": biz["id"] * 10000 + kw["id"],
            "openingTime": "08:00:00",
            "closingTime": "23:59:59",
            "business": {
                "id": biz["id"],
                "businessName": biz_name_eff,
                "name":         biz_name_eff,
                # Trading name(s) the platforms list this business under when they
                # differ from `name` (businesses.also_known_as) — Wichita Florist is
                # listed as "Flower Factory Flowers". The dispatch's fabricated-rank
                # gate matches on these too, else a genuine win for a DBA business
                # looks absent from its own list and gets re-captured forever.
                "alsoKnownAs":  biz.get("alsoKnownAs") or "",
                "clientId":     biz.get("clientId"),
                "client":       {"clientId": biz.get("clientId"), "clientName": ""},
                "gmb":          {"id": biz["id"], "name": biz_url, "type": "GMB"},
            },
            "address": {
                "addressLine1": address_line1,
                "city":         city_p or biz.get("city") or "",
                "state":        state_p or biz.get("state") or "",
                "stateCode":    state_p or biz.get("state") or "",
                "zipCode":      zip_p or biz.get("zipCode") or "",
            },
        },
        "detail": {
            "keyword":  {"id": kw["id"], "name": kw.get("keywordText") or kw.get("name") or ""},
            "backlink": {"status": False, "url": ""},
        },
        "conversation": {"platform": platform, "status": False, "prompts": []},
        "_source": SOURCE_TAG,
    }


# Optional skip filter (retry mode): drop pairs already terminal in a CSV.
# EXCLUDE_SUCCESS skips success only; set RETRY_KEEP_NORANK=1 to ALSO treat
# no_rank as terminal (don't retry it) — correct for initial ranking where
# no_rank is a valid result for brand-new businesses, so only errors re-run.
if os.environ.get("EXCLUDE_SUCCESS"):
    import csv as _csv, glob as _glob
    _terminal = {"success"}
    if os.environ.get("RETRY_KEEP_NORANK") == "1":
        _terminal.add("no_rank")
    _done = set()
    # EXCLUDE_SUCCESS may be a glob — append_row date-splits the CSV into
    # <base>_<rowdate>.csv, so read every matching file.
    _files = _glob.glob(os.environ["EXCLUDE_SUCCESS"]) or [os.environ["EXCLUDE_SUCCESS"]]
    for _fp in _files:
        try:
            for _r in _csv.DictReader(open(_fp)):
                if (_r.get("status") or "").lower() in _terminal:
                    _done.add(((_r.get("campaign_id") or "").strip(), (_r.get("platform") or "").lower().strip()))
        except FileNotFoundError:
            pass
    _b = len(job_specs)
    job_specs = [(k, b, p, t) for (k, b, p, t) in job_specs
                 if (str(b["id"] * 10000 + k["id"]), p) not in _done]
    print(f"[retry] EXCLUDE_SUCCESS (terminal={sorted(_terminal)}): {_b} -> {len(job_specs)} (skipped {_b - len(job_specs)})")

# Sample preview
if job_specs:
    s_kw, s_biz, s_plat, s_type = job_specs[0]
    sample_jr = make_job_record(s_kw, s_biz, s_plat, s_type, int(time.time()))
    sample_audit = build_audit_dispatch_job(sample_jr)
    print("\n=== SAMPLE audit_job (first spec, post build_audit_dispatch_job) ===")
    print(json.dumps(sample_audit, indent=2)[:800])
    print("...")

if DRY_RUN:
    print(f"\nDRY_RUN=1 — would run {len(job_specs)} ranking jobs across {WORKERS} workers. Exiting.")
    sys.exit(0)

if not job_specs:
    print("\nnothing to run — exiting.")
    sys.exit(0)

print(f"\n=== STARTING {len(job_specs)} RANKING JOBS ({WORKERS} parallel workers) ===")
t0 = time.time()
done = 0
counts = {"success": 0, "error": 0, "no_rank": 0, "other": 0}
errors = []


def _one(idx_spec):
    idx, (kw, biz, plat, jtype) = idx_spec
    job_id = int(time.time() * 1000) + idx
    jr = make_job_record(kw, biz, plat, jtype, job_id)
    audit_job = build_audit_dispatch_job(jr)
    try:
        row = dispatch_audit_job(audit_job, platform=plat, csv_path=CSV_PATH)
        return ("ok", idx, kw, biz, plat, jtype, row)
    except Exception as e:
        return ("err", idx, kw, biz, plat, jtype, f"{type(e).__name__}: {e}")


def _tally(payload, kind, kw, biz, plat):
    """Fold one job result into counts/errors. Return True if the phone got a
    LIVE tunnel (the failure, if any, was not proxy_unreachable)."""
    if kind == "ok":
        status = (payload.get("status") or "").lower()
        counts[status if status in counts else "other"] = counts.get(status if status in counts else "other", 0) + 1
        err = (payload.get("error") or "").lower()
    else:
        counts["error"] += 1
        errors.append((kw["id"], biz.get("name"), plat, payload))
        err = str(payload).lower()
    return "proxy_unreachable" not in err


# --- Tunnel warmup + health gate -------------------------------------------
# Every proxied job routes 100% of a phone's traffic through the Decodo VPN, so a
# dead tunnel makes the phone look offline. Run a canary wave (one real job per
# online phone) FIRST and check how many got a live tunnel; abort before
# committing the whole batch if the fleet path is unhealthy, instead of grinding
# hundreds of jobs against dead tunnels. Canary jobs are real work — their rows
# count, nothing is wasted. Disable with WARMUP_GATE=0.
_total = len(job_specs)
if WARMUP_GATE and len(job_specs) > WORKERS:
    canary, job_specs = job_specs[:WORKERS], job_specs[WORKERS:]
    print(f"\n[warmup] canary wave: {len(canary)} jobs (~1 per phone) to verify tunnels before the full batch...", flush=True)
    live = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_one, (i, s)): i for i, s in enumerate(canary)}
        for fut in as_completed(futs):
            kind, idx, kw, biz, plat, jtype, payload = fut.result()
            done += 1
            if _tally(payload, kind, kw, biz, plat):
                live += 1
    frac = live / len(canary) if canary else 0.0
    print(f"[warmup] tunnels live: {live}/{len(canary)} ({frac*100:.0f}%)", flush=True)
    if frac < WARMUP_MIN_FRAC:
        print(f"[warmup] ABORT: only {live}/{len(canary)} phones got a live tunnel "
              f"(< {WARMUP_MIN_FRAC*100:.0f}% threshold). Fleet/proxy path unhealthy — NOT "
              f"dispatching the remaining {len(job_specs)} jobs. Check gost/SocksDroid/Decodo "
              f"and re-run.", flush=True)
        sys.exit(2)
    print(f"[warmup] fleet healthy — dispatching remaining {len(job_specs)} jobs.\n", flush=True)


with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = {ex.submit(_one, (i, s)): i for i, s in enumerate(job_specs)}
    for fut in as_completed(futs):
        kind, idx, kw, biz, plat, jtype, payload = fut.result()
        done += 1
        _tally(payload, kind, kw, biz, plat)
        if done % 10 == 0 or done == _total:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed else 0
            eta_s = (_total - done) / rate if rate else 0
            print(f"  {done:>4d}/{_total} done  | success={counts['success']} error={counts['error']} no_rank={counts.get('no_rank',0)} | elapsed={elapsed:.0f}s rate={rate:.2f}/s ETA={eta_s/60:.1f}m", flush=True)

print(f"\n=== DONE ===")
print(f"  total:   {done}")
print(f"  success: {counts['success']}")
print(f"  error:   {counts['error']}")
print(f"  no_rank: {counts.get('no_rank', 0)}")
print(f"  other:   {counts.get('other', 0)}")
print(f"  elapsed: {(time.time()-t0)/60:.1f} min")
print(f"  csv:     {CSV_PATH}")
if errors:
    print(f"\nfirst 5 errors:")
    for e in errors[:5]:
        print(f"  kw_id={e[0]} biz={e[1]!r} plat={e[2]} → {e[3]}")
