#!/usr/bin/env python3
"""
Local Keyword Research — our own LocalFalcon-style local keyword tool.

Pipeline (see LOCAL_KEYWORD_RESEARCH.md):
  seed + location
    -> IDEAS:   Google Autocomplete (free, no key) + alphabet-soup + local modifiers
    -> ENRICH:  DeepSeek API -> intent, commercial-intent, one-line reasoning,
                                conversational AI-search variants
    -> DIFF:    (optional) measured from a real on-device SERP scrape (seo_dispatch.py)
    -> SCORE:   LVS (Local Value Score, 1-100)  [provisional until real volume in Phase 2]
    -> OUTPUT:  two ranked lists (traditional + ai_search) as JSON

stdlib only (matches the repo's runner convention). DeepSeek is OpenAI-compatible, called
over urllib. Everything except the DeepSeek call is free; without a key the tool still
produces ideas + measured difficulty, just with neutral enrichment.

Usage:
  export DEEPSEEK_API_KEY=sk-...            # or put it in .env.dev and `source` it
  python3 keyword_research.py --seed "childcare" --location "San Francisco, California"

  # add measured difficulty for the top N keywords (needs a live phone + proxy tunnel):
  python3 keyword_research.py --seed "childcare" --location "San Francisco, California" \
      --difficulty --serial "<adb-serial>" --difficulty-top 5

  # score difficulty against an already-scraped SERP json instead of a live run:
  python3 keyword_research.py --seed childcare --location "San Francisco" \
      --difficulty-from seo_results/bilingual-childcare-near-me_20260602_105324.json
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ----- config -------------------------------------------------------------------------

AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# Local modifiers we prepend/append to the seed to mine intent-rich variants for free.
PREFIX_MODIFIERS = ["best", "affordable", "cheap", "top", "licensed", "near me", "24 hour"]
SUFFIX_MODIFIERS = ["near me", "prices", "cost", "reviews", "open now", "for toddlers"]
ALPHABET = "abcdefghijklmnopqrstuvwxyz"

# Big aggregator/directory domains that signal a harder local SERP to crack.
AGGREGATORS = {
    "yelp.com", "tripadvisor.com", "yellowpages.com", "facebook.com", "angi.com",
    "thumbtack.com", "nextdoor.com", "bbb.org", "mapquest.com", "foursquare.com",
    "winnie.com", "care.com", "niche.com", "greatschools.org", "wonderschool.com",
    "expedia.com", "booking.com", "healthgrades.com", "zocdoc.com", "avvo.com",
}


# ----- 1. idea generation (free) ------------------------------------------------------

def _autocomplete(query, gl, hl, timeout=8):
    """Hit Google's free suggest endpoint. client=firefox returns [query, [suggestions]]."""
    params = urllib.parse.urlencode({"client": "firefox", "hl": hl, "gl": gl, "q": query})
    req = urllib.request.Request(
        f"{AUTOCOMPLETE_URL}?{params}",
        headers={"User-Agent": "Mozilla/5.0 (keyword-research)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return data[1] if isinstance(data, list) and len(data) > 1 else []
    except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError):
        return []


def generate_ideas(seed, city, gl, hl, max_ideas):
    """Mine the free autocomplete endpoint. Track a popularity proxy = how many distinct
    seed-queries surfaced each suggestion (broadly-suggested terms score higher)."""
    seed = seed.strip().lower()
    city = (city or "").strip()
    city_first = city.split(",")[0].strip()

    # Build the seed-query set: base, alphabet soup, modifiers, and city-scoped variants.
    queries = [seed, f"{seed} "]
    queries += [f"{seed} {c}" for c in ALPHABET]
    queries += [f"{m} {seed}" for m in PREFIX_MODIFIERS]
    queries += [f"{seed} {m}" for m in SUFFIX_MODIFIERS]
    if city_first:
        queries += [f"{seed} in {city_first}", f"{seed} {city_first}", f"best {seed} {city_first}"]
    queries = list(dict.fromkeys(queries))  # dedup, keep order

    freq = {}          # suggestion -> count of seed-queries that surfaced it
    first_seen = {}    # suggestion -> rank order first seen (lower = earlier/likely more relevant)
    order = 0
    for q in queries:
        for s in _autocomplete(q, gl, hl):
            order += 1
            key = s.strip().lower()
            if not key or seed not in key and not _shares_token(seed, key):
                continue
            freq[key] = freq.get(key, 0) + 1
            first_seen.setdefault(key, order)
        time.sleep(0.05)  # be gentle

    if not freq:
        return []

    max_freq = max(freq.values())
    ideas = []
    for kw, f in freq.items():
        # popularity proxy in [0,1]: blends breadth-of-suggestion + early appearance
        breadth = f / max_freq
        early = 1.0 - min(first_seen[kw], 200) / 200.0
        pop = round(0.7 * breadth + 0.3 * early, 4)
        ideas.append({"keyword": kw, "popularity": pop, "_freq": f})

    ideas.sort(key=lambda x: x["popularity"], reverse=True)
    return ideas[:max_ideas]


def _shares_token(seed, kw):
    seed_tokens = set(re.findall(r"\w+", seed))
    kw_tokens = set(re.findall(r"\w+", kw))
    return bool(seed_tokens & kw_tokens)


# ----- 2. DeepSeek enrichment ---------------------------------------------------------

def _deepseek_chat(messages, api_key, temperature=0.3, timeout=60):
    body = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        DEEPSEEK_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode())
    return resp["choices"][0]["message"]["content"]


def enrich_keywords(ideas, seed, location, api_key):
    """One DeepSeek call: classify intent + commercial-intent + a one-line reason per keyword."""
    if not api_key:
        for it in ideas:
            it.update(intent="unknown", commercial_intent=0.5, reasoning="(no DEEPSEEK_API_KEY — enrichment skipped)")
        return ideas

    kw_list = [it["keyword"] for it in ideas]
    sys_prompt = (
        "You are a local-SEO keyword analyst. For each keyword, return its search intent and a "
        "commercial-intent score. Respond with a JSON object: "
        '{"results":[{"keyword":..., "intent":"informational|navigational|commercial|transactional", '
        '"commercial_intent":0.0-1.0, "reasoning":"<=12 words why it matters for this local business"}]}'
    )
    user_prompt = (
        f"Business seed: {seed}\nLocation: {location}\n"
        f"Keywords:\n" + "\n".join(f"- {k}" for k in kw_list)
    )
    try:
        content = _deepseek_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            api_key,
        )
        parsed = json.loads(content).get("results", [])
        by_kw = {r.get("keyword", "").strip().lower(): r for r in parsed}
        for it in ideas:
            r = by_kw.get(it["keyword"], {})
            it["intent"] = r.get("intent", "unknown")
            it["commercial_intent"] = _clip01(r.get("commercial_intent", 0.5))
            it["reasoning"] = r.get("reasoning", "")
    except Exception as e:  # degrade, don't crash the run
        print(f"   ⚠ DeepSeek enrichment failed ({e}); using neutral values", file=sys.stderr)
        for it in ideas:
            it.setdefault("intent", "unknown")
            it.setdefault("commercial_intent", 0.5)
            it.setdefault("reasoning", "")
    return ideas


def generate_ai_search(seed, location, api_key, n=8):
    """Conversational queries someone would ask an AI assistant — the 'AI search' list."""
    if not api_key:
        return []
    sys_prompt = (
        "Generate natural, conversational questions a person would ask an AI assistant "
        "(ChatGPT, Gemini) when looking for this local service. Respond as JSON: "
        '{"results":[{"keyword":"<question>","intent":"commercial|informational",'
        '"commercial_intent":0.0-1.0,"reasoning":"<=12 words"}]}'
    )
    user_prompt = f"Service: {seed}\nLocation: {location}\nProduce {n} distinct questions."
    try:
        content = _deepseek_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            api_key, temperature=0.7,
        )
        out = json.loads(content).get("results", [])
        for r in out:
            r["keyword"] = r.get("keyword", "").strip()
            r["commercial_intent"] = _clip01(r.get("commercial_intent", 0.6))
            r["popularity"] = None  # autocomplete doesn't cover conversational queries
        return [r for r in out if r["keyword"]]
    except Exception as e:
        print(f"   ⚠ DeepSeek AI-search generation failed ({e})", file=sys.stderr)
        return []


# ----- 3. measured difficulty (our edge) ----------------------------------------------

def difficulty_from_serp(serp_record):
    """Compute a 0-100 difficulty from a real SERP (the shape seo_dispatch.py writes).
    Signals: aggregator density in organic top-10, and map-pack incumbent review strength."""
    organic = serp_record.get("organic_results", []) or []
    places = (serp_record.get("local_results") or {}).get("places", []) or []

    top = organic[:10]
    agg_hits = 0
    for o in top:
        link = (o.get("link") or o.get("displayed_link") or "").lower()
        if any(a in link for a in AGGREGATORS):
            agg_hits += 1
    agg_ratio = agg_hits / len(top) if top else 0.0

    # map-pack strength: high review counts on the top-3 = entrenched incumbents = harder
    reviews = [p.get("reviews") or 0 for p in places[:3]]
    avg_reviews = sum(reviews) / len(reviews) if reviews else 0
    # normalize: 0 reviews -> 0, 200+ reviews -> ~1
    review_strength = min(avg_reviews / 200.0, 1.0)

    # blend: aggregators dominate organic difficulty; incumbent reviews dominate local difficulty
    score = 100.0 * (0.55 * agg_ratio + 0.45 * review_strength)
    return {
        "difficulty": round(score, 1),
        "difficulty_basis": (
            f"measured: {agg_hits}/{len(top)} aggregators in organic top-10, "
            f"map-pack avg {round(avg_reviews)} reviews"
        ),
    }


def measure_difficulty_live(keyword, location, serial, local_port, out_dir):
    """Run one keyword through the on-device scraper, then score its SERP.
    Requires a live phone + proxy tunnel (see SESSION_HANDOVER). Returns dict or None."""
    try:
        import seo_dispatch  # local module
    except ImportError:
        print("   ⚠ seo_dispatch.py not importable; skipping live difficulty", file=sys.stderr)
        return None
    try:
        seo_dispatch.HTTP_TIMEOUT_S = max(getattr(seo_dispatch, "HTTP_TIMEOUT_S", 300), 300)
        summary = seo_dispatch.dispatch_one(
            serial=serial, keyword=keyword, target=None, out_dir=Path(out_dir),
            local_port=local_port, retries=0, location=location,
        )
        json_path = summary.get("json_path") or summary.get("json")
        if json_path and Path(json_path).exists():
            return difficulty_from_serp(json.loads(Path(json_path).read_text()))
    except Exception as e:
        print(f"   ⚠ live difficulty for '{keyword}' failed: {e}", file=sys.stderr)
    return None


# ----- 4. scoring ---------------------------------------------------------------------

def compute_lvs(item, weights):
    """Local Value Score (1-100). Provisional: uses autocomplete popularity as a volume
    proxy until real volume data lands in Phase 2."""
    pop = item.get("popularity")
    pop = 0.5 if pop is None else pop                 # neutral for conversational queries
    ci = item.get("commercial_intent", 0.5)
    diff = item.get("difficulty")
    diff_norm = 0.5 if diff is None else diff / 100.0  # neutral if difficulty not measured

    z = (weights["volume"] * pop
         + weights["intent"] * ci
         - weights["difficulty"] * diff_norm)
    # center so a neutral keyword (~0.5,0.5,0.5) lands mid-scale, then squash to 1-100
    lvs = 100.0 / (1.0 + math.exp(-4.0 * (z - 0.15)))
    return max(1, round(lvs))


def _clip01(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


# ----- main ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Local keyword research (autocomplete + DeepSeek + measured difficulty)")
    ap.add_argument("--seed", required=True, help="Seed keyword, e.g. 'childcare'")
    ap.add_argument("--location", default="", help="Location label, e.g. 'San Francisco, California'")
    ap.add_argument("--gl", default="us", help="Country code for autocomplete (default us)")
    ap.add_argument("--hl", default="en", help="Language code for autocomplete (default en)")
    ap.add_argument("--max-ideas", type=int, default=40, help="Max traditional keywords to keep")
    ap.add_argument("--ai-count", type=int, default=8, help="How many AI-search questions to generate")
    ap.add_argument("--out", default="keyword_results", help="Output directory")
    # difficulty
    ap.add_argument("--difficulty", action="store_true", help="Measure difficulty live via the scraper")
    ap.add_argument("--difficulty-top", type=int, default=5, help="How many top keywords to measure live")
    ap.add_argument("--difficulty-from", help="Score difficulty from an existing SERP json (no live run)")
    ap.add_argument("--serial", help="adb serial for live difficulty")
    ap.add_argument("--local-port", type=int, default=8765)
    # scoring weights
    ap.add_argument("--w-volume", type=float, default=0.40)
    ap.add_argument("--w-intent", type=float, default=0.35)
    ap.add_argument("--w-difficulty", type=float, default=0.30)
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    weights = {"volume": args.w_volume, "intent": args.w_intent, "difficulty": args.w_difficulty}

    print(f"[1/4] mining Google Autocomplete for '{args.seed}' ({args.gl}/{args.hl})…")
    ideas = generate_ideas(args.seed, args.location, args.gl, args.hl, args.max_ideas)
    print(f"      -> {len(ideas)} candidate keywords")
    if not ideas:
        print("No suggestions returned — check connectivity or try a broader seed.", file=sys.stderr)
        sys.exit(1)

    print(f"[2/4] enriching via DeepSeek ({'key set' if api_key else 'NO KEY — neutral enrichment'})…")
    ideas = enrich_keywords(ideas, args.seed, args.location, api_key)
    ai_search = generate_ai_search(args.seed, args.location, api_key, args.ai_count)
    print(f"      -> {len(ai_search)} AI-search questions")

    # difficulty
    diff_note = "not measured"
    if args.difficulty_from:
        rec = json.loads(Path(args.difficulty_from).read_text())
        d = difficulty_from_serp(rec)
        # apply to the closest-matching keyword if present, else to all as a baseline
        for it in ideas[: args.difficulty_top]:
            it.update(d)
        diff_note = f"from file {args.difficulty_from}"
    elif args.difficulty:
        if not args.serial:
            print("   ⚠ --difficulty needs --serial; skipping", file=sys.stderr)
        else:
            print(f"[3/4] measuring difficulty live for top {args.difficulty_top} (needs live phone+proxy)…")
            for it in ideas[: args.difficulty_top]:
                d = measure_difficulty_live(it["keyword"], args.location, args.serial, args.local_port, args.out)
                if d:
                    it.update(d)
                    print(f"      {it['keyword']!r}: difficulty {d['difficulty']}")
            diff_note = "measured live"
    else:
        print("[3/4] difficulty: skipped (pass --difficulty or --difficulty-from to enable)")

    print("[4/4] scoring (LVS) + writing output…")
    for it in ideas + ai_search:
        it["lvs"] = compute_lvs(it, weights)
        it.pop("_freq", None)
    ideas.sort(key=lambda x: x["lvs"], reverse=True)
    ai_search.sort(key=lambda x: x["lvs"], reverse=True)

    now = datetime.now(timezone.utc)
    record = {
        "seed": args.seed,
        "location": args.location,
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "engine": "keyword_research.py (autocomplete + DeepSeek + measured difficulty)",
        "scoring_weights": weights,
        "difficulty_basis": diff_note,
        "notes": "LVS is provisional — uses autocomplete popularity as a volume proxy until "
                 "real volume (Keyword Planner / DataForSEO) lands in Phase 2.",
        "traditional": ideas,
        "ai_search": ai_search,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", args.seed.lower()).strip("-")
    stem = f"{slug}_{now.strftime('%Y%m%d_%H%M%S')}"
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))

    # console summary
    print(f"\n  seed: {args.seed!r}  location: {args.location!r}")
    print(f"  traditional keywords: {len(ideas)}   ai-search: {len(ai_search)}")
    print("  top 10 traditional by LVS:")
    for it in ideas[:10]:
        diff = it.get("difficulty")
        diff_s = f" diff={diff}" if diff is not None else ""
        print(f"    {it['lvs']:>3}  {it['keyword']}  ({it.get('intent','?')}{diff_s})")
    print(f"\n  -> {out_path}")


if __name__ == "__main__":
    main()
