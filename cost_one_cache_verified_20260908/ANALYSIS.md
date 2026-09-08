# Cache-preserving Gemini ranking trial — 2026-09-08

One kw64 / Carrot Software / Eugene / device-104 attempt succeeded, rank 2/3.
The provider report is COMPLETE: before39607.792208MB, after39604.881585MB,
charged2.910623MB for one accepted success. Settlement waited>=300seconds after
the attempt and>=120seconds of stable readings. This is86.12% below the earlier
20.970692MB successful sample (not a fleet-average or isolated randomized A/B).
Including the setup-only failure, this continuation spent3.049518MB on Evomi.
Device-104 was restored to v79 after settlement. Full stale queue never resumed.

## What changed

Experimental v82 audit flag geminiCachePrepared defaults false. The host trial
is restricted to device-104, Gemini, one attempt, and verified native v82.
It closes old tabs, creates a fresh blank tab, clears all browser cookies and
Gemini/Google origin storage (including service workers and CacheStorage), and
requires two consecutive clean-state checks. It never requests HTTP-cache deletion.
The app skips its redundant full Chrome wipe only after this verified preparation.
Normal daily, Copilot cap/Edge clearing, targeting defaults, and fleet APKs are
unchanged. The test wrapper restores device-104 to its original v79 afterward.

The separate same-answer screenshot fix now tries zoom .65, .55, then .50 while
preserving the complete answer, rank, OCR and geometry guards. Original style is
restored. The prior oversized 4-card answer was recovered on its existing page
without a proxy, navigation or new generation. This trial's final actual phone
screenshot visibly shows Twenty Ideas, Carrot Software, IEQ Technology, and
[RANK: 2/3]; root inspected it personally. No retry or regenerated screenshot job.

## Measured traffic, not estimated by proxy duration

| Local interval | Prior cold traced attempt | Cache trial |
|---|---:|---:|
| Gemini opening → submission | 16.925986 MB | 1.799744 MB |
| Native session start → response returned | 21.680983 MB | 2.704690 MB |
| Post-response capture/OCR/background | 3.156533 MB | 0.047706 MB |
| Total GOST live counters | 24.859020 MB | 2.853215 MB |

The 60-second warmup remains unchanged and used .004262 MB locally. The major
reduction is in downloads, not merely less time connected. Local counters and
browser encoded bytes are separate accounting layers; never add them to the
provider meter or treat their totals as billed MB.

Passive Chrome Network observation finished 134 resources with 38 cache hits,
2.045188 MB encoded network bytes, no protocol errors and zero unfinished requests.
Of 58 gemini.gstatic.com script responses, 17 were cached; transferred script
bytes totalled 1.756187 MB. All 3 fonts were cached. Both Gemini document responses
and all 31 Gemini XHR responses were non-cached; the experiment did not reuse an
old answer page. Early events can race attachment; this is not a complete bill.
Queries, cookie values, arbitrary headers and response bodies were not retained.

## Honest comparison and limits

The earlier same-keyword successful v79 job cost20.970692 MB. The cold traced v79
attempt cost24.501217 MB but failed screenshot acceptance, so it is NOT a prior
cost per success. Compare the current provider report to those outcomes separately.

This is a warmed-cache, single-phone, single-keyword result, not a randomized
fleet average. Direct tests warmed the browser beforehand. A first cold load still
costs bandwidth; cache eviction, different assets, different cities/businesses,
and other jobs that fully clear Chrome can change the result. v82 also contains
the earlier native failed-input/submit evidence fixes, and the capture helper
changed, so the whole-run difference is not a pure isolated cache effect.
The reduced pre-submit phase plus observed cache hits directly support cache
reuse as a substantial contributor.

Daily and other ranking platforms still fully clear Chrome. A mixed-platform
rollout therefore needs scheduling/cache-isolation validation; do not assume
Gemini's cache survives a ChatGPT or host-side Copilot Chrome clear. Before any
fleet rollout, validate distinct businesses/locations, clean-session identity,
first-cold versus warmed costs, screenshot correctness and aggregate success rate.
The experimental cache flag remains OFF by default; no fleet deployment or queue
restart was performed.

Debug accounting: cost_one_cache_20260908 was a setup-only failure before prompt
submission, billed0.138895 MB. It was not relabeled as success. A repeat local
preparation passed; the original exact failure reason was not persisted, so its
cause is not proved. The helper now allows bounded settling while requiring two
clean snapshots and saves failure-stage evidence. The successful paid receipt
shows2clean snapshots,2checks,0reclears. Direct v82 tests were unproxied and the
Evomi balance stayed unchanged until the paid attempts.

## Research and evidence

- [Chrome Network protocol](https://chromedevtools.github.io/devtools-protocol/tot/Network/)
  documents separate cookie/cache operations and resource/cache events.
- [Chrome Storage protocol](https://chromedevtools.github.io/devtools-protocol/tot/Storage/)
  supplies origin-state clearing and usage verification. CacheStorage is distinct
  from the browser HTTP cache; actual reuse was verified by this trace.
- report.json / meter.jsonl: settled provider charge and timing.
- candidate/cache_prepared.json: verified blank session and empty identity state.
- candidate/network.jsonl: sanitized resource/cache receipts.
- candidate/gost_phases.jsonl / phase_summary.json: live bytes and native phases.
- candidate/results_2026-09-08.csv: one accepted success and screenshot path.
- ../direct_ui_20260908_phase_card_reframe_half: free oversized-answer replay.
