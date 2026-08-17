# Proxy Cost Specification — Fleet Operations

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
