# Device farm — monthly proxy cost forecast

As of September 8, 2026. USD, before taxes/payment fees. Planning month: 30 days.
Scope: this Mac's device farm and its daily/ranking processes, not other farms
that might share an account. No provider switch, purchase or production change
was made to prepare this forecast.

## Executive budget

For the current measured workflow, plan **about $306/month on Evomi** if ranking
resumes at **two 3,492-pair sweeps/month**, or **$367 with a 20% bandwidth allowance**.
While ranking remains paused, the daily-only run rate is **about $126/month**.
These use Evomi's public Core subscription terms, not a verified account invoice.
The buffer is a planning choice, not a statistical confidence interval.

**Do not budget the whole farm at 4.12 MB/job.** That is a small, warmed-cache,
Gemini-only experiment, not the deployed mixed-platform production rate.

## 1. Demand and measurement assumptions

| Input | Value | Evidence / limitation |
|---|---:|---|
| Daily bill | 8,537 MB/night | Recorded provider-meter run: 2,155 attempts / 1,648 successful sessions |
| Daily monthly traffic | 256.11 GB | 30 identical nights; not a measured 30-day average |
| Ranking bill with failures/retries | 26,836 MB / 513 successes | September 7 chain sample, 920 logged attempts |
| Ranking cost per accepted pair | 52.311891 MB | Includes failed work and retries already; do not multiply by retries again |
| Planning sweep size | 3,492 accepted pairs | Historical stale-set size; pair = keyword × platform, NOT three platforms per pair |
| Base recurrence | 2 sweeps/month | Assumption pending business confirmation; stale eligibility has a 14-day cutoff, not a guaranteed schedule |
| Monthly ranking output | 6,984 successful pairs | Base planning target, not a capacity guarantee |
| Decimal unit convention | 1 GB = 1,000 MB | Confirm provider invoice unit conventions before purchase |

Local evidence: [cost specification](../PROXY_COST_SPEC.md),
[runner's stale eligibility](../run_ranking.py), and
[settled cache pilot](../cost_cache_pilot_20260908/report.json).
Historical sections of the specification describe obsolete providers and older
3 MB assumptions; they are NOT the baseline used here.

The daily session and ranking pair are different deliverables. The mixed daily
average cannot be used as a matched Gemini ranking control. More phones do not
directly multiply a bandwidth bill at fixed output, but concurrency can change
failure rates and hence bandwidth per accepted result.

## 2. Monthly scenarios

| Workload scenario | Daily GB | Ranking GB | Total GB | Evomi USD/month |
|---|---:|---:|---:|---:|
| Daily only; ranking stays paused | 256.11 | 0 | 256.11 | $126.48 |
| Daily + one full ranking sweep | 256.11 | 182.67 | 438.78 | $215.99 |
| Daily + two sweeps: base planning case | 256.11 | 365.35 | 621.46 | $305.50 |
| Base plus 20% bandwidth allowance | — | — | 745.75 | $366.41 |
| Daily + steady 14-day ranking cadence | 256.11 | 391.44 | 647.55 | $318.29 |

One-off backlog is separate from recurring cost: the last recorded 1,384/3,492
completed implies 2,108 remaining pairs, roughly **110.27 GB / $54.03 additional
Evomi overage** at the old aggregate rate. Reconcile the actual outstanding queue
before allocating that amount; do not add it if already included in a planned sweep.

Formula:

```text
ranking_MB_per_success = 26,836 / 513
monthly_GB = nights × 8.537 + successful_ranking_pairs × ranking_MB_per_success / 1000
Evomi_USD = 49.99 + max(0, monthly_GB - 100) × 0.49
```

## 3. Provider comparison — conditional migration estimates

**Only Evomi has a current measured farm baseline.** Other rows hold output,
traffic and success rates constant to show price sensitivity. They are not
measured migration costs or claims that those accounts work today. Evomi billed
GB includes its targeting extras; the same number is used as a workload proxy
for other providers because matched raw-byte/provider-meter tests do not exist.
That can overstate their traffic. Different success rates can instead increase
their cost. Replace the cross-provider workload multiplier after a matched test.

| Provider / tariff used | Daily only | Daily + two sweeps | Base +20% | Qualification |
|---|---:|---:|---:|---|
| Evomi Core: $49.99/100 GB + $0.49 extra GB | $126.48 | $305.50 | $366.41 | Current working provider; invoice still needed |
| DataImpulse: $1/GB × 2 for targeted traffic | $512.22 | $1,242.91 | $1,491.49 | Assumes all traffic uses paid state/city/ZIP targeting; historical account failure not re-tested |
| Rayobyte Professional: $1.50/GB | $384.17 | $932.18 | $1,118.62 | 250–999 GB published tier; bulk alternative below; local city/pool/concurrency limitations remain |
| Decodo PAYG: $4/GB | $1,024.44 | $2,485.82 | $2,982.99 | Flexible benchmark, NOT its cheapest volume offer; historical auth failure not re-tested |

Pricing checked on official pages September 8:

- [Evomi pricing](https://evomi.com/pricing): Core subscription is 100 GB for
  $49.99/month and $0.49 per additional GB. Do not confuse Premium Residential
  prices elsewhere on the page with Core. Account-specific terms may differ.
- [Evomi ZIP documentation](https://docs.evomi.com/proxy-instructions/residential-proxies/expert-settings/zipcode/):
  ZIP targeting consumes extra bandwidth. It is ALREADY in our metered baseline;
  no additional ZIP percentage has been added to the Evomi forecast.
- [DataImpulse pricing](https://dataimpulse.com/residential-proxies/): $1/GB standard,
  $800 for 1 TB at the listed advanced rate, with non-expiring credit. Its official
  [state](https://docs.dataimpulse.com/proxies/parameters/state),
  [city](https://docs.dataimpulse.com/proxies/parameters/city) and
  [ZIP](https://docs.dataimpulse.com/proxies/parameters/zip) instructions specify
  double-rate traffic. The current docs also supersede our old claim that the
  provider has no city/ZIP capability; our adapter and pool still need validation.
- [Rayobyte residential pricing](https://rayobyte.com/buy-ethical-residential-proxies/):
  $1.50/GB for 250–999 GB, $0.70/GB for 1,000–4,999 GB. Its
  [billing FAQ](https://portal.rayobyte.com/en/support/solutions/articles/64000272133-residential-proxy-billing-faq)
  says purchased residential bandwidth does not expire. Public pages show different
  starting offers; confirm the specific dashboard tariff before committing.
- [Decodo residential pricing](https://decodo.com/proxies/residential-proxies):
  $4/GB PAYG; 100 GB subscription is $275/month; advanced geo-targeting is included.
  Request a 600–750 GB quote. Do not extrapolate the 100 GB subscription's rate
  to unlimited overage or assume the advertised $2/GB floor applies at our volume.

### Purchase cash versus consumption cost

The table above is not a checkout recommendation. For the base case, if the
published volume packages apply and accounts start with no credit:

| Alternative package | Equivalent monthly consumption cost | Initial cash commitment | Why different |
|---|---:|---:|---|
| Rayobyte 1,000 GB at $0.70/GB | $435.02 | $700 | 378.54 GB unused credit remains after a 621.46 GB month |
| DataImpulse advanced 1 TB at $800, targeted 2× | $994.33 | $1,600 for two 1 TB blocks | Needs 1,242.91 billed-credit GB; remaining credit carries forward |
| Decodo negotiated volume plan | Quote needed | Quote needed | A verified plan/overage schedule is missing |

Bulk consumption rates only apply after the qualifying purchase; cash payments
will be lumpy rather than identical each month. Existing credit, subscription
renewals, expiry rules, rounding, tax and negotiated invoices must be reconciled.
On the stated assumptions Evomi remains the lowest modeled option, including
the listed bulk alternatives, but provider performance must decide migration.

## 4. Workflow optimization opportunities

| Priority / workflow | What the evidence says | Forecast treatment / next validation |
|---|---|---|
| 1. Preserve Gemini static HTTP cache, reset conversation/identity | Pilot: 24.705904 MB / 6 accepted successes = 4.117651 MB/success, including a seventh interrupted attempt. Earlier single success: 20.970692 MB. Six screenshots personally verified. | Promising, default-off on fleet. Finish remaining four IDs; test first cold load, mixed-platform clears, different devices and sustained accuracy. No whole-farm savings booked. |
| 2. Recover screenshots from the existing answer | Same-answer framing recovered complete rankings without regenerating them in successful tests. Legacy screenshot processing still consumed enough time to hit the pilot cutoff. | Keep strict rank/full-answer checks. Measure residual capture-only traffic; do not add this saving to cache saving because the pilot used both. Local ADB PNG transfer itself is not proxy traffic. |
| 3. Targeting ladder / unnecessary ZIP premium | Matched ten-job serial legs: ZIP-first 543.62 MB/6 successes; city-first 369.78 MB/8 successes. | About 49% lower observed MB/success in that sample, not a universal rate. Require client geo acceptance and fresh matched samples. Do not stack with cache savings. |
| 4. Retry scheduling and unhealthy-device quarantine | Old ranking spent 26.8 GB for 513 successes. Disabling generation-timeout rotation in a matched sample worsened MB/success: 49.76 → 68.78. | Do not simply disable every retry. Track accepted successes per billed GB by failure class, defer repeated failures, exclude device125 and investigate108 before reuse. No invented savings percentage. |
| 5. Per-job preflight/tunnel reuse | 1,431 preflights in the historical ranking leg; ranking creates a proxy per job while daily reuses per wave. | Measure setup-only bytes and safe reuse by required location/session. Counts alone do not establish a large cost. No savings booked. |
| 6. Shorter warmup / proxy idle time | Prior idle test used 0.048679 MB/180s; a traced 60s warmup used about 0.004 MB. Large cold load was before prompt submission. | Low priority for bandwidth; may save time. The short-warmup comparison was confounded. Longer connection time alone is not the main measured driver. |
| 7. Daily / Edge reset optimization | Daily currently about 8.5 GB/night. Edge pm-clear and Copilot concurrency cap4 were important reliability fixes. | Keep both. Test any lighter reset on isolated jobs with quality and meter evidence before rollout. A hypothetical 10% daily reduction is 25.61 GB / $12.55 Evomi per month, NOT achieved. |
| 8. Direct/off-proxy diagnostics and asset isolation | Direct smoke tests and local screenshot/DOM inspection do not require paid proxy traffic. Browser cache avoids repeated assets without moving geo-sensitive requests to another exit. | Keep APK transfer/OCR/local inspection off-proxy. Investigate unexpected background traffic with per-host traces. Do not bypass AI/navigation/DNS geo checks or blindly block rendering assets. |

Pilot evidence: [analysis](../cost_cache_pilot_20260908/ANALYSIS.md),
[earlier cold phase attribution](../cost_one_phase_20260908/ANALYSIS.md),
[city trial](../cost_trial_20260907_v3/report.json),
[timeout trial](../cost_timeout_20260908/report.json).

### What the pilot might mean financially — not a committed budget reduction

For every **1,000 comparable Gemini successes/month**, reproducing the earlier
20.970692 → 4.117651 MB comparison would save **16.85 GB**, or **$8.26/month** at
Evomi's marginal $0.49 rate. For 2,328 Gemini successes (one third of the assumed
6,984-pair monthly output), that illustration is **39.23 GB / $19.22/month**.
Do not apply the 80% experiment reduction to the entire 621 GB farm forecast.
Actual production Gemini success-adjusted cost is not separately established
under the same retry/platform mix; monthly savings remain uncommitted.

## 5. Operational cost controls and missing inputs

Keep a daily ledger by provider/workflow/platform: starting and settled ending
balance, accepted successes, failed/interrupted attempts, targeting tier, cache
state, bytes per successful result, and invoice rate. Separate test traffic from
production and mark overlapping account use as unattributable. Recompute the
forecast from at least seven normal nights and a complete ranking cycle.

Use the measured per-success rate for forecasting successful output; use the
per-attempt rate only when the input is explicitly an attempt count. Track the
next nightly reserve separately from ranking spend authorization. A 20% reserve
around the measured nightly demand is about 10.25 GB, before concurrent work.

Confirm before making purchase decisions:

1. Actual monthly ranking success target/cadence and current active pair count.
2. Invoices/discounts, plan minima, GB unit definitions and targeting surcharges.
3. Whether other Macs/services consume the same proxy accounts.
4. Per-provider success/geo quality on the same controlled farm sample.

## 6. Editable files

- [inputs.json](inputs.json): workload, tariff and buffer assumptions.
- [monthly_forecast.csv](monthly_forecast.csv): spreadsheet-readable scenario table.
- [calculator](../tools/forecast_proxy_costs.py): offline, no network or production actions.

```bash
python3 tools/forecast_proxy_costs.py --inputs proxy_forecast_20260908/inputs.json --output proxy_forecast_20260908/revised_forecast.csv
```

Use a new output filename; existing files are never overwritten by the calculator.
The calculator's Rayobyte Professional rate is intended for these 250–999 GB
scenarios; changing volume outside that range requires updating the tariff.
