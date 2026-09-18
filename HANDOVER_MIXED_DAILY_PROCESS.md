# Mixed Daily / Voice continuation handover

Paste this document into a fresh DeviceAgent session before doing work.

## Scope

Continue implementing the existing Daily pipeline as one mixed process:

- 8 jobs per campaign/location
- 5 `mode=type`
- 3 `mode=voice`
- Existing platform rotation remains ChatGPT/Gemini/Copilot
- Do not create a separate Voice scheduler

The current ranking/Daily processes are not running at handover creation time.

## Repository and commits

Repository: `/Users/seolocalph/projects/device-agent`

Branch: `feat/top3-deepdive-ranking-geo-fix`

Remote: `devicefarm1` → `DeviceFarm1/device-agent`

Latest pushed commits:

- `98d178b` — planner/browser routing/operations runbook
- `695978b` — voice executor routing
- `c1fb9e4` — voice proxy override for smoke tests
- `7b09731` — voice lease/handoff/idempotent retry fixes
- `32e3aeb` — bounded ranking retry supervisor
- `e76b999` — Copilot inconsistent-rank correction retry

Operations documentation:

- `OPERATIONS_RUNBOOK.md`

## Completed

### Planner

`daily_prompt_plan.py` now assigns deterministic modes:

- Voice: `local_intent`, `problem_based`, `conversational`
- Type: the other five prompt types

`validate_mixed_modes()` verifies 5 type + 3 voice. Planner tests pass.

Run:

```bash
python3 -m unittest tests.test_daily_prompt_plan tests.test_typed_daily_consolidation -q
```

### Browser routing

Typed jobs default to Chrome. Jobs can request `browser=edge`.

- Edge ChatGPT/Gemini routing is opt-in.
- Edge Copilot remains on its existing flow.
- Edge ChatGPT input/submit smoke passed on an idle test phone.
- Edge Gemini full-generation smoke passed.

### Voice executor

Local checkout:

`/Users/seolocalph/projects/voice-search`

The standalone executor is:

`/Users/seolocalph/projects/voice-search/agent/voice_agent.py`

Patched scrcpy audio client/server were built successfully. Scrcpy runs with
`--no-video`; it is used for audio injection, not screen display.

Standalone no-proxy ChatGPT voice smoke passed on device-125:

- Exact recognition passed
- Answer state was `complete`
- TTS audio trace was recorded

DeviceAgent now routes `mode=voice` through `voice_agent.py`, holds the shared
phone lease, and maps voice bundle status/exactness into the result row.

## Current blocker

The DeviceAgent voice adapter works in the no-proxy smoke path, but the
Evomi/GOST proxied voice adapter still hangs/fails in the voice proxy/bootstrap
path. Do not enable mixed production Daily until this is fixed.

The latest successful standalone voice result used phrase:

`Reply voice smoke okay only`

The first underscore phrase correctly failed exactness because speech converted
underscores to words.

## Dane Roofing ranking state

Client 328, campaign 501, five keywords, 15 platform jobs.

The complete manually verified consolidated file is:

`/Users/seolocalph/Desktop/Rankings/dane_roofing_ranking_consolidated_all_2026-09-19.csv`

It contains 15 deduplicated successful rows. The Copilot row was manually
verified from the current device-101 screenshot and is dated Sep 19 because it
was captured then; do not relabel it as Sep 18.

Copilot evidence:

`/Users/seolocalph/projects/aeo-appium/audit_results/2026-09-19/Copilot/kw5220_copilot_manual_corrected.png`

## Ranking retry behavior

`tools/retry_ranking_until_success.py` was added because direct
`run_ranking.py` does not provide an outer retry-until-success loop. The normal
wrapper is currently blocked by the ranking cost-release gate. The supervisor
must always receive an explicit `DATE`; otherwise the legacy runner defaults to
June 8.

Never use a partial API catalog. The Admin API timed out; the current ranking
snapshot was reconstructed from authorized RDS into `/tmp` snapshots.

## Next work, in order

1. Fix voice proxy ownership/handoff so the voice executor can run through the
   existing GOST/SocksDroid contract without duplicate tunnel management.
2. Add a focused integration test for a one-job voice plan and verify the durable
   bundle, exact recognition, `voice_trace`, and CSV fields.
3. Add mixed Daily consolidation fields and completion validation for exactly
   5 type + 3 voice successes.
4. Test one complete mixed 8-job campaign on idle phones only.
5. Only then enable the mixed planner in production Daily.

## Safety rules

- Do not deploy fleet-wide while voice proxy smoke is failing.
- Use disjoint phone pools for parallel Mac minis.
- Device-102/108/125 have known instability/exclusion history; verify before use.
- Preserve actual timestamps; never rewrite execution dates to make a batch appear
  historical.
- Sample/planned CSV rows must never be imported as successful execution.
- Do not weaken Copilot rank/list consistency validation to force success.
