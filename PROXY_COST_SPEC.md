# Proxy Cost Specification — Fleet Operations

## 2026-09-08 completed phone comparison

`cost_trial_20260907_v3/report.json` finished 06:32 local; meter unchanged at
06:47 (41,785.365754 MB). Same ten Gemini keywords per leg, three workers:

| Routing | Billed MB | Successes | MB/scheduled job | MB/success |
|---|---:|---:|---:|---:|
| Existing ZIP-first ladder | 543.618749 | 6/10 | 54.36 | 90.60 |
| City-first ladder | 369.781804 | 8/10 | 36.98 | 46.22 |

Observed reductions: 31.98% billed MB, 48.98% MB/success. Not a causal estimate
for all platforms: serial ordering, previously successful selected keywords, and
different realized internal failures/rotations are limitations. Geo quality still
requires review before rollout. This does NOT establish parity with daily cost.

Internal amplification: control 6 OCR recaptures + 4 generation-timeout rotations,
20 warmup/setup cycles. Candidate 4 OCR recaptures + 2 generation-timeout rotations
+ 1 input rotation, 17 cycles. Outer retries were zero in both. GOST terminal
connection byte totals (lower bounds) were 398.21 MB and 339.61 MB respectively;
these are not exact provider billing or per-request attribution.

Next authorized test: `cost_timeout_20260908/report.json`, identical city-first
legs except generation-timeout rotation off in candidate. Screenshot validation
stays enabled; no full stale queue restart. Total 1 GB guard with meter-lag caveat.

## 2026-09-07 investigation: current measurements supersede estimates below

Full stale ranking remains paused at the user's request. The historical sections
below are retained for context, not current budgeting.

| Workload | Billed MB/attempt | Billed MB/success | Evidence |
|---|---:|---:|---|
| Daily, Edge pm-clear enabled | 3.96 | 5.2 | 8,537 MB / 2,155 attempts / 1,648 sessions |
| Ranking with retries | 29.17 | 52.31 | 26,836 MB / 920 attempts / 513 successes, chain 09-07 |
| Controlled ZIP download | n/a | n/a | 10/10 successful 1 MB downloads; 13.792797 MB billed |
| Controlled city download, fresh short session IDs | n/a | n/a | 10/10 successful 1 MB downloads; approximately 9.77 MB observed, provisional |

ZIP-download meter: 51,957.710445 -> 51,943.917648 MB. This measures proxy
billing, **not ranking success or ranking MB/success**. It used no phones. Waited
for the balance deduction and six unchanged ten-second reads afterward.

City meter started at 51,930.534488 MB. The initial settled reading of
51,921.666108 was premature: another charge posted by 20:59, with the balance
at approximately 51,920.77 MB. The 21:02 full-precision reading was
51,920.766357 MB (9.768131 MB deducted, approximately 29.18% below ZIP).
However, the daily started proxy traffic at about 21:01, before a fully isolated
five-minute settlement window could be verified. Treat this saving as provisional,
not a proven ranking reduction. The earlier 35.70% claim is withdrawn.
API `extra` stayed at 7.76 MB during the initial corrected city run; the observed
additional usage was `default` traffic. City accuracy/result quality still needs
the matched phone sample before the production policy changes.

Discarded city controls: an early trial reused the ZIP session IDs and used an
underscore city name, so its 13.37 MB deduction cannot establish city savings.
Fresh long session IDs produced ten rejected requests (0 completions). Correct
dot-separated `new.york` plus production-style ten-character random sessions
gave ten completed downloads. Do not use rejected requests as cheap successes.

The matched ranking trial is now managed by `com.deviceagent.bandwidthtrial0907`.
It waits for the daily and uses ten fixed Gemini keywords per leg, first normal
ZIP-first routing then `EVOMI_CITY_FIRST=1`, with all other controls identical.
Outputs: `cost_trial_20260907_v3/report.json`, per-leg CSV/logs/meter/byte ledger.
The original waiting supervisor was replaced before starting any jobs to load
a minimum five-minute post-traffic wait plus two minutes of stable readings.
The final supervisor also waits five minutes after the daily, rejects top-ups
and between-leg meter drift, and validates exactly ten expected distinct pairs.
The keywords were previously successful, not a random sample of the stale set.
It has no authority or code to resume the full stale queue. A 1 GB guard stops
the sample (delayed accounting can overshoot it), with a 10 GB balance reserve.

The Evomi usage API shows 4,861.18 MB of `extra` billing versus 27,031.84 MB
total across hourly buckets 2026-09-06 20:00 through 2026-09-07 01:00 UTC,
approximately the expensive ranking leg (bucket boundaries differ from the leg).
The extra component is 17.98%. Ranking emits `_zip-...`, the only expert
parameter found in its generated credentials. Daily does not. Evomi documents
ZIP as an extra-bandwidth feature:
https://docs.evomi.com/proxy-instructions/residential-proxies/expert-settings/zipcode/
https://docs.evomi.com/public-api/endpoints/bandwidth-usage/

Measurement corrections:

- On macOS, `seq 1 0` emits `1` and `0`. Thus the former zero-retry test actually
  launched two retry rounds. Fixed using an arithmetic loop; 0/1/2 cases checked.
- Immediate unchanged balances do not mean zero traffic; billing arrived later
  during the controlled download. Earlier interrupted samples lack attribution.
- A 2–3 minute absence of CSV output does not prove startup failure. Ranking
  includes a 60-second warmup plus generation. Optional phase timestamps now
  distinguish tunnel, warmup, reset, and session time.
- The proposed Gemini OCR bypass also bypassed inconsistent-rank detection.
  It now requires a parsed text rank with no inconsistency, and is opt-in again.
- Shorter tunnel waits and skipped input rotations remain opt-in; neither has a
  matched result-quality/cost sample proving an improvement.
- Optional GOST_COST_LEDGER saves sanitized per-listener traffic counters before
  log removal. These count completed connections and are lower bounds; Evomi is
  still the billing authority.

Browser cache is not automatically erased by a new proxy IP. Explicit browser
data clearing causes cold downloads; the earlier cache explanation below is
inaccurate. Screenshot transfer over ADB is local, but browser reloads/repeated
generation caused by screenshot validation consume proxy traffic.

---

**Version:** 1.0 · **Date:** 2026-08-14 · **Owner:** Fleet Ops
**Purpose:** Explain what our proxy (rented internet connection) usage costs, per check and per
batch, **and why each number is what it is** — so the team can budget and make provider decisions.

---

## 1. Background — how we got here

Our phones can't just use our office internet: the AI sites (ChatGPT, Gemini, Perplexity)
must see each check coming from the **right US location**, or they refuse or give the wrong
local answer. So every check is routed through a **residential proxy** — a real home internet
connection we rent in the target area.

The provider situation evolved:

1. **Originally:** everything ran on **Decodo**, which can pin us to an exact **zip/city**.
   Accurate, but priced higher (~$3.5/GB).
2. **Decodo funding lapsed**, so we temporarily moved the **daily engagement** work to
   **DataImpulse** (~$1/GB, cheaper). It worked perfectly (100%) because engagement checks
   are quick.
3. **We tried ranking on DataImpulse too — and it failed** (only ~1% of checks succeeded).
   *Why:* a ranking check holds one connection open ~150 seconds (load the page, wait for the
   AI to finish writing, screenshot it). DataImpulse's default gateway **changes the exit IP
   mid-check**, which breaks that long capture.
4. **The fix:** DataImpulse also offers "sticky" connections that **keep one IP for the whole
   check**. Switching to those took ranking from ~1% to ~78% success. So ranking now works on
   DataImpulse — but only at **state-level** accuracy (it can't do exact zip like Decodo).

**Where that leaves us:** daily on DataImpulse (cheap, works), ranking on DataImpulse-sticky
as a working stopgap, and Decodo held for ranking again once funded (for zip-exact client reports).

---

## 2. How proxy billing works (why we cost what we cost)

Residential proxies bill by **data used (bandwidth)**, not by number of checks — exactly like
a phone data plan. So our cost is driven by just two things:

- **How much data one check uses** (megabytes), and
- **How many times a check has to run** (failed checks retry and re-spend data).

Nothing else. Note: the **screenshot itself is saved locally over USB, not through the proxy**,
so it costs nothing in data.

**Definitions:**
- **Job / check** = one keyword on one AI site.
- **Run / batch** = all the jobs in one session (e.g. a full daily, or one ranking sweep).

---

## 3. Why ~3 MB per check

One check downloads a full fresh page (the site's code + images) plus the AI's written answer.
Because every check uses a new IP, nothing is cached — the page loads from scratch each time.
That adds up to roughly **3 MB per check** (our working estimate; range 2–5 MB). For scale,
that's about like opening a couple of normal web pages.

> This 3 MB is an **estimate** — we don't yet meter exact bytes. The provider dashboard shows
> real GB used; dividing that by checks over a period would confirm it.

---

## 4. Why checks retry — and the real multiplier

Some checks fail on the first try (a slow IP, the AI didn't finish, a bad screenshot), so the
system **automatically retries** them. Retries use more data, so we count them.

We **measured** this on the Aug 13 ranking run: **1,385 total attempts produced 904 finished
results** → a **1.53× multiplier**. In other words, delivering 900 good results really costs
about 1,385 checks' worth of data. (Daily retries are lower, ~1.3×, and still being measured.)

---

## 5. Cost per check (per job)

Formula: **cost = data-per-check × price-per-GB**.

**Data per check: ~3 MB.** At our current DataImpulse price (~$1/GB):

| Price per GB | Data / check | **Cost / check** |
|---|---:|---:|
| **$1 (DataImpulse, current)** | 3 MB | **$0.0030** (≈ ⅓ of a cent) |
| $3.5 (Decodo) | 3 MB | $0.0105 |

Counting retries, each **finished** result really costs ~4–5 MB — about **$0.0046** on
DataImpulse. Still under half a cent per usable result.

---

## 6. Cost per batch (per run)

Formula: **cost = checks × retry × data-per-check × price-per-GB**.

| Batch | Checks | Retry | Real attempts | Data used | **Cost @ $1/GB (current)** | Cost @ $3.5/GB (Decodo) |
|---|---:|---:|---:|---:|---:|---:|
| **Daily engagement** | ~1,600 | 1.3× | ~2,080 | ~6 GB | **~$6** | ~$21 |
| **Ranking sweep** | ~900 | 1.53× | ~1,385 | ~4 GB | **~$4** | ~$14 |

*To size a different batch:* `cost = checks × retry × 0.003 GB × price`.

**Why the daily costs more than a ranking sweep** even though a single ranking check is heavier:
the daily simply runs **more checks** (~1,600 vs ~900).

---

## 7. Provider choice (why the split)

| | **Decodo** | **DataImpulse** |
|---|---|---|
| Location accuracy | **Exact zip / city** | **State only** (no zip) |
| Price *(confirm)* | ~$3.5 / GB | ~$1 / GB |
| Best for | **Client ranking reports** (location must be exact) | **Daily engagement** (location can be looser) |
| Special note | — | Ranking must use a **sticky connection**, or it fails (see §1.3–4) |

**Recommendation:** keep **daily on DataImpulse** (cheap, works), and move **ranking back to
Decodo once funded** for zip-exact client reports — using DataImpulse-sticky in the meantime.

---

## 8. Assumptions & what to confirm

The dollar figures are close estimates. Two inputs would make them exact:

1. **Real price per GB** — from each provider's latest invoice.
2. **Real data per check** — from the provider dashboard (GB used ÷ checks over a known window).

---

## 9. Measured usage — 2026-09-03 (supersedes the estimates above)

**Version:** 1.1 · Everything below is read from the provider's own meter
(`evomi_balance.py`) either side of a controlled run — not modelled.

### 9.1 The headline correction

§3 assumes **~3 MB per check for both workloads**. That is right for the daily and
**wrong for ranking by roughly 6x**:

| Workload | §3 estimate | **Measured** | Basis |
|---|---:|---:|---|
| Daily engagement | ~3 MB | **1.96 MB/job** | 1,702 jobs, 3,338 MB, 2026-09-02 |
| Ranking (single pass) | ~3 MB | **16.6 MB/job** | 21 jobs, 348 MB, 2026-09-03 |
| Ranking (single pass, repeat) | ~3 MB | **16.98 MB/job** | 230 jobs, 3,904 MB, 2026-09-03 |

An earlier note records **~34 MB/job** for ranking (2026-08-29), attributed there to
"full Chrome clear + screenshots". That figure is NOT reproduced by either measurement
above and its conditions are unknown. The likeliest difference is platform mix: it
predates Copilot, which is the cheapest platform at 8.99 MB and pulls the average down,
and it was taken on a different provider. **Treat 16.6-17 MB/job as the current number
and 34 as unexplained** until someone re-measures a with-retries run.

### 9.2 Per platform (ranking, Evomi, retries off)

| Platform | MB/job | MB per *successful* job |
|---|---:|---:|
| **Copilot** | **8.99** | 12.59 |
| ChatGPT | 16.28 | 22.79 |
| Gemini | 24.38 | 42.66 |

Copilot is the cheapest platform by a wide margin — about a third of Gemini. That is a
real argument for the Perplexity -> Copilot swap independent of ranking quality.

### 9.3 Where ranking's extra data goes

Ruled OUT by reading the code: both flows do a full Chrome clear (`fullClear = true`),
and ranking actually waits *less* (150s vs the daily's 240s). Neither explains the gap.
What remains:

1. **Retries — NOT yet measured.** Both figures above are single-pass
   (`run_ranking.py` directly). A production run uses `run_ranking_auto.sh`, which
   loops up to 40 retry rounds, and `audit_dispatch_http.py` builds a `GostManager` at
   three points (initial, retry, OCR re-capture), so a planned "job" can be several
   full page loads. The multiplier is plausible but UNQUANTIFIED — do not budget with
   a number for it until a retry-loop run is metered.
2. **Screenshots + re-renders.** The daily takes **zero** screenshots; ranking captures
   one and may re-render the page again via `_cdp_js_frame_screenshot` /
   `_cdp_strip_map_screenshot`.
3. **Richer answers.** Ranking asks for a local top-3, so platforms render place cards
   and map embeds (images); the daily's conversational prompts render mostly text.
4. **Scrolling.** `scrollToRankLine` up to 14 swipes lazy-loads content the daily never
   reaches.
5. **Tunnels.** One gost per *job* for ranking; one per *wave* for the daily.

### 9.4 Failure rate is a bandwidth problem

Every failed attempt still pays full freight, so the failure rate IS a cost driver:

| Workload | Success | Dominant failure |
|---|---:|---|
| Daily | 91% | `http fail` — 132 of 156 |
| Ranking | 65-67% | `RemoteDisconnected` on the opening POST |

Measured 2026-09-03: making the phone run sessions asynchronously (v77, `/result`
polling) did **not** move the ranking rate (65% vs 67%). The disconnect happens on the
*initial* request, not from holding one open — only 1 of 230 jobs died while polling.
The remaining cause is the phone's HTTP server refusing connections at connect time.

Copilot specifically ran 45% (36/80) under 15-worker concurrency, with 23 of its 40
errors being Edge first-run faults (`reset_edge` x12, `open_copilot` x11) — every job
`pm clear`s Edge and must re-walk a 4-screen wizard. Not exercised by single-phone tests.

### 9.5 Provider status and runway

§7's provider table is out of date. As of 2026-09-03:

| Provider | State |
|---|---|
| **Evomi** | **Working.** Zip targeting verified; the only pool in use. |
| Decodo | **Refusing auth** (`rejected by the SOCKS5 server (1 3)`) since ~2026-09-02 |
| DataImpulse | Dead (per 2026-08-29) |

At 45.8 GB remaining:

- Daily only: **~14 nights** (3.3 GB/night)
- Remaining stale ranking set (3,287 jobs): **~53 GB** at the measured single-pass rate.
  A production run adds retries on top, so the true figure is higher by an unmeasured
  margin — **it does not fit within 45.8 GB either way**

The stale set cannot be completed on the current balance at either rate. Cutting the
failure rate should help — every failed attempt pays full freight — but the size of that
saving is not yet measured, so it is a direction, not a costed plan.
