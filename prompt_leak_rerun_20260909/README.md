# Four Gemini replacement captures — 2026-09-09

## Capture outcome: four attempted, zero accepted

Settled Evomi cost: **98.461371 MB total; 24.615343 MB per attempt; no successful
replacement denominator**. Before31,329.605677MB; after31,231.144306MB. Settlement
completed04:54 Manila after at least300seconds and120seconds of stable readings.
Production79 was confirmed after cleanup with accessibility enabled. No Gost,
ranking runner or fleet lock remained; the full stale queue was still disabled.

The four-job pass ran 04:34–04:48 Manila on production device104. No automatic
retry was launched, and no original report was replaced. Billing is recorded in
`report.json` after settlement; its `complete` means measurement completed,
not that these replacement captures succeeded.

- Charles/Tattoo: `ocr_no_answer`. Root viewed both saved images: prompt plus
  oversized Maps cards, not the full ranked answer. Response text contained the
  prompt's example `[RANK: 4/4]`, but no model answer. Native generation-wait
  reported success after four seconds. The host did not accept that example rank.
- AppsTango/Silicon Slopes: `error`, input failed after 38 seconds.
- AppsTango/St. George: `ocr_no_answer`. Root viewed the live loading screen and
  saved final image: Maps cards plus prompt, incomplete ranked answer. Native
  generation-wait reported success after three seconds.
- KDR/roll off dumpster rental: `flow_failed`, submit failed after 13 seconds,
  then generation wait failed after 150 seconds. Root observed voice input and
  a microphone permission prompt on the live screen. Root tapped "Never allow"
  during this last attempt; no microphone permission was granted. This manual
  intervention must be disclosed in any analysis of this run.

Do not trust the launcher's `FINISHED remaining=0` line for this run: with
`RANK_RETRY_ROUNDS=0`, it does not calculate remaining failures. All four still
need valid replacement captures. The Desktop `_attempt_results.csv` labels them
explicitly and includes original report dates separately from the new run date.

Before further paid retries, test answer-only completion detection and reliable
text-input/submit targeting without proxy traffic. This run does not establish
that Gemini's model produced any of the apparent `4/4` positions.

Requested source: `~/Desktop/Rankings/prompt_leak_top3_rerun_2026-09-09.csv`.
Only its four Gemini rows are in scope; the 45 retired Perplexity rows are excluded.

| Original report date | Client | Keyword | Keyword ID | Old position |
|---|---|---|---|---|
| 2026-08-04 | Charles Huurman | Tattoo | 345 | 2 |
| 2026-08-13 | Scott Kincaide | roll off dumpster rental | 143 | 3 |
| 2026-08-18 | Russ Thornton | hire software developers St. George | 4711 | 3 |
| 2026-08-18 | Russ Thornton | custom software development Silicon Slopes | 4680 | 1 |

These are new observations, not proof of the historical August rankings. Old
positions identify the requested repairs; new results must not be forced to match.
Original reports are not overwritten and no backend upload is performed here.

Execution: device104 only, Gemini only, four jobs, one attempt each, no outer
retries. Default geo targeting and production APK retained. Experimental cache
preservation is off; same-answer screenshot recovery and OCR validation are on.
The full stale queue stays disabled.

The supervisor records the Evomi balance before and after billing settlement,
with a 150 MB stop threshold and a 10 GB nightly reserve. Delayed billing can
overshoot a threshold. See `report.json`, `meter.jsonl`, and `candidate/` for
execution evidence. Do not treat a supervisor's `complete` status as four accepted
captures: check `successful_pairs` and review every screenshot separately.
