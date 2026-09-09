# Eight-type daily — implementation checkpoint (NOT released)

User order: measured ranking fix first, then eight-type daily + AEO Admin,
then tests, then September9 execution. Stale ranking must not be restarted.

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
