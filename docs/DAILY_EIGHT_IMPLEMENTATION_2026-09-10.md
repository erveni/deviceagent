# Eight-type daily — deployed, September9 guarded run active

Live update06:26 Manila:API571811c deployed successfully; admin index-Bzp3LbO4.js
active; additive migration and16 campaign-location repairs applied. All265 campaign
GPS/timezones verified.15 focused daily Python tests plus typed consolidation test
and8 backend tests pass. Full workspace typecheck still has preexisting errors.

Three phone queries completed, actual screenshots checked and sessions147659–147661
imported with typed metadata. Copilot's brand check confused Yokl with another company;
this is a verification finding, not a verified recommendation or discovery win.
Settled smoke44.359568MB/3 (14.786523MB each) is NOT a low-cost fleet forecast.

Full Sep9 run now active:267 legacy credits+3 new successes leave1850 slots.
Supervisor PID48091, status `daily_release_20260910_sep09/report.json`.
8workers, Copilot cap4, devices108/125 excluded,8500MB admission budget,9000MB floor,
8hour admission deadline,3outer rounds/no nested retries. In-flight jobs/meter lag
can overshoot. It auto-consolidates/imports typed successes without timestamp rewriting
or legacy duplication. Partial runs stay partial; no silent budget reset/restart.
Stale ranking remains paused. The setup checkpoints below are historical.

User order: measured ranking fix first, then eight-type daily + AEO Admin,
then tests, then September9 execution. Stale ranking must not be restarted.

## Latest checkpoint (supersedes older counts and gates below)

- September9 legacy-credit policy is accepted and implemented. Fresh read-only
  catalog:265 campaigns,267 existing successes credited,1853 new jobs
  (687 ChatGPT,690 Gemini,476 Copilot). No plan written or phone jobs launched.
  Historical types stay NULL; credit manifests plus new slots must total8.
- Nine Python daily tests and eight backend tests pass. Backend tests exercise
  actual HTTP build and ingestion for all8 types against isolated PostgreSQL,
  duplicate200/conflict409 behavior and unchanged NULL historical metadata.
- API/admin bundles build. API typecheck comparison:64 preexisting/64 current
  errors, zero newly introduced;16 preexisting Zod barrel collisions remain.
- Lightweight daily-catalog endpoint avoids historical activity query timeouts.
  Typed imports use exact IDs; retries cannot replay the base wave and stop
  incomplete after3 rounds. Canonical build no longer starts old local LLM server.
- Nine parser fixes leave16 unresolved campaigns:457,277,389–402. Approval to
  verify/update their location data is unanswered. No production data changed.
- Remaining release gates: verify locations and GPS, migrate/deploy backend/admin,
  measured daily phone tests and full-run budget guard. No production deployment.
- Older sections below are initial-checkpoint history, not current launch counts.

## Implemented locally

- Canonical planner: exactly8 slots per real campaign/business pair, even with
  one keyword. Three ChatGPT, three Gemini, two Copilot;14-day type rotation.
- Eight guide types, seven unbranded discovery prompts, one separately marked
  brand-verification prompt. No backlink or follow-up injection in typed daily.
- Stable date/campaign/business/type slot IDs in jobs, CSV and retry identity.
  Partial retry plans are validated without requiring completed slots again.
- Old CSV headers are preserved; typed results cannot append to an old header.
- Typed daily skips Mae's old210-job add-on and legacy Copilot-slice remapping.
- Copilot concurrency cannot exceed4; existing device125 pool exclusion retained.
- Backend worktree: `/Users/seolocalph/projects/AEOAdmin-daily-eight`, branch
  `feat/daily-eight-prompt-types-20260910`. Nullable persistence, additive explicit
  migration, successful-slot uniqueness, API contracts/codegen and admin display.
  Original AEOAdmin worktree conflicts remain untouched.

## Verification so far

- Six Python tests pass (slot counts/rotation/retries/validation/real CSV writer).
- Seven backend tests pass, including in-memory PostgreSQL migration twice,
  unchanged NULL history and deduplicated successful slots.
- Backend bundle builds. Full workspace typecheck is NOT green: generated Zod
  barrel name collisions and Express parameter typing errors need triage;
  do not equate a bundle build with complete type safety.
- Cached-catalog dry-run:273 groups/2184 slots (819/819/546). No plan file or phone
  work created. This cache is NOT the production launch scope.
- Live database READ ONLY preview:1558 active keywords/265 campaigns;
 1428 keyword contexts render all eight types.25 campaign locations fail safe
  validation. No database values changed. Initial query using keyword.status
  instead of is_active returned1 keyword and was corrected; discard that sample.
- Campaign searchAddress takes precedence over headquarters city/state. Incomplete
  or ambiguous geography fails closed rather than silently targeting another city.

## Release gates still OPEN

1. Resolve/verify location context for campaign IDs76,90,98,152,159,457,492,277,
   389,390,391,392,393,394,280,281,395,396,397,398,399,400,401,402,359.
   Some only lack commas; others omit city/state or have ambiguous neighborhood
   labels. Do not invent data or silently omit their eight jobs. Also verify
   campaign mock-GPS coordinates versus business headquarters before dispatch.
2. Refresh catalog and reconcile active campaign eligibility (cached273 versus
   live265). Validate backend endpoint round trips, typed CSV/API import exact IDs,
   and reporting behavior. Brand verification must not become a discovery win.
3. Fix/triage full typecheck, build admin UI, review generated changes, migrate
   additive database columns BEFORE deploying API code that selects them.
   Migration has NOT run against production; backend/admin NOT deployed.
   Existing `_build_server_lib.sh` still targets original AEOAdmin, not worktree.
4. Resolve September9 transition:267 old successes have no prompt type. User has
   been asked whether to credit them toward8 (recommended) or run8 new types
   additionally. No answer yet. Builder blocks historical-success dates rather
   than making that choice or fabricating labels. Reconciliation not implemented.
5. Guard resumed base runs against replay, agree bounded retries/budget, perform
   measured new-daily phone samples, inspect outputs, then launch approved
   September9 remaining work under fleet lock and monitor through import.

No new daily phone samples or full run have started. Do not describe this checkpoint
as a production rollout. Ranking Copilot savings remain a two-success104-only pilot;
see `COPILOT_BANDWIDTH_WIFI_2026-09-10.md` for settled meter evidence.
