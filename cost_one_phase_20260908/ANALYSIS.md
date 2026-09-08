# One-job bandwidth attribution — 2026-09-08

One bounded kw64 / Gemini / device-104 / installed v79 attempt. Full stale queue
remained disabled. City-first, one attempt, no outer retry, screenshot OCR enabled.
No browser behavior changes for this test; only opt-in localhost byte telemetry.
The authoritative settled report is complete: before39632.432320MB,
after39607.931103MB, charged24.501217MB, zero accepted successes. Settlement
waited at least300seconds after completion and120seconds of stable readings.

## Measured local traffic

GOST live counters recorded 24.859020 decimal MB, including still-open connections.
These are local SOCKS bytes, NOT Evomi billing MB. Do not add the old terminal
connection ledger or sum cumulative snapshots. Provider preflight before GOST
starts is outside this trace. Native boundaries have approximately one-second
sampling uncertainty; host/phone clock alignment was checked.

| Interval | Local MB |
|---|---:|
| Everything before Gemini navigation, including reset | 0.591539 |
| Gemini navigation through start of prompt submission | 16.925986 |
| Submit through native response returned to dispatcher | 4.184962 |
| Post-response screenshot/reframe/CDP/OCR and background traffic | 3.156533 |
| Total | 24.859020 |

The 60-second warmup alone was 0.004355 MB. Thus approximately 68% of observed
local bytes arrived in the Gemini loading/input interval BEFORE submission.
This identifies an expensive phase, not necessarily every traffic destination.
It does not prove that input automation itself caused those downloads.

The browser's existing Resource Timing buffer was read after teardown, without
navigation, reload, new prompts or fetching any asset. It contained 133 entries,
including 60 gemini.gstatic.com script entries. Their exposed transferSize values
were zero (cross-origin restrictions or caching); do NOT treat those as measured
zero-byte downloads or claim all 16.9 MB was those scripts.
The visible StreamGenerate response transferSize was 104684 bytes (0.104684 MB),
encoded body 104384 bytes, decoded body 850246 bytes. This is that response only,
not all generation-related traffic. Visible font transfers summed to 467948 bytes.

## Correctness result: failed screenshot acceptance

Native generation completed with rank 4/4, but the original screenshot displayed
large place cards and app/sign-in banners; the complete list/rank did not fit.
Same-answer recovery rejected full_answer_clipped_or_changed. The dispatcher
then tried its legacy CDP fallback. Root viewed both original and final PNGs;
neither is an acceptable complete ranking screenshot. CSV correctly remains
ocr_no_answer. No retry was launched and this must NOT be labeled a successful
or cheaper finished pair. The preceding single successful recovery is therefore
not evidence the recovery now works for all layouts.

Current logs retain the helper's reason but not frame_diagnostics, so this failure
cannot distinguish every geometry condition retrospectively. Oversized place
cards are visibly present; answer mutation is not proved by the generic reason.
Post-response bytes mix browser background loading and screenshot work: they are
not an isolated measured cost of reframe or CDP.

## Daily comparison and next target

Daily and ranking Gemini both call native resetChrome(fullClear=true). Ranking
also has host-side Chrome pm clear. Do not claim this alone explains the daily
aggregate versus ranking gap: the daily ~3.96 MB/attempt is a mixed-platform
average, not a matched Gemini control. Edge clearing is unrelated to this Gemini
sample and the measured Copilot cap/clear settings remain unchanged.

Target the cold-page download interval next. A resource-level trace attached
before Gemini navigation can identify scripts/images/fonts and encoded network
bytes. Test retaining only safe static browser cache while resetting conversation
and identity, rather than reusing an old answer or changing location/session
semantics. Cache-preserving behavior is NOT implemented or validated yet; no
fleet rollout or claimed savings. Also repair oversized-answer capture without
removing answer text, hiding missing ranks, or regenerating a paid answer.

## Research used

- [GOST live metrics](https://latest.gost.run/en/tutorials/metrics/) and
  [version-matched connection wrapper](https://github.com/go-gost/x/blob/v0.8.1/metrics/wrapper/conn.go):
  basis for cumulative live-connection counters rather than terminal records.
- [Evomi usage API](https://docs.evomi.com/public-api/endpoints/bandwidth-usage/):
  normal/extra billing breakdown. The previous successful 20.97 MB hour had
  20.97 normal, zero extra, ruling out targeting surcharges for that sample.
- [Chrome Network protocol](https://chromedevtools.github.io/devtools-protocol/tot/Network/):
  request tracking and separate browser-cache/cookie controls for the next
  measured cache investigation. This documentation does not prove savings.

Evidence: report.json, meter.jsonl, candidate/phase_summary.json,
candidate/gost_phases.jsonl, candidate/resource_timing.json, candidate/ranking.log,
and the unchanged failed candidate/results_2026-09-08.csv.
