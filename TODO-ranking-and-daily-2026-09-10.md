# Approved work order — September 10, 2026

User requested this sequence. Do not launch September 9 daily before the gates below.

## 1. Finish the ranking bandwidth investigation/fix first

- [x] Resolve Copilot pilot with valid screenshots and settled Evomi measurements.
- [x] Do not promote the failed Edge cache-preservation experiment to the fleet.
- [x] Test off-proxy full-reset/bootstrap with Wi-Fi settlement on device104 only.
- [x] Verify two successful samples, original-APK restoration and no test VPN.
- [x] Commit scoped change, tests and operational documentation.

Measured successful control19.652356MB; Wi-Fi-settled runs0.629016 and0.540893MB,
both automatic1/8 with root-reviewed PNGs. Average0.584955MB (~97% lower).
This is a two-job pilot on104, NOT a fleet-wide reliability claim. The fix moves
fresh-profile downloads to ordinary Wi-Fi; it does not eliminate total network
bytes. All pilot flags remain defaultOFF. Controlled wider rollout remains needed;
do not restart the stale queue as part of the daily implementation.
See `docs/COPILOT_BANDWIDTH_WIFI_2026-09-10.md`.

YOKL delivery is already complete: 15/15 results. Do not rerun or overwrite those
results. Comparison samples remain separate. Daily and stale ranking stay paused.

## 2. Implement the new daily in device-agent AND AEO Admin backend

- [ ] Exactly **8 planned sessions per campaign/location per day**, shared across
  platforms, not per keyword or per platform. Replace the current min(8, keyword
  count) behavior, which normally produces5. Review/remove conflicting legacy
  12-session priority overrides and separate210-session Mae add-on; do not silently
  carry them into the new standard eight-run daily.
- [ ] Use the guide at
  `/Users/seolocalph/Downloads/Signal-AEO-8-Run-Daily-Prompt-Guide.html`.
- [ ] Eight types: direct service, best provider, local intent, problem-based,
  conversational, trust-based, comparison, brand verification.
- [ ] Three ChatGPT, three Gemini, two Copilot sessions per campaign/day.
  Perplexity is retired; replace guide references with Copilot.
- [ ] Rotate type/platform assignments over14days; distribute discovery coverage
  over each campaign's verified eligible keywords while preserving service,
  location and intent. Brand verification is business-level, not discovery.
- [ ] Discovery prompts1–7 must not name the business. Only brand verification
  names it; never count a prompted mention as a discovery ranking win.
- [ ] Add nullable prompt-type metadata to AEO Admin persistence, build-session
  API, job payloads, result ingestion and relevant reporting contracts.
- [ ] Historical records stay NULL/empty. No inferred backfill or relabeling.
- [ ] Preserve exact prompt, keyword/campaign identity, platform, date, session
  condition and result evidence. Keep daily and formal ranking measurement separate.
- [ ] Retain fresh-chat boundaries, no invented business claims, device125 exclusion,
  Copilot concurrency cap4, provider verification and retry/deduplication safeguards.

## 3. Test, then run September 9 daily

- [ ] Tests: eight slots with fewer than8keywords, three/three/two distribution,
 14-day coverage, campaign/location separation, no brand leakage in discovery,
  nullable historical metadata, API round trips, retries and resume idempotency.
- [ ] Dry-run actual campaign plans and inspect generated prompts/results.
- [ ] Bounded measured device test before running the full daily.
- [ ] Reconcile September9's already completed results before replanning. Preserve
  them with empty historical prompt types; do not fabricate classifications or
  blindly repeat completed jobs. Resolve any transition-policy ambiguity first.
- [ ] After ranking fix and new daily verification, execute September9 daily,
  monitor to completion, verify costs and consolidated deliverables.
- [ ] Update HANDOVER.md and commit scoped changes in both repositories.

Current September9 snapshot:1391regular daily jobs/265campaigns plus210Mae jobs;
267saved successes and1334remaining in the1601combined plan at the prior checkpoint.
Re-read actual results before execution; these are not a new run authorization count.
