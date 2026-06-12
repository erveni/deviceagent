# Local Keyword Research — what Local Falcon does, and how we build our own

_Research + design note, 2026-06-03. Pairs with the on-device SERP rank pipeline
(`seo_dispatch.py` + `com.deviceagent`)._

---

## 1. What Local Falcon's "Local Keyword" tool actually is

A seed-keyword → localized-keyword-ideas generator, tuned for **local** SEO instead of
national. You give it:

- **A seed keyword** (or it auto-suggests one from the business category)
- **A location** (saved business location, or a manually typed city / state / address)

…click **Get Keywords**, and a few seconds later it returns **two ranked lists**:

| List | For | Style |
|---|---|---|
| **Traditional search** | Google, Bing | classic keyword phrases |
| **AI search** | ChatGPT, Google AI Overviews | conversational, "how people talk to AI" |

Each keyword row carries these fields:

- **Intent** — informational / navigational / commercial / transactional
- **Keyword difficulty** — how hard to rank
- **Search volume** — *localized*, not national
- **WYN Score** — proprietary 1–100 value metric (see below)
- **AI reasoning** — hover tooltip explaining *why* it suggested that keyword

Then you `+` keywords into a list and either **Run Quick Scan** or **Add to Campaign** — which
feeds their **geo-grid rank tracker** (3×3 … 21×21 grids) and the **SoLV** metric (Share of Local
Voice = % of grid points where the business sits in the map-pack top-3).

### The WYN Score (their headline metric)

WYN = "Weighted Yield Number". Their pitch: *"how valuable a keyword is, not just how popular."*
It blends:

- **+ Localized volume & difficulty** — scaled by the metro's **approximate population** and
  **number of competitors**, instead of national figures
- **+ Commercial intent** — how "action-oriented / purchase-ready" the phrasing is
- **+ Trend / seasonality** — favor rising terms, avoid declining ones
- **− Competitive difficulty** — strong negative driver

Output 1–100. Their own docs say it's *"a strategic guide, not absolute truth."*

---

## 2. The honest read on how it works under the hood

Stripping the marketing, this is **not** magic data — it's an LLM + a licensed keyword database
+ a population-scaling trick:

- **Keyword ideas** = an LLM expansion of the seed, almost certainly cross-checked against a
  licensed keyword corpus (DataForSEO-style) for the volume/difficulty columns.
- **"Localized" volume** — Google does **not** hand out true per-metro volume. They almost
  certainly take **national/regional** volume (licensed) and **scale it down by the metro's
  population fraction**, nudged by competitor density. That's the whole "approximate population"
  line in their docs.
- **WYN** = a weighted formula (volume↑, intent↑, difficulty↓, trend↑) partly driven by an LLM
  for the intent/reasoning pieces. Reproducible.
- The genuinely hard-to-fake, valuable part of Local Falcon is **not** the keyword tool — it's the
  **geo-grid rank measurement (SoLV)**, which is real measurement. The keyword tool is just the
  funnel that feeds it.

**Takeaway:** every piece of this is buildable. And the one part that's hard to fake — real
local measurement — is the part **we already have** (the on-device SERP scraper).

---

## 3. What we already own that maps onto this

| Our asset | What it gives the keyword tool |
|---|---|
| On-device real-Chrome **SERP scraper** (rank JSON + screenshots), residential per-metro | **Measured** keyword difficulty + real local-pack competition, not estimates |
| SERP parser already harvests organic + local pack with rich fields | Free source of "related searches" / "people also ask" keyword ideas |
| device-agent fleet also automates **ChatGPT / Gemini / Perplexity** (AEO) | We can *ground* the "AI search" list by actually asking the assistants if the client shows up |
| Residential geo targeting (`country-us-zip-<zip>`) | True location control for both ideas and difficulty |

**Our differentiator vs Local Falcon: we can _measure_ difficulty and rank on real phones, not
just license an estimate.**

---

## 4. Building blocks for our own tool

### A. Keyword idea generation (cheap / free)
- **Google Autocomplete / Suggest** — `https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q=<seed>`
  — no key, no OAuth, free. "Alphabet-soup" expand (append a–z, " near me", city names);
  localize via `gl`/`hl`. Gives *real* suggestions people type.
- **SERP-harvested ideas** — pull "Related searches" + "People also ask" straight out of our
  on-device SERP scrape (we already walk that a11y tree).
- **LLM expansion** _(model-agnostic — see §10; use DeepSeek or a free/local model, not
  necessarily Claude)_ — seed → semantic variants + conversational AI-search phrasings + a
  one-line *reasoning* string + an intent label, in one call. This is exactly Local Falcon's
  "AI reasoning" + "AI search list".

### B. Search volume (the one part that needs a data source)
- **Option 1 — Google Ads Keyword Planner API (free):** `GenerateKeywordIdeas` /
  `GenerateKeywordHistoricalMetrics`, geo-targetable via `geo_target_constants`, returns avg
  monthly searches + competition + CPC. **Free** with a Google Ads account. Catch: low-spend
  accounts get **bucketed ranges** (e.g. 1K–10K), and it needs API access approval.
- **Option 2 — DataForSEO Keyword Data API (paid, precise):** pay-as-you-go, location + language
  params, Google-Ads-sourced volume / CPC / competition / trend, no Google rate limits. Best
  granularity; small per-keyword cost.
- **Localize either one** by scaling national/regional volume by the metro population fraction
  (the Local Falcon trick) — population from a static census table.

### C. Keyword difficulty — **OUR EDGE, measured not estimated**
Run the keyword through our on-device scraper for the target metro, then score difficulty from
the *real* SERP:
- count of strong aggregators in the top 10 (Yelp, Tripadvisor, Yellow Pages…)
- map-pack saturation + the review counts / ratings of the incumbents holding those 3 slots
- domain repetition, ads present
→ combine into a 0–100 **measured** difficulty. No competitor offers this from a real device.

### D. Intent — the LLM (§10) classifies informational / navigational / commercial / transactional
+ a 0–1 commercial-intent score.

### E. Our value score (the WYN analogue) — propose **LVS = Local Value Score (1–100)**
```
LVS = 100 × sigmoid(
        w_v · norm(localized_volume)
      + w_i · commercial_intent
      + w_t · trend
      − w_d · measured_difficulty
   ) , then adjusted by metro population & competitor density
```
Transparent, tunable weights — the opposite of a black box. Start with
`w_v=0.35, w_i=0.25, w_d=0.30, w_t=0.10` and calibrate.

### F. Two lists
- **Traditional** — from autocomplete + planner volume.
- **AI search** — LLM-generated conversational variants, optionally **validated for real** by querying
  ChatGPT / Gemini / Perplexity through the existing device fleet and checking whether the client
  gets mentioned (a true AEO signal Local Falcon can only *guess* at).

### G. Close the loop
Selected keywords → feed straight into the geo-rank scraper to **track actual rankings over time**
(our SoLV analogue). Research → measurement in one system.

---

## 5. Data flow

```
seed + location
  → IDEAS:    autocomplete  +  SERP-harvest (related/PAA)  +  Claude expansion
  → DEDUP / cluster
  → ENRICH:   volume (Planner|DataForSEO, localized)
              intent + reasoning (Claude)
              difficulty (OUR on-device scraper)
              trend/seasonality
  → SCORE:    LVS 1–100
  → OUTPUT:   two ranked lists + reasoning + JSON  (same shape family as our SERP JSON)
  → SELECT →  rank-tracking campaign (existing seo_dispatch pipeline)
```

## 6. Proposed output JSON (keep it consistent with our SERP JSON)
```json
{
  "seed": "childcare",
  "location": "San Francisco, California",
  "generated_at": "2026-06-03 ...",
  "traditional": [
    {
      "keyword": "bilingual childcare near me",
      "intent": "commercial",
      "commercial_intent": 0.82,
      "search_volume": 1300,
      "search_volume_basis": "national 8100 × SF pop-fraction",
      "difficulty": 64,
      "difficulty_basis": "measured: 4 aggregators in top10, map-pack avg 41 reviews",
      "trend": "rising",
      "lvs": 73,
      "reasoning": "High local commercial intent; map pack beatable (low review counts)."
    }
  ],
  "ai_search": [
    {
      "keyword": "what's the best bilingual daycare in san francisco for toddlers",
      "intent": "commercial",
      "lvs": 68,
      "assistant_mentions": { "chatgpt": false, "gemini": true, "perplexity": false },
      "reasoning": "Conversational; Gemini already cites 2 local providers — winnable."
    }
  ]
}
```

## 7. Build phases
- **Phase 1 — cheap MVP, zero paid APIs, fully ours:** autocomplete + SERP-harvest + Claude
  ideas/intent/reasoning + **measured difficulty from our scraper** + a provisional LVS that uses
  autocomplete relative popularity in place of true volume. Ships fast.
- **Phase 2 — real volume:** add Keyword Planner (free) or DataForSEO (paid) → proper localized
  volume + WYN-grade LVS.
- **Phase 3 — moat features:** AEO-grounded AI-search list (live assistant queries) + the
  rank-tracking loop + trend/seasonality.

## 8. Cost / dependency summary
| Component | Source | Cost |
|---|---|---|
| Keyword ideas | Google Autocomplete | free, no key |
| Related/PAA ideas | our on-device SERP scrape | free |
| Intent / reasoning / AI variants | **local Ollama** (Qwen3 / DeepSeek) or a free API tier (§10) | **free** |
| Search volume | Keyword Planner | free (Ads acct + approval; bucketed) |
| Search volume (precise) | DataForSEO | paid, pay-as-you-go |
| **Difficulty** | **our scraper** | **free — our edge** |
| AI-search validation | device fleet (ChatGPT/Gemini/Perplexity) | free (our phones) |

> **Every row above can be free.** A 100%-free Phase-1 stack = Google Autocomplete + our SERP
> scraper + a local/free LLM + measured difficulty. No paid API required.

## 9. Open decisions (for the team)
1. **Volume source:** Keyword Planner (free, needs approval, coarse buckets) **or** DataForSEO
   (paid, precise)? Recommendation: start Phase 1 with **no** volume source, add DataForSEO in
   Phase 2 if budget allows, else Keyword Planner.
2. **Home repo:** build in `seo-device-agent` (the stated home for daily search)?
3. **AEO-grounded AI list** — now (Phase 1) or later (Phase 3)?
4. Want me to **authenticate the connected Local Falcon account** (MCP) so we can inspect their
   *exact* keyword-tool fields/scores and match parity before we build?

---

## 10. The LLM step is model-agnostic — pick a free one (not Claude)

The "AI" parts (idea expansion, intent label, one-line reasoning, conversational AI-search
variants) are just text generation. Any decent model does it. Options, cheapest-first:

| Option | Cost | Limits | Notes |
|---|---|---|---|
| **Local Ollama on the Mac** (Qwen3 8B, or a DeepSeek distill) | **$0, unlimited** | only your hardware | truly free, no quotas, runs offline. **Best fit** — we already have the Mac. 8GB RAM runs a 7–8B model. |
| **Mistral free "Experiment" plan** | $0, no card | ~1B tokens/month | huge free monthly budget; best free *API* for volume. |
| **Groq** (Llama 3.3 70B) | $0, no card | ~14,400 req/day | very fast; generous daily cap. |
| **Google Gemini Flash** free tier | $0 | 250 req/day | small cap, fine for low volume. |
| **DeepSeek API** | 5M free tokens on signup, then **$0.30 / 1M in** | pay-as-you-go after trial | dirt cheap even paid; great quality. Good when local isn't enough. |

**Recommendation:** run **local Ollama (Qwen3 8B or DeepSeek distill)** for Phase 1 — zero cost,
no rate limits, no keys, and keyword expansion is well within a small model's ability. Keep
**DeepSeek API** as the cheap paid fallback if we ever need bigger batches or higher quality.
Claude is *not* required anywhere in this pipeline.

## 11. Existing open-source repos to build on (don't start from scratch)

| Repo | What it gives us | License | Catch |
|---|---|---|---|
| **chukhraiartur/seo-keyword-research-tool** | Exactly our idea-gen layer: Autocomplete + People-Also-Ask + Related Searches → CSV/JSON/TXT, with `hl`/`gl`/`gd` locale args | MIT | uses **SerpApi** for the SERP parts — **but we replace that with our own on-device scraper** (we already parse PAA/related) + the free autocomplete endpoint. Keep its structure, drop the paid dep. |
| **rdowns26/seo_keyword_research_tools** | Keyword **volume + competition** + expand 1 seed → up to 500 keywords | open | uses **Google Ads / AdWords API** (free with an Ads account) — this is our Phase-2 volume layer, ready-made. |
| **hassancs91/Keyword-Research-tool-python** | Autocomplete-based research (reverse-engineers AnswerThePublic / KeywordTool.io) | open | pure-autocomplete approach; good reference for alphabet-soup expansion. |
| **ecoron/SerpScrap** | Python SERP scraper: url/title/snippet/rich-snippet, ad detection, screenshots | open | a desktop fallback if we ever want non-device SERP parsing; we mostly don't need it (our phones do this). |

**Plan of attack:** fork **chukhraiartur** for the idea-gen skeleton (MIT, clean), rip out SerpApi
and wire in (a) the free `suggestqueries.google.com` autocomplete endpoint and (b) our on-device
scraper for PAA/related + measured difficulty. Pull in **rdowns26**'s Google Ads volume code when
we get to Phase 2. The LLM scoring/reasoning layer (§4D–E, §10) is the only genuinely new code.

This means **almost none of it is built from zero** — we're gluing two MIT/open repos to the
scraper we already own, with a free local LLM on top.

---

## 12. Phase 1 — BUILT ✅ (`keyword_research.py`, 2026-06-03)

Phase-1 tool is implemented and working end-to-end. stdlib-only; DeepSeek via its
OpenAI-compatible endpoint over urllib.

**Pipeline:** Google Autocomplete (free) → DeepSeek enrichment (intent + commercial-intent +
reasoning + AI-search questions) → measured difficulty from a real SERP → LVS score → two-list JSON.

**Setup**
```bash
cd ~/projects/device-agent
# key lives in .env.dev (gitignored); already set
set -a; source .env.dev; set +a        # exports DEEPSEEK_API_KEY
```

**Run (free idea-gen + DeepSeek, difficulty scored from an existing SERP json)**
```bash
python3 keyword_research.py --seed "childcare" --location "San Francisco, California" \
  --max-ideas 30 --ai-count 8 \
  --difficulty-from seo_results/bilingual-childcare-near-me_20260602_105324.json
# -> keyword_results/<slug>_<ts>.json   (traditional[] + ai_search[])
```

**Run with LIVE measured difficulty** (needs a fresh phone + Decodo tunnel up — see
SESSION_HANDOVER for bringup; difficulty runs the top-N keywords through `seo_dispatch.py`):
```bash
python3 keyword_research.py --seed childcare --location "San Francisco, California" \
  --difficulty --serial "<adb-serial>" --difficulty-top 5
```

**Output fields** — per keyword: `keyword, popularity, intent, commercial_intent, reasoning,
difficulty, difficulty_basis, lvs`. AI-search rows omit `popularity` (autocomplete doesn't cover
conversational queries).

**Verified 2026-06-03:** seed `childcare` / San Francisco → 30 traditional + 8 AI-search;
DeepSeek correctly floats commercial terms (`childcare center` LVS 85, `childcare provider` 80)
above autocomplete noise (`childcare manhwa` etc.); difficulty `39.9` measured from a real SERP
(*"6/10 aggregators in organic top-10, map-pack avg 31 reviews"*).

**Status of each layer**
- ✅ Idea-gen (autocomplete + alphabet-soup + local modifiers) — free, live-tested
- ✅ DeepSeek enrichment + AI-search list — live-tested with the team key
- ✅ Difficulty scorer (`difficulty_from_serp`) — tested against a real SERP json
- ⚠️ **Live** difficulty path (`measure_difficulty_live`) — coded, but not yet run against a live
  phone (fleet/proxy were torn down). Needs one live verification next session.

**Phase-1 limitation:** LVS uses autocomplete *popularity* as a volume proxy (no true volume yet).
Phase 2 swaps in real volume (Keyword Planner free, or DataForSEO) for WYN-grade scoring.

### Sources
- Local Falcon — How to use the Local Keyword Tool (KB86)
- Local Falcon — "Say goodbye to generic keyword research" (WYN Score blog)
- Local Falcon — Suggested Keywords answer; Features page (geo-grid, SoLV)
- Google Ads API — GenerateKeywordIdeas / GenerateHistoricalMetrics docs
- DataForSEO — Keyword Data / Google Ads API
- Google Autocomplete/Suggest endpoint (suggestqueries.google.com) usage guides
- Repos: chukhraiartur/seo-keyword-research-tool, rdowns26/seo_keyword_research_tools,
  hassancs91/Keyword-Research-tool-python, ecoron/SerpScrap
- Free-LLM survey: mnfst/awesome-free-llm-apis; Ollama (Qwen3 / DeepSeek local)
