# Session Handover — 2026-09-07 10:45 PST

## Current user-approved order — September10

### Latest daily release checkpoint (supersedes earlier blockers below)

**LIVE Sep9 daily started06:26 Manila, September10.** Supervisor PID48091,
`daily_release_20260910_sep09/report.json`; launcher.log in same directory;
worker log `/private/tmp/daily_auto_2026-09-09.log`. Eight workers actually started
on1850 remaining slots.267 legacy credits+3 smoke successes already counted.
Actual run overrides:8500MB admission budget,9000MB floor,8hour admission deadline,
3outer rounds/no nested retries/Copilot cap4/devices108&125 excluded. Meter baseline
29698.300338MB. Do NOT start ranking, a second daily, or edit active runtime modules.
The supervisor automatically consolidates typed successes and imports via API;
budget/deadline/exhausted retries mean partial-stopped, never false complete.
Immutable Bash snapshots are in the release directory. No unattended queue restart.

Deployment SUCCEEDED:AppRunner operationd4d1c465975e481fb71ee3c25ce79820 ended06:08:21;
API commit571811c, latest backend source/importer d8f80d8. Admin index-Bzp3LbO4.js
live, CloudFront invalidation I4C358BKBHA2SR63HHROG3OYZ2 completed. Additive migration
and16 location repairs applied; all265 GPS/timezones verified. Three daily smoke
queries completed and screenshots root-reviewed. Copilot brand verification confused
Yokl with another company: retain this finding; is_discovery=false, NOT a verified
recommendation. DB session IDs147659/147660/147661 imported successfully, types/flags
checked read-only. Slot date isSep9; pg Date JSON timezone serialization is not a
change to the SQL date. No historical types overwritten or legacy rows re-imported.

Smoke settled44.359568MB/3 =14.786523MB/job, not proof of low-cost daily. Evidence:
daily_eight_smoke_20260910/settled.json. Account-wide meter, delayed deductions;
do not allocate billed bytes by interim platform readings or extrapolate3jobs.
Full run may hit8.5GB guard before finishing; report actual remaining, do not refill
budget/restart automatically. Ranking efficient fleet rollout STILL incomplete.

The following setup checkpoints are historical and superseded by this live state.

- User approved verifying/completing the16 location settings and asked to push/run.
  All16 campaign search_address repairs APPLIED atomically with exact-before checks.
  Backup:/tmp/daily-location-repair-20260910-before.json. No historical sessions edited.
  Fresh preview:1558/1558 keywords across265 campaigns pass location rendering.
- Found/fixed new planner HQ-GPS fallback. All265 campaigns now resolve through
  daily_city_geo.json (156 city/state keys), including polygon-derived timezone.
  This is city-level GPS, not street-level precision. No paid proxy geocoding.
  OSM attribution/ODbL retained; one-time lookup evidence /tmp/daily-city-geo-20260910.jsonl.
- Additive production daily columns/index migration COMPLETE. Backend571811c pushed;
  deployment GitHub run34409776482 is still IN_PROGRESS (AppRunner operation
  d4d1c465975e481fb71ee3c25ce79820). Verify completion + JSON capability before jobs.
- Admin assets uploaded, index NOT switched yet. Previous index backup:
  /tmp/aeo-admin-index-before-daily-20260910.html. No old assets deleted.
- New admission budget guard:typed daily requires Evomi ledger; runner defaults
  12000MB budget,9000MB floor, no nested retries. Existing in-flight jobs finish;
  meter lag/flight traffic can overshoot. Stops on meter failure; never resets
  baseline between retry rounds. devices108/125 excluded.15 daily Python tests pass.
- NEXT: verify deployed API, switch admin index/invalidate, build NEW Sep9 eight-v1
  plan via tools/build_daily_release.py with267 legacy credits; three-platform
  single-phone/zero-retry smoke under100MB guard; verify meter/results before full
 1853-job remaining launch. No daily phone work started at this checkpoint.
- Stale ranking STILL PAUSED; efficient ranking fleet rollout still incomplete.

- UPDATE latest user: proceed with daily; next ranking must use efficient usage.
  Sep9 legacy-credit recommendation accepted. Fresh READ ONLY DB snapshot in
  `/tmp/aeo-daily-catalog-20260910-0442`:265 campaigns,267 credits,1853 new jobs
  (690Gemini/687ChatGPT/476Copilot). No production plan written or jobs launched.
  Transition manifest preserves historical NULL types; new+credited quota is8.
- Ranking normal launcher now FAILS CLOSED in `tools/ranking_cost_release.py`
  until rollout is released; metered zero-retry harnesses only. This does NOT
  mean efficient mode is deployed. Keep stale queue paused. Copilot cap4 clamped.
- Copilot106/v86 measured comparison completed at3.133920MB/0success. Offline
  preparation13.440309MB,154.7s,71.7squiet. Native log says Network issues after1s,
  but generic result said generation timeout. Root viewed post-job PNG (prompt
  and spinner, no answer); later idle XML had no Network issues text. This does
  not prove the earlier message was false. No retry occurred in that sample.
  Wrapper rollback hit ADB timeout; direct HTTP /adb/rearm recovered wireless
  debugging (previous0), then `tools/restore_copilot_trial.py` restored original79,
  accessibility/noVPN verified in attempt4_wrapper/recovery.json.
- COMPLETED phone work for follow-up:106/v87, prefix
  `copilot_bootstrap_wifi_20260910_device-106_attempt5_{wrapper,metered}`.
  Native87 confirms exact visible Network issues for3s only on prepared audit;
  error namedcopilot_network_issues instead oftimeout. Daily native path unchanged.
  One5225 job/no retries/30MBguard, fresh full reset/WiFi settlement, reused verified
  unchanged settled meter baseline29746.471228. Valid native PNG reviewed:1/8,
  no prompt leak. Original79/accessibility/noVPN automatically restored.
  Launcher exited2 AFTER success (shell parse error; current bash -n passes).
  Likely script edited while Bash was reading it. Harness now saves/checks an
  immutable launcher copy, settles spent traffic before reporting launcher error,
  and wrapper exits nonzero on errors. No repeat paid job for this bookkeeping bug.
  Original meter report remains invalid; recovered_settlement.json is SETTLED:
  before29746.471228 minus after29745.815882 =0.655346MB,1row/1success.
  Recovery waited5min with16stable readings and no local competing workload;
  no extra paid job. Account-wide attribution caveat remains. Pushed code2462895;
  backend e4d9e48 on its daily-eight feature branch. Neither is a production rollout.
  No Network issues guard event occurred on success; do not claim causal proof.
- Daily backend: eight real HTTP build+ingest round trips pass against isolated
  PostgreSQL, duplicates200/conflicts409/historyNULL. Admin/API bundles build.
  Typecheck comparison:64 baseline/64current API errors, none new (same installed
  dependencies); whole workspace is NOT green. Removed newly introduced Zod name
  collision through generator config;16older barrel collisions remain.
  Lightweight daily-catalog endpoint avoids slow historical activity queries.
  Old keyword GET timed out on both App Runner and CloudFront; partial snapshot
  folders must not be used. No backend deploy/migration yet; Docker daemon off.
- Nine address parsing fixes reduce unresolved campaigns25→16:457,277,389–402.
  Async permission request to complete these location settings remains unanswered.
  Do not infer LehiUT for VoiceDepot campaigns nationwide. No campaign data changed.
  Daily now skips stale local LLM build server, validates quotas before dispatch,
  always resumes typed slots, disables nested retries, defaults3rounds, returns
  incomplete rather than success when retries exhaust. Never delete old results.

- DAILY IMPLEMENTATION CHECKPOINT: local source and13 focused tests now present;
  API bundle builds, but NOT deployed/migrated or phone-tested. See
  `docs/DAILY_EIGHT_IMPLEMENTATION_2026-09-10.md` for exact release gates.
  Live READ ONLY preview:265 campaigns,1558 active keywords;25 campaign locations
  need verification. Cached273-group dry-run is not the launch count. Sep9 old
  successes must be reconciled; builder blocks silently purchasing8 extra runs.
  Daily/stale remain paused. Do not treat this checkpoint as production ready.

- AUTHORITATIVE UPDATE03:16: Wi-Fi-settled Copilot pilot VERIFIED2/2 automatic
  successes1/8, both PNGs root-reviewed, settled Evomi0.629016 and0.540893MB.
  Previous successful traced control19.652356MB; mean0.584955MB (~97% reduction).
  Both wrappers COMPLETE, original79/accessibility/noVPN restored; no active test.
  Hostsource/docs committed; defaultOFF and104only, NOT fleet-wide deployment.
  Cause supported by measured14.87/14.54MB Wi-Fi bursts before paid proxy; earlier
  paid proxy sessions transferred14MB. Same proxy duration, not just shorter wait.
- NOW proceeding with daily8/backend implementation, as user ordered. AEOAdmin
  worktree `/Users/seolocalph/projects/AEOAdmin-daily-eight`, branch
  `feat/daily-eight-prompt-types-20260910` from refreshedorigin/main. Original
  AEOAdmin stale .env/.gitignore conflicts and other changes preserved untouched.
  Daily/stale queues STILL PAUSED. Sep9legacy-credit choice still unanswered.

- UPDATE03:00: WiFi-settled pilot SUCCESS1/8, actual PNG root-verified (top3/rank/
  summary, prompt absent). Offline wlan0 transferred14.874494MB over154s with51.2s
  quiet; paid Gost cumulative0.404801MB. Evomi currently0.629016MB vs traced
  predecessor19.652356MB. Meter still finishing five-minute post window; do NOT
  launch confirmation until report complete and original79/noVPN restored.
  Active prefix copilot_bootstrap_wifi_20260910_{wrapper,metered}.
- NEXT after settlement/rollback: same wrapper flags plus COPILOT_WIFI_CONFIRM=1;
  prefix copilot_bootstrap_wifi_confirm_20260910_{wrapper,metered}. Same fix, same
  single5225/104, no retries,30MB guard, fresh cleared Edge each run. This repeats
  the measurement rather than generalizing from one cheap sample. No live rollout.
  Preparation exceptions now release pool reservation before aborting the isolated
  job. Daily/backend still queued; legacy-count question remains unanswered.

- UPDATE02:47: traced confirmation generated SUCCESS1/8 with nativePNG; root
  visually verified top3/rank/summary, no prompt leak. Final local traffic14.073361MB:
  HTTP:80 without hostname11.734250MB, edge.microsoft.com1.943364MB,
  copilot.microsoft.com0.084736MB. HTTP Host parser added for NEXT trace (current
  process only labels TLS SNI). Therefore large background HTTP transfer dominates;
  exact HTTP hostname not yet established. Do not claim it is MSN/news based on UI.
  Meter after still settling (~19.652356MB deduction), wrapper then restores79.
- NEXT PREPARED, NOT LAUNCHED: add COPILOT_BOOTSTRAP_SETTLE=1 to traced wrapper
  command below. Prefix copilot_bootstrap_wifi_20260910_{wrapper,metered}. Uses
  previous traced report ONLY after settled/rollback. Same104/86/5225/30MB/no retry.
  One changed behavior: after offline full reset, wait >=150s and >=30s without
  bulk WiFi traffic (>16KB/5s), max300s; fail closed before paid proxy if busy.
  Records actual wlan0 RX+TX deltas, submits zero AI prompts during preparation.
  This shifts downloads to ordinary WiFi, does NOT reduce total internet usage.
  No update/security endpoints blocked. Defaults remainOFF.12Copilot+4observer tests pass.
- Daily remains queued; Sep9 recheck270rows/267success/3errors. User asked through
  async question whether267legacy successes count toward8 (recommended) or eight
  new types are additional. No reply yet; don't invent historical prompt types.
  AEOAdmin has pre-existing unresolved .env/.gitignore conflicts: do not resolve
  or commit secrets; no backend source edits yet.

- UPDATE02:31: automatic bootstrap confirmation COMPLETE, **19.302452 MB**;
  NOT a confirmed saving. Native answer1/8 valid but nativePNG missing; recovered
  actual same screen locally (candidate/recovered_screen.png), raw CSV unchanged.
  Original79/accessibility/noVPN restored. Full cumulative Gost metrics14.035936MB;
  terminal-only ledger0.426021MB missed open connections. Most transfer occurred
  during Copilot, not preflight; inspect cumulative counters, never sum snapshots.
- ACTIVE ONE diagnostic: COPILOT_BOOTSTRAP_TRIAL=1 COPILOT_BOOTSTRAP_CONFIRM=1
  COPILOT_TRAFFIC_CONFIRM=1 python3 -u tools/copilot_cache_trial.py. Output prefix
  copilot_bootstrap_trace_20260910_{wrapper,metered};104only/86/30MB/no retries.
  Passive SOCKS forwarding records hostname/port/cumulative counts (no payload or
  credentials, no DNS/SNI rewrite), to locate large download bursts. Fresh meter
  baseline, automatic original79 rollback. Native-null screenshot fallback now
  scoped to inline104/Copilot and same idle framed answer with strict rankOCR.
  All trial flags defaultOFF; no daily/backend rollout. Await measured result.

- UPDATE02:15: first off-proxy FULL Edge bootstrap SUCCESS1/8, root reviewedPNG;
  settled0.513867MB vspriorfull-reset paid12.727877MB (~96%less Evomi thissample).
  Manualforegroundassistance disclosed; notfullyautomatic.79rollback verified.
- ACTIVE automatic confirmation: COPILOT_BOOTSTRAP_TRIAL=1 COPILOT_BOOTSTRAP_CONFIRM=1
  python3 -u tools/copilot_cache_trial.py; outputs copilot_bootstrap_auto_20260910_*
  (wrapper/metered). Candidate86,1job5225/104/30MB/no retries. Now dispatcher
  RANK_COPILOT_OFFLINE_BOOTSTRAP=1 runs fullpmclear/native reset-only BEFOREgost,
  provesoffline/nogeneration, thennativecopilotEdgePrepared skipsduplicatepaidreset.
  Explicitforegrounding included. AllflagsdefaultOFF; otherdevices/daily unchanged.
  NineCopilot tests pass. Await automaticactualPNG/settledmeter/79rollback.
  Do NOT promote failedcache85path. Newapproach shiftsstartuptraffic toWiFi,
  not proof of smaller totalnetwork traffic. Daily/backend remain queued.

- UPDATE02:08: ACTIVE bootstrap86 test, copilot_bootstrap_one_20260910_wrapper/
  metered. Offline FULL reset readiness55s passed; baseline29790.243732MB.
  Root manuallyforegrounded Edge duringproxywarmup afterchecking nativeidle;
  needed becausepreparedpath skippedreset's launch. manual_assist.json discloses
  this; hostcode nowautomatesforegroundforfuturetest. Do not callfullyautomatic.
  Await actualresponse/screenshot/settledmeter/original79rollback. Dailyqueuedonly.

See TODO-ranking-and-daily-2026-09-10.md. Finish/measure ranking bandwidth fix
FIRST; then implement guide's eight daily prompt types, exactly8sessions per
campaign,3ChatGPT/3Gemini/2Copilot,14-day distribution, in device-agent AND AEO
Admin backend. Historical prompt types stay empty/null. Test before executing
September9 daily, preserving completed results and resolving transition counts.
No daily launch yet. YOKL15results alreadydelivered; Copilot savings unresolved.
Last cache trial v5 settled12.088494MB/0success; wrapper restored79/accessibility/
noVPN. Bootstrap86 alternative prepared, not yet run. Earlier ACTIVE notes stale.

## Sep10 — Copilot bandwidth fix requested; ONE cache trial active

- UPDATE01:56: v5 offline reset PASS38s then paidreset PASS38s, but openCopilot
  sign-in sheet swipes twice and failed31s.0answers. Meter STILL SETTLING with
  large late deductions (~12MB as oflastreading). Do NOT claim cache savings.
- Cache-preserving path NOT promoted. Candidate86/0.9.69-copilot-bootstrap-trial
  nowbuilt. Alternative experiment retains FULL Edge pmclear+native reset but
  performs setup OFFPROXY, then a single-use86/104/5225 receipt allows skipping
  duplicatepaidreset. Actual Copilot opening/generation stays on Evomi.
  This shifts startup downloads toWiFi; NOT proof of reduced totalnetwork bytes.
- PREPARED NOTSTARTED: COPILOT_BOOTSTRAP_TRIAL=1 python3 -u tools/copilot_cache_trial.py
  Outputs copilot_bootstrap_one_20260910_wrapper/metered. Requires v5 complete,
  original79rollback, offlinefullresetproof;30MB/1attempt/10min/no retries.
  NativecopilotEdgePrepared defaultfalse, all daily/fleet defaults unchanged.

- UPDATE01:46: v4 failed reset18s/no submit; logcat shows Edge background role
  activity launch blocked, phone on launcher. OFFPROXY explicit amstart Main
  brought normalEdge toolbar back. Provisional0.126629MB; v4 meter settling.
- v5 PREPARED: hostforce-stop thenexplicit amstart Edge/Main+3s. New native
  audit-only copilotCacheResetOnly stops immediately afterreset; wrapper must
  pass this OFFPROXY/0prompts readiness before any metered job. Same85 withAPKhash.
  Output copilot_cache_one_20260910_v5_wrapper/metered. Waitv4complete/rollback,
  thenrun tools/copilot_cache_trial.py, not whilev4wrapper stillactive.

- UPDATE01:41: v3 COMPLETE0.330991MB/0success (resetfailed,no submit),79rollback
  verified. ACTIVE v4 copilot_cache_one_20260910_v4_wrapper/metered, one5225,
  processrestart+personalizationNotnow+strictcache reset/freshchat. No success yet.

- UPDATE01:37: v3 failed reset_edge16s BEFORE submit. Root inspected live XML and
  screenshot: actual blocker is "Personalize your web experience" popup, NOT old
  Copilot panel. Root declined exactNotnow OFFPROXY and verified menu reachable.
  Native85 now handles this exactpopup onlyin cachetrial; rebuilt/tested.
- v3 meter settling (~0.331MB); original wrapper will restore79. v4 PREPARED
  NOTSTARTED, updated popupguard + prior processrestart; onejob/30MB. Reuse v3
  finalbaseline after settlement/rollback. New output copilot_cache_one_20260910_v4_*.
  Newwrapper records candidateAPK SHA256 as source85 has test revisions.

- UPDATE01:33: v2 meter COMPLETE0.478956MB/0success,79rollback/accessibility/noVPN
  verified. ACTIVE NOW v3 wrapper/meter (copilot_cache_one_20260910_v3_*), one5225,
  same85/cache settings + pre-reset Edge process force-stop, no data wipe.
  Await actual answer/screenshot and settled meter. No successful savings yet.

- UPDATE01:29: v2 cache reset34s/open8s/fresh conversation2s allPASSED; submitted
  once, failed after6s with Network issues. Root saved/viewed failed_screen.png;
  no answer, not a success. Provisional0.127097MB; meter still settling, wrapper
  will restore79 afterward. SocksDroid stopped manually once Gost/job finished.
- v3 PREPARED NOT STARTED: same85/cache reset, host additionally force-stops old
  Edge process BEFORE native reset so old embedded Copilot heap cannot survive.
  This is a hypothesis test, not an established cause. Reuses v2 finalbaseline
  only after settledcomplete/79rollback. New v3 wrapper/meter output names.

- UPDATE01:18: first wrapper stopped BEFORE any proxy job: reused baseline was
  older than15min. Original79 restored/accessibilitytrue/noVPN, no paid attempt.
  ACTIVE fresh-baseline rerun outputs copilot_cache_one_20260910_v2_wrapper and
  copilot_cache_one_20260910_v2_metered. No baseline reuse; wait full settlement.
  Existing non-v2 directories are failed preflight evidence, not a paid sample.

- YOKL delivery remains complete15/15. User now asks to fix Copilot bandwidth.
- ACTIVE wrapper tools/copilot_cache_trial.py, output copilot_cache_one_20260910_wrapper;
  meter copilot_cache_one_20260910_metered. One104, exact5225 comparison ONLY,
  ZIP-first, notification denial, no retries,30MB guard/10min plus meter settlement.
  Not a report replacement; do not merge into YOKL export or rerun completed queue.
- Candidate85/0.9.68-copilot-cache-trial: opt-in audit copilotCacheTrial only.
  Host skips pm-clear only104/singleattempt/85. Native UI verifies All time,
  history/cookies/tabs ON, cached files/passwords/autofill/site settings OFF;
  no full-wipe fallback. Opens New chat and checks empty composer/no old rank or
  prompt before submit. Default daily/fleet reset unchanged, cap4 unchanged.
- Edge CDP /json/version identifies com.microsoft.emmx, but embedded Copilot not
  exposed as target. Do not claim Chrome CDP identity cleanup covers this surface.
  Device Edge UI inspected offline; original saved answer remains in finalreport.
- Wrapper installs85 only104 and restores original79/accessibility/noVPN in finally.
  Check wrapper restore_error and meter completion before claiming savings.
  Prior same-keyword full-reset successful baseline12.727877MB, warm retained state;
  one comparison cannot prove fleet-wide reliability or cold-cache savings.
- Build85 and host compile pass; ongoing test requires real screenshot review.
  Keep daily/stale paused. No commercial toolkit skills applied.

## Sep10 00:56 — YOKL COMPLETE: 15/15 accepted; no ranking running

This completion supersedes all ACTIVE/PREPARED YOKL notes below.

- Five keywords each on ChatGPT, Gemini and Copilot. All15 actual screenshots
  visually checked.12 automatic successes plus3 explicitly reviewed/recovered
  ChatGPT captures; original failed CSV rows remain unchanged. Do not rerun them.
- Final Copilot5225 retry succeeded1/8, settled12.727877MB. Previous three-job
  batch44.021083MB included failed5225; both costs preserved, no hidden retries.
- Final local report: /Users/seolocalph/Desktop/Rankings/Yokl_initial_2026-09-10/index.html
  Alongside rankings.csv,15PNGs,attempts.json,bandwidth.json. Verified15unique
  accepted rows,15images and every HTML link. No backend upload/backdating.
- Full measured YOKL total210.080601MB, including old interrupted mixed run
  109.547768MB. Follow-up work100.532833MB delivered14missing results.
  Gemini5=21.698169MB (4.339634MB/result); ChatGPT5=4.916596MB
  (0.983319MB/delivered result, includes review/recovery, not5automatic).
  New Copilot4=73.918068MB including2failed attempts (18.479517MB/result).
  Earlier successful Copilot5221 cost cannot be isolated from mixed run.
  Warm-cache one-phone samples do NOT establish fleet-wide/cold-cache savings;
  Copilot cache policy unchanged and remains the heavier workflow.
- Device104: original79/accessibilitytrue/idle; SocksDroid force-stopped;
  exact tun0 interface absent. Cleared Edge notification USER_FIXED only;
  normal denied USER_SET retained. No Edge data clearing after final capture.
- Completed test LaunchAgents disabled, including finalretry0910. Dailyfull
  confirmed not running; stale chain still held. Do not resume either implicitly.
- All new source/tools in device-agent on feat/top3-deepdive-ranking-geo-fix.
  Legacy runtime screenshot sources remain in aeo-appium, final copies on Desktop.
  No commercial toolkit skills applied (trial client-use restriction).

## Sep10 00:44 — YOKL final Copilot capture failed; one bounded retry prepared

- UPDATE00:47: three-job meter COMPLETE44.021083MB/2automatic successes.
  ACTIVE NOW com.deviceagent.yoklcopilotfinalretry0910, exact5225, new output
  yokl_copilot_final_retry_20260910_metered. Baseline29815.996679MB reused only
  if rechecked unchanged. Three-job LaunchAgent disabled. No other ranking runs.
  Check final retry screenshot and settled meter, then clean104notification
  USER_FIXED, stop lingering SocksDroid, disable retrylabel, export15ifaccepted.

- ChatGPT5/Gemini5/Copilot4 =14/15 verified. Root viewed Copilot5223=40/40,
  5224=1/5. Final5225 raw ocr_no_answer, no rank, screenshot says Unable to reach
  Copilot. Native read_answer OK was not proof of a valid answer; frame_shot failed.
- Three-job meter still settling (~44MB); no jobs/Gost active,104SocksDroid stopped.
- Prepared NOT STARTED com.deviceagent.yoklcopilotfinalretry0910, exact5225 only,
  original79/104/ZIP-first/notification guard,30MB guard/10min/no automatic retries.
  Gate requires completed three-job meter below60MB and exact two successes plus
  failed5225. Reuse settled three-job baseline; never rerun14accepted results.
- After settlement start prepared final retry, inspect actual PNG and final meter.
  Final export includes this retry's cost. Daily/fullstale remain paused.

## 2026-09-09 late — YOKL ChatGPT and Copilot now authorized; first ChatGPT test active

- UPDATE Sep10 00:30:58: retryCopilot meterCOMPLETE12.728773MB/1success2/3;
  plusfirstfailed4.440335MB =17.169108MB for this newlydeliveredkeyword sofar.
- ACTIVE NOW com.deviceagent.yoklcopilotthree0909, exact5223–5225,104/original79,
  ZIP-first+verifiedpostresetnotificationdenial,1worker,noretries,100MBguard/25min.
  Reuses settledretrybaseline29860.017762MB. Inspect yokl_copilot_three_20260909.log
  and *_metered/report.json. Rootmustviewall3savedPNGs and finalmeterbeforeexport.
  Retrylabeldisabled.12/15usable now; previousChatGPT/Gemini complete, doNOTrerun.
  Atfinal stop104SocksDroid, clear onlynotificationUSER_FIXED,testlaunchlabeldisable,
  verify79/idle/noVPN, exporttools/export_yokl_merged.py --output NEWDesktopfolder.
  Daily/fullstaleheld; nobackendupload. No commercialtoolkitskills used.

- UPDATE Sep10 00:26: retryCopilot5222 SUCCESS2/3. Root viewed fulltop3/rank/summary
  withshopyokl.com citation/no prompt. Native reset completed, postresetnotification
  denialverified, generation6s,read14s. Firstfailedattempt4.440335MB remainscost.
  Retrymeter nowsettling; no finalizedretrycostyet.12/15usable; last3Copilot pending.
  WaitretryreportCOMPLETE +cost<30MB, thenstartpreparedcom.deviceagent.yoklcopilotthree0909.
  No newAPK; original79 throughoutCopilot. Clear104notificationUSER_FIXEDatfinal
  cleanup (retainnormaldeniedUSER_SET), no otherphonepermissions touched.

- UPDATE Sep10around00:23: firstCopilot5222 FAILED networkissues,0answers; final
  meter29877.186870->29872.746535 =4.440335MB. Root savedfailedscreen showinglate
  Androidnotificationdialog aftersubmit. DismissedDon'tallow; underlyingCopilot
  reportsNetworkissues,noanswerrecoverable. Not claimingpopupsolecause.
- Offline104diagnostic proved pmclear erasesUSER_FIXED notificationflags. Explicit
  test-only hostguard nowdeniesnotifications afterhostclear AND reappliesvia2s
  asyncprogresshook once native reset_edge succeeds. NoAPKchange; original79.
  Restore normalpermissionbehavior at end by clearingUSER_FIXED flag on104.
- ACTIVE com.deviceagent.yoklcopilotretry0910: exactlyONEretry5222, newoutput
  yokl_copilot_retry_20260910_metered,log yokl_copilot_retry_20260910.log. Requires
  settledfailedfirst<30MB;100MBguard/noinnerorouterretries. Restores ZIP-first
  targetingusedbyoldsuccessfulYOKLCopilot; also suppresseslatepermissionprompt.
  This is delivery repair withtwocorrections,notisolatedcausalsavingsproof.
- Three-keywordcontinuation now requires success<30MB fromretryreport and reuses
  retryfinalbaseline. SameZIP-first/notificationguard. Preparedlabel
  com.deviceagent.yoklcopilotthree0909 STILLNOTLOADED. Do not runit before retry
  settles androotreviewsPNG. OriginalfirstCopilotlabeldisabled.11/15usable remain.

- UPDATE Sep10 00:11:15 ChatGPTfour meterCOMPLETE3.422797MB; first+four total
  4.916596MB/5delivered =0.9833192MB/delivery. Only2automatic successes;3other
  accepted through explicitreview/recovery, no paidretries. Wrappercomplete
  restored79/accessibilitytrue/noVPN. Detailed ANALYSIS.md in fourmeterdirectory.
- ACTIVE NOW com.deviceagent.yoklcopilotone0909, original79/104, exact5222.
  See yokl_copilot_one_20260909.log and *_metered/report.json. Reuses freshGPTfour
  settledbaseline29877.186870MB if unchanged. EdgepmclearON,1worker,singleattempt,
  100MBguard. No Copilot cache change or savings claim. ChatGPTfour label disabled.
  After1Copilot success<30MB + settledmeter/rootPNGreview, launchprepared
  com.deviceagent.yoklcopilotthree0909 for5223–5225. Daily/fullchainstillheld.

- UPDATE Sep10 00:06: ChatGPTfour ALL4attempts finished.2automatic successes
  (5222=2/2,5225=1/8),2explicitreviewacceptances(5223=1/6,5224=1/3). Root viewed
  everyPNG. With first5221recovered1/8, ALL5ChatGPT nowusable; no paidretries.
  TotalYOKL11/15usable; remaining4Copilot5222–5225 only. Four-runmeter settling,
  provisional3.383635MB. Wait *_metered/report complete + *_direct/report restored79
  before launching Copilotone. Do not rerun any ChatGPT based on raw failed rows:
  explicitreview/recovery receipts are authoritative for delivery, rawCSV preserved.

- UPDATE Sep10around00:05: ChatGPTfour stillactive,last5225inflight. Raw5222success
  2/2;5223ocr_no_answer1/6;5224ocr_no_answer1/3. Root viewed5223originalnativePNG:
  fulltop3/rank/summary,noprompt,exactOCRpasses; accepted savedcapture WITHOUT
  newimage/job. Reject was0.0084CSS-pixel geometry drift; code nowallows<=1/16CSSpx
  only, stillrejects1px/textchange; not loaded into alreadyrunningfourworker.
- 5224browserclip fullypassedcapture/OCR; nameconsistency falsely rejects listed
  "Yokl Food Tours" versus"Yokl, Inc.". Root verified officialyokltours.com food
  tours/contact pages linkingHello@shopyokl.com and reviewedcomplete1/3shot.
  Reviewed captures in *_metered/reviewed_captures.json withSHA256, rawCSV unchanged.
  Export merges explicitreviewrecords; no globalmatcher/DBalias changed.10usable
  of15sofar:5Gemini,4ChatGPT(includesrecovery+2reviewacceptances),1Copilot.

- UPDATE23:50:37: firstChatGPT meter COMPLETE,29882.103466->29880.609667,
  1.493799MB. Raw0automatic/1row; oneusable1/8afterdocumentedfree recovery.
  Wrappercomplete restored79/accessibilitytrue/noVPN. FirstLaunchAgent disabled.
- ACTIVE now com.deviceagent.yoklchatgptfour0909 (launched23:50): newdirect5222
  readiness then4paidremaining5222–5225. Inspect yokl_chatgpt_four_20260909.log,
  *_direct/report.json, *_metered/report.json. Finalmeter/rollback stillpending.
- Copilot1 and3 launchers prepared/notloaded. Start one ONLY afterGPTfour final
  meter+rollback/rootreview, reusing unchangedfreshGPTfourbaseline; then3requires
  first5222Copilot complete1success<30MB. Remaining3 reusefirstCopilotfinalbaseline.
  Outputs yokl_copilot_one_20260909_metered, yokl_copilot_three_20260909_metered.
  Never resume daily/fullstale; never re-run6originalsuccesses or recoveredGPT5221.

- Paid ChatGPT5221 completed with real1/8 answer, raw ocr_no_answer because
  capture moved during screenshot. No paid retry. Proxy/Gost finished; root
  stopped lingering104SocksDroid before local same-answer recovery (no newprompt,
  reload,navigation). Root viewed recovered_kw5221.png:fulltop3/rank/summary,
  no prompt. recovery.json records explicitmanualrecovery + SHA256; rawCSV stays
  failed. Current7acceptedYOKL pairs includes this recovery, not7automatic.
- Added3stable geometry observations beforeChatGPT capture; recovered SAMEpaid
  answer passed newhostcode. ChatGPTtrial now skips oldCDP fallback on proof
  failure (it cost extra proxy time and freezes JS); persists proofdiagnostics.
  Firstsettlement ongoingasof23:48,provisional1.493799MB/oneDELIVEREDcapture,
  zeroautomatic successes. Do not call finaluntilmetercomplete+79rollback.
- Follow-up gate accepts explicitreviewed/hashverified same-paid-answer recovery
  matched to rawrow plus settled<15MB + rollback; stillrequiresfreshdirectproof
  beforefourremainingpaidjobs. Mergeexport labels recovery and preservesrawrow.

- Fresh ChatGPT direct check PASSED automatically (103s); root viewed its full
  real answer clip1/3 with map + top3 + summary, no prompt. Baseline started
  23:34:13Manila,29882.103466MB. No paid row as of23:39; await meter supervisor.
- Follow-up now PREPARED, not launched: --chatgpt-cache --chatgpt-followup,
  com.deviceagent.yoklchatgptfour0909, remaining5222–5225. Requires completed
  exact5221ChatGPT success below15MB and original79/accessibility/noVPN rollback.
  Same100MBguard/25min, one104, no retries. Reuses first settled meter only when
  fresh and rechecked unchanged. No duplicate5221 or Gemini captures.
- tools/export_yokl_merged.py --output NEW_DIRECTORY merges the explicit paid run
  directories into15-pair CSV, PNGs and team-readable index.html; default refuses
  incomplete15. --allow-partial labels missing pairs Pending. Includes old
  interrupted-run109.547768MB via settled-boundary difference, not just newcache
  costs. Not yet executed; no completed report claimed. Copilot remaining-three
  expected output yokl_copilot_three_20260909_metered after first5222 measurement.

- User requests all missing ChatGPT/Copilot YOKL results. Preserve5Gemini and
  kw5221Copilot already accepted. Daily/fullchain remain held. Toolkit skills not
  used (client-use trial restriction); independent work continues.
- ACTIVE com.deviceagent.yoklchatgptone0909: direct_audit_smoke.py --chatgpt-cache,
  output yokl_chatgpt_one_20260909_direct, paid yokl_chatgpt_one_20260909_metered,
  log yokl_chatgpt_one_20260909.log. Direct readiness then exactly1paid5221ChatGPT,
  device104/v84, cacheON, singleattempt,100MBguard,10GBreserve, original79rollback.
  DO NOT relaunch or duplicate. Direct/paid completion and actual screenshot still
  require review; no measured ChatGPT savings yet. Source84 is test-only.
- First direct attempt rejected stale hardcoded health83 despite APK84 (0requests);
  corrected native health constants and added version-parity test. Second direct
  generated real ChatGPT answer1/3 but strictGemini-style proof refused native
  fullpage/prompt text and clipped screenshot. It restored79; no proxy used.
- Debugged the SAME retained direct answer, not new generations: actual new
  logged-out DOM uses data-assistant-markdown, not data-message-author-role.
  ChatGPT native answer boundary is explicit "ChatGPT said:"; summary follows
  rank by prompt design. Separate platform gate isolates it then independently
  checks exact rank in assistant DOM and screenshot. Gemini gate unchanged.
- Modern ChatGPT requires wheel positioning (scrollTop ignored); preserve exact
  textContent through temporary layout zoom. captureBeyondViewport=True moved
  page during capture; ChatGPT now usesFalse with pre/post geometry verification.
  Same-answer proof succeeded0newprompts/0reloads/0navigations, real browserclip
  .55zoom; root viewed fulltop3/rank/no-prompt at
  yokl_chatgpt_direct_20260909_v2/validated_rank.png. Map remains part of answer,
  no DOM deletion. Earlier wrapper report remains failure; separate frame JSON
  records free retained-answer recovery. Fresh automatic proof now running.
- Copilot one-job LaunchAgent/plist PREPARED ONLY, not started:
  com.deviceagent.yoklcopilotone0909, fixed5222, COST_YOKL_COPILOT=1, catalogYOKL,
  one104, original79, normalEdgepmclearON/cap4, no cache savings claim. Supervisor
  permits only missing5222–5225 (1–4ids),100MBguard/25min. Must wait until current
  ChatGPT wrapper + settled meter + rollback finish before starting another meter.
- Build84 passed;26cache/guard tests and2YOKL tests passed,24synthetic capture
  checks passed. More screenshots and actual meter numbers required before
  continuing remaining4ChatGPT/remaining3Copilot. No backend report upload yet.

## 2026-09-09 — Gemini follow-up complete; ChatGPT extension in preparation

- Gemini follow-up settled: 4/4 successes, 18.679272 MB, 4.669818 MB/success.
  Together with the first cache test: 5/5, 21.698169 MB, 4.339634 MB/success.
  Root viewed all four screenshots. Keyword5223's rank marker is dim near the
  composer edge but its explicit position4 sentence and full top3 are visible.
  Direct wrapper completed, restored79/accessibilitytrue/noVPN; daily not running.
  Six of15 YOKL pairs now accepted (5Gemini plus earlier5221Copilot); do not rerun.
- User now authorizes same cache approach for ChatGPT and Gemini. Gemini done;
  remaining ChatGPT should start with ONE metered5221 after a direct evidence pass.
  Copilot/daily/full stale queue held. No ChatGPT paid trial launched yet.
- Uncommitted WIP adds explicit RANK_CHATGPT_CACHE_TRIAL/device104-only path,
  native chatgptCachePrepared audit-only/defaultfalse, source APK84 built locally
  (NOT installed yet), original79 rollback unchanged. Gemini legacy82/evidence83
  gates remain exact: existing Gemini wrappers will reject84, do not relaunch them.
  Direct wrapper --chatgpt-cache uses fixedYOKL5221; optional --metered-output
  allows one paid ChatGPT job only. Must inspect direct response and screenshot
  before paid use. Remaining four ChatGPT continuation NOT implemented yet.
- Build passed; helper18 tests, combined9 tests, newChatGPT5 tests passed; compile,
  bash syntax and diffcheck passed. Native device regression/real ChatGPT DOM
  selector and meter evidence remain pending. No ChatGPT savings claim yet.
- User asked about shared PDTK003/004 skills. Both LICENSE-TRIAL.md read in full:
  internal evaluation through2027-08-27; section4.7 excludes client/paid delivery
  without commercial license. Inventoried filenames and selected metadata only;
  NO toolkit skill applied to current ChatGPT/YOKL implementation. Need commercial
  permission before applying those trial skills to client delivery. Independent
  implementation can continue; no toolkit files copied or installed.

## 2026-09-09 22:30 — VERIFIED cache+v83 Gemini:3.018897MB/success; four-keyword follow-up

- yokl_cache_20260909_metered/report.json COMPLETE:1paidkw5221/Gemini accepted4/4,
  no retries. Evomi29903.801635 ->29900.782738MB =3.018897MB. >=300s postsettle,
  >120s stable. Root viewed actual paid fulltop3/rank/no-prompt PNG. No newanswer
  recovery needed. CDP26cachehits/140finished/2.478432encodedMB;2unfinished,
 14failedresources,earlyeventsmaybemissing; not providerbyteattribution.
- Directv2/report.json COMPLETE restored79/accessibilitytrue/noVPN. Directchecks
  warmedcache outsideEvomi, so this is warm-cache Gemini/city-first evidence, NOT
  cold-cache/normalZIPfirst/mixed-platform/fleet savings. Detailed ANALYSIS.md in
  measured directory. OldcacheOFFpass total109.547768MB remains separate.
- User authorizes usingcache. New com.deviceagent.yoklcachefour0909 validates prior
  complete1success<8MB+rollback then runsONLYremaining5222–5225Gemini on104/v83,
  cacheON,promptfreeON,singleattempt/no retries,100MBguard,25minexecution,10GBreserve.
  Direct readiness on5222first, then same settledbaseline reused only if fresh and
  unchanged. Separateper-keyword cache/network receipts (RANK_CACHE_PILOT1).
  No repeat of5221Gemini or its previously successfulCopilot capture.
- Follow-up paths yokl_cache_four_20260909_direct/report.json and
  yokl_cache_four_20260909_metered/report.json; log yokl_cache_four_20260909.log.
  CURRENT104maytemporarily83duringfollowup; do not assume79untilfinalrollback.
- Daily remains paused267/1601saved,1334remaining. No automatic daily resume in
  cache wrapper. ChatGPT/Copilot remaining jobs held. Oldyoklpriority,yoklexport,
  cacheevidence and completedyoklcache LaunchAgents now launchctl-disabled so a
  reboot cannot restart the canceled expensive path or its automaticdailyresume.
  chain0906 remains disabled. Normal daily20:00schedule itself notdisabled.
- Current valid YOKL paid captures:5221Copilot1/3 (root viewed) and5221Gemini4/4.
  Full15pairrequest NOT complete. Afterfollowup, inspect allpaidimages and export
  partial results honestly; old15-pair export watcher is intentionally disabled.

## 2026-09-09 22:15 — User switches YOKL to cache-preserving Gemini; other work HELD

- User explicitly said use the cheaper cache setup. Stopped cache-OFF15pair run
  through owned supervisor SIGTERM after holding its parent shell, allowing APK
  rollback but preventing automatic daily resume. Verified original79/accessibility
  true/noVPN; then booted out com.deviceagent.yoklpriority0909. Export watcher also
  booted out (partial15pair CSV is not a complete deliverable). Daily still paused,
  original scheduled20:00LaunchAgent installed/notrunning. Fullchain0906disabled.
- Old priority rawCSV has4completed attempts:5221ChatGPT generationtimeout;
  5221Gemini submitfailed;5221Copilot success1/3;5222ChatGPT ocr_no_answer. A later
  started attempt may add charges. Oldmeter report deliberately invalid/interrupted;
  settle total separately. Preserve the Copilot success; do not re-run successes.
- Root viewed failedGemini PNG: prompt entered but Send icon not rendered; page
  progress bar stillloading. Cache may improve this, not yet proof. No blindtapfix.
- New com.deviceagent.yoklcache0909 runs direct_audit_smoke.py --cache-trial
  --cache-evidence --single-manifest tools/yokl_one_cache_0909.json ([5221]), using
  the isolated YOKL catalog and its original direct/request.json. Only104/v83,
  strict answer+prompt-freeOCR before ONEpaidGemini,no retries,cacheON,100MBguard,
  10GBreserve,automatic79rollback. No automatic daily/fullranking resume.
- First free preparation yokl_cache_20260909_direct refused unexpectedpage;0jobs,
  0proxy,restored79. Inspected actual browser: lastpaidYOKLChatGPT /uc/ tab remained.
  Verified page text containedYOKL+trolley, closed ONLYthat exactknownpaidtab and
  openedabout:blank throughCDP, without clearingHTTPcache. Genericguard unchanged.
- Retrying freecheck under sameLaunchAgent with NEW output
  yokl_cache_20260909_direct_v2; paid output yokl_cache_20260909_metered; log
  yokl_cache_20260909.log. Inspect these for current state; savings NOTestablished.
  Old combined-after-daily waiter remains unloaded. No expansion beyondGemini.
- Directv2PASSED26s; root viewed full prompt-free4/4answer at.65zoom. Cache receipt
  confirms2clean snapshots/0cookies/noHTTPcacheclear. Differentfreshanswerfromprior
  direct1/3; neither direct observation is a proxied deliverable. Meterbaseline
  started22:14:37at29903.801635MB; onepaidkw5221stillawaitssettling asofcheckpoint.
  OldcacheOFFpass baseline30013.349403minusnewbaseline=109.547768MB provisional
  untilnewbaselinefullysettles;4completedrows/1Copilot success plusinterruptedwork.

## 2026-09-09 evening — YOKL priority supersedes bandwidth test

- User explicitly requested pausing daily and running YOKL free-trial ranking first.
  Found live API business363/client329 Yokl, Inc., shopyokl.com,129CedarAvenue,
  Hershey PA17033; five active keywords5221–5225, campaign502, zero ranking history.
  Published address agrees with every keyword's campaignName. Isolated input
  snapshot ranking_yokl_20260909/catalog; shared /tmp catalogs untouched.
- Daily LaunchAgent booted out to pause (in-flight work interrupted), then its
  original plist reloaded with RunAtLoad=false: scheduled20:00 service preserved,
  NOT currently running daily. _build_remaining.py recorded267saved successes,
  1334remaining of1601. No successful daily rows deleted or replayed.
- com.deviceagent.cacheevidence0909 booted OUT while waiting; no test proxy/jobs
  started. Its old state.json still says waiting but it is NOT active. Do not
  reload it: source fingerprints changed for this priority request. Fullchain0906
  remains disabled. Bandwidth optimization still NOT verified with combined83.
- Active priority com.deviceagent.yoklpriority0909 -> tools/run_yokl_priority_0909.sh.
  Monitor ranking_yokl_20260909/priority.log; direct/report.json; metered/report.json.
  First direct YOKL Gemini readiness check; only104temporarily83, original79backup.
  Requires valid answer-only top3+prompt-free exact-rank screenshot before paidphase.
  Then exact15pairs (5keywords x ChatGPT/Gemini/Copilot),1worker104,no retries,
  normal ZIP-first targeting, cache OFF, prompt-free Gemini ON,750MBguard with
  meter-lag caveat,10GBreserve,75minpaid execution limit. This is the requested
  priority delivery, NOT a cache savings trial or full stale queue restart.
- Wrapper restores79/accessibility/noVPN before shell can resume daily using
  SKIP_BASE=1 PROXY_PROVIDER=evomi daily_full_auto.sh 2026-09-09. This retains the
  original plan and rebuilds only remaining jobs. A bad rollback blocks resume.
  Paid pass completion does not imply15valid captures: inspect CSV and images.
  Do not kickstart/reload the priority job (output directory is one-shot).
- Offline84tests passed/1optionalintegration skipped; Android candidate remains
  already-built83. No fleetwide APK rollout; no backend ranking writes made by
  preparation. Need final screenshots/deliverable and actual meter after paid run.
- Direct check completed63s; root inspected prompt-free full answer PNG. It is
  readiness evidence only, excluded from deliverables. Paid15-pair pass started
  21:53:50Manila, settled baseline30013.349403MB. First job5221/ChatGPT/104;
  do not call the overall run complete until its report/CSV confirms outcomes.
- com.deviceagent.yoklexport0909 waits for wrapper's final report (up to3h), then
  automatically exports all15observed outcomes and accepted PNGs to
  Desktop/Rankings/Yokl_initial_2026-09-09/. Delivery status is
  ranking_yokl_20260909/delivery_state.json; export.log records failures. Failed
  rows remain visibly failed; no fabricated ranks/backdating/backend upload.
  Root visual review of paid captures and any failed-pair follow-up remain required.

## 2026-09-09 evening — Combined cache/evidence test prepared; waiting for daily

- User authorized the next direct-then-ONE-metered-job test, NOT a queue restart.
  Sep09 daily is still building its plan; no phone touched or paid trial started
  during preparation. Fullchain0906 remains disabled; daily/Copilot unchanged.
- Explicit wrapper `--cache-trial --cache-evidence` adds83 opt-in compatibility;
  legacy gate still82/defaultoff. One device104, one paidkw64, no retries, no pilot
  or four-row mode. Requires completed native top3 answer plus prompt-free real
  screenshot/exact-rank production OCR BEFORE releasing the lock for paidphase.
- One-shot waiter tools/after_daily_cache_evidence.py under LaunchAgent
  com.deviceagent.cacheevidence0909: exact Sep09 ALL DONE, no fleet/build/proxy
  processes or mutex,60s quiet before direct actions. Source/APK fingerprint guard,
  output-directory no-repeat guard; deadline Sep10noon Manila/no start after10:00.
  It does NOT cancel daily or restore/resume anything unrelated.
- Inspect cost_cache_evidence_20260909/state.json FIRST for actual current state;
  queued is NOT measured. direct/report.json owns APKrollback79+accessibility+noVPN;
  metered/report.json and meter.jsonl own settled provider costs. test.log captures
  execution. No second paid job on failure. Final screenshots require root visual
  review; waiter does not turn measurement completion into a savings claim.
- Candidate preserves HTTP cache but clears identity/conversation state. Direct
  precheck WARMS the cache; single paid job uses city-first like prior cachepilot,
  not normal ZIP-first like the four replacements. Warmup60unchanged;100MBguard
  (lag can overshoot),10GBreserve. No cold-cache/fleet/daily-level cost claim.
- Offline82tests passed/1optionalintegration skipped,24helper tests passed; test83
  APK build succeeded. Pending phone regression, meter and visual confirmation.

## 2026-09-09 05:37 — Four replacements DELIVERED; three automatic + one same-answer recovery

- Finished the supervised repair pass below. Exact4 keyword IDs; no automatic
  retries. Paid runner accepted345,4680,4711; root viewed all3 prompt-free images.
  Scott143 had a correct answer but no scroll range to hide the prompt. No new
  generation: after proxy disconnect, root verified the retained answer and a
  browser-rendered answer-only clip. Added opt-in clip fallback, replayed it
  successfully on the SAME paid answer with OCR, unchanged text,0 reload/prompts.
- Do NOT call this4/4 fully automatic: raw report correctly remains3 successes.
  delivery_report.json separately records4 usable captures after recovery. All
  four current model outputs are4/4; August positions2/3/3/1 are references only.
- Settled Evomi31231.144306 ->31122.855906MB,108.288400MB this pass;36.096133MB
  per automatic success,27.072100MB per delivered capture after free recovery.
  Earlier failed pass98.461371MB; cumulative206.749771MB for these4 delivered
  replacements. No claim of daily-level cost or fleet-wide savings. Cache OFF.
- Deliverables: Desktop/Rankings/prompt_leak_top3_fixed_2026-09-09/results.csv
  plus4 PNGs, mirrored in prompt_leak_rerun_fixed_20260909/deliverables/.
  Original49-row request and historic reports/backend untouched.45 Perplexity
  rows skipped. These are new observed rankings, not backdated August evidence.
- Wrapper direct_ui_20260909_rerun_fixed_wrapper/report.json confirms original
  v79 restored, accessibilitytrue, no tun0. Fullchain0906 remains disabled.
  Native source83 is test-only. Clip fallback is host-side/default-off via
  RANK_GEMINI_PROMPT_FREE; validated direct on retained paid answer, not in a
  subsequent new paid generation. Daily/Copilot unchanged.

## 2026-09-09 — Gemini repair validation details (completed above)

- User said proceed after four rejected captures. Source test83 adds audit-only
  full-prompt verification, identified Send button (no blind mic-position taps),
  and answer-only completion. Daily/Copilot flow unchanged; cache gate remains82
  and is OFF for this repair. Native83 is not a fleet deployment.
- Direct inspection proved the missing-answer bug: old reader cuts at depth20
  and rect.top<=150, while actual Gemini answer nodes are depth25–31 and the rank
  is off-screen at bounds0,0. Audit reader now traverses Chrome WebView to64 with
  node/time bounds and reads off-screen text; parser requires one Gemini said
  boundary, one valid terminal rank and the complete numbered top3 answer.
- First83 direct test safely timed out before reader-depth correction. Corrected
  direct Charles and Scott tests completed in~51s, input/submit~1s each, answer
  text free of prompt. Both restored79. Evidence: direct_ui_20260909_* folders.
- Root found full-answer framing still showed prompt text. New prompt_free mode
  aligns answer at safe top, verifies user-query is above safe band, preserves
  exact answer and restores CSS. Scott card answer verified visually/OCR at0.65,
  no prompt text. Default framing unchanged unless explicitly enabled.
- Completed wrapper: tools/direct_audit_smoke.py --output
  direct_ui_20260909_rerun_fixed_wrapper --request-json
  tools/gemini_audit_charles_0909.json --rerun-manifest
  tools/prompt_leak_top3_rerun_20260909.json --metered-output
  prompt_leak_rerun_fixed_20260909. Direct precheck passed; settled baseline
  31231.144306MB. Exact4 IDs345,143,4711,4680,104 only,83,cacheOFF,
  prompt-freeON,150MBguard,no retries. Paid run, settlement, visual review and
  wrapper rollback all finished; nothing remains running from this wrapper.
- Offline75 tests (1 opt-in skipped),24 helper tests and Android build passed.
  Final measurement and limitations are recorded in the completion entry above.

## 2026-09-09 04:54 Manila — Four prompt-leak reruns attempted, ZERO replacements accepted

- User requested only four Gemini rows from Desktop/Rankings/
  prompt_leak_top3_rerun_2026-09-09.csv. Exact keyword IDs 345,143,4711,4680;
  original report dates Aug04/Aug13/Aug18 preserved as reference, not backdated
  observations. The 45 retired Perplexity rows were not run.
- Daily Sep08 finished03:41, remaining0; 1438/1438 non-Mae rows consolidated.
  New four-job pass04:34–04:48 used only104/production79, one attempt each,
  normal ZIP-first geo, same-answer reframe on, cache trial OFF. No APK deployment.
- Settled Evomi before31329.605677MB after31231.144306MB:98.461371MB total,
  24.615343MB/attempt, ZERO successes (MB/success undefined). Meter settled>=300s
  after exit with>=120s stable. See prompt_leak_rerun_20260909/report.json and
  meter.jsonl. `complete`/`valid` describe measurement, NOT accepted screenshots.
- Charles345 and St.George4711: ocr_no_answer. Root viewed saved images: prompt
  and large Maps cards, incomplete answer. Native wait_generation returned OK
  after4s/3s; saved response contained no model answer. Prompt example4/4 must
  not be treated as a real rank. Same-answer repair lacked a valid answer rank.
- SiliconSlopes4680: input failed. Scott143: submit failed then150s generation
  timeout. Root viewed voice-input UI/microphone permission prompt and tapped
  Never allow during143; no permission granted. Manual intervention disclosed.
- Desktop separate `_attempt_results.csv` contains all4 rejected outcomes.
  Original reports and backend unchanged. All4 still need valid replacements.
  No automatic retries. Fix/test answer-only completion and text/submit targeting
  without paid traffic before repeating these failures.
- Cleanup verified: no Gost/ranking runner/fleet lock,104health79/accessibility
  true, no SocksDroid tun0 (vowifi_tun0 is unrelated), chain0906stilldisabled.
- New COST_DRIVER=rerun_four in tools/run_ranking_cost_pair.sh: exact4 IDs,
  device104 only,150MB guard,40min leg cap,10GB reserve, no cache activation.
  WARNING existing launcher's FINISHED remaining=0 is not a success count when
  RANK_RETRY_ROUNDS=0; it never calculated remaining. Read CSV/measurement report.

## 2026-09-08 — Ranking-cost code consolidated into device-agent

- User requested one repository. Proxy routing/telemetry now lives in
  `device_agent_proxy/gost_manager.py`, with local tests and Rayobyte seed data.
  All tracked GostManager callers use this explicit local package. Sibling
  aeo-appium commit `126e890` is historical provenance, no longer a dependency.
- Source branch remains `feat/top3-deepdive-ranking-geo-fix`. See
  `RANKING_COST_README.md` for ownership, configuration and offline checks.
  Proxy settings must come from exported launcher settings or device-agent's
  optional `.env`; no sibling environment file is loaded or copied.
- Existing shared catalogs/audit-output paths and legacy Appium workflows were
  not relocated. Sibling history and unrelated edits were left untouched.
- This is a source-only consolidation: no paid sample, APK installation, queue
  restart, daily change or new savings measurement. The partial pilot below
  remains the latest evidence, not a fleet-wide savings guarantee. Cache trial
  remains default-off, source82/production79 as last verified; Copilot cap4 and
  Edge clearing unchanged. Localhost GOST integration now requires explicit opt-in.

## 2026-09-08 19:58 — PARTIAL mixed-city Gemini pilot: settled 4.12 MB/success

- User authorized ten-job pilot, NOT full-queue restart. Deadline19:52 protected
  tonight20:00 daily. cost_cache_pilot_20260908/report.json PARTIAL with settled
  bill24.705904MB: before39604.881585 after39580.175681. Six accepted successes
  (399,573,564,538,357,617); seventh340 interrupted in screenshot processing;
  three never started. All seven attempts' charges included:4.117651MB/success,
  ~80.4% below earlier20.970692MB successful single-job sample, NOT fleet estimate.
- Root viewed all six final PNGs: full3business answers+correct ranks4/4,4/4,4/4,
  1/3,4/4,2/3. Seven clean-cache preparations passed. No retries/rotations.
  Warmup60 unchanged; actual cache hits20–74/job; variable static-asset downloads.
- Remaining IDs [553,589,340,372]. Do NOT claim10finished or100% initiated success.
  Different six businesses/cities/states, but one phone and warmed Gemini-only
  cache; no cold-start/mixed-platform cache-survival validation. No live rollout.
- Only104 temporarily82; wrapper direct_ui_20260908_cache_pilot_smoke_v2/report.json
  restored79/accessibilitytrue/tun0absent. Expectedwrapperexit1 becausepartial
  supervisor, NOT failedrollback. NoGost/fleetlockafter; chain0906stilldisabled.
  Daily settings/20:00 LaunchAgent untouched; balance39.58GB ample for8.5GB daily.
- Free initial wrapper direct_ui_20260908_cache_pilot_smoke failedbeforeanyjob or
  proxy: unexpected_page_after_reset/verify_fresh_page; restored79. Retrypassed
  without behavior change. Originalfailure lacksIDs, causeNOTproved. Addedsafe
  page-count/isfresh/url-classdiagnostics. POSTpilot helpernowwaits<=3s forONLY
  knownoldtargets todisappear BEFOREidentityclear; unknown/freshnavigated/context
  issuesfailclosed.18offlinetestsPASS, NOT phone-tested or partofbillcomparison.
- New cache_pilot supervisor requires10IDs,1worker104,150MBbudget,singleattempt,
  hardUTCdeadline+330s settlementcap, ownedphone/hostcancellation+partialevidence.
  RANK_CACHE_PILOT1 enablesperkwcache/networkreceipts;normalpaths unchanged.
  tools/ranking_cache_pilot_0908_SELECTION.md documents selectionbias/scope.
  tools/summarize_cache_pilot.py read-only JSON aggregator; evidence_summary.json
  and ANALYSIS.md in cost_cache_pilot_20260908 contain full results/limitations.
- Next: finish4remaining in separate measured window, phone-test teardownguard,
  then cold-vs-warm and interleaved-cache validation before fleet deployment.

## 2026-09-08 14:28 — VERIFIED 2.91 MB successful cache-preserving job

- cost_one_cache_verified_20260908/report.json COMPLETE: ONEacceptedGemini kw64
  success/device104/testv82,rank2/3; before39607.792208MB after39604.881585MB,
  used2.910623MB. Finalsettle>=300safterjob+>=120sstable. Comparedwithpreviousvalid
  success20.970692MB:86.12%lowerOBSERVEDcost. NOTfleetaverage/isolate randomizedA/B.
- Wrapper direct_ui_20260908_cache_smoke_v3 restored104tooriginalv79 aftermeter.
  Allfleet still79; cachetrial remainsDEFAULT-OFF,test104only. Fullchain0906 still
  disabled; no fullqueuerestart/deployment. NoGost/fleetlock aftercleanup.
- ActualfinalPNGrootviewed: TwentyIdeas,CarrotSoftware,IEQTechnology+rank2/3all
  visible. Sameanswerreframepassed; noOCRregeneration/rotation/outerretry.
- LocalGOSTtotal2.853215MB; Geminiopen→submit1.799744MB vs16.925986oldcoldtrace;
  native-session2.704690MB; postcapture/background.047706MB; warmup60s.004262MB.
  PassiveNetworktrace134finished,38cachehits,2.045188encodedMB,0unfinished/errors.
  17of58GeminigstaticScriptresponses cached; all3fontscached.2GeminiDocs+31XHR
  uncached. Thusactualresource reuse, not merelyshorterproxytime oroldanswerreuse.
- First paidcacheattempt cost_one_cache_20260908 endedPREPROMPT oncacheguard,
  billed0.138895MB,0successes. Originalreasonnotpersisted; subsequentfreeprepare
  passed afteroldtabsalreadyclosed. CauseNOTproved. Helpernow3sboundedsettling,
  two clean snapshots>=200msapart, up to3reclears; dirty/auth/unexpectedpagesnever
  accepted. Successreceipt2checks0reclears. Totalcurrentcontinuation3.049518MB.
- Cachepreserveremovesallcookies+Google/GeminioriginstateinclSW/CacheStorage,
  closesoldtabs/verifiesfreshblank; retainsHTTPcache. Nativev82auditbooldefaults
  false; host gate104/Gemini/singleattempt/health82; ChromeMainforegroundnoURL
  beforeprepare; helperreceiptpersistedbeforefailure.70focusedtestsPASS,build82OK.
- Importantrolloutlimit: firstcoldfill stillcosts~20MB; directtests warmedcache.
  Ordinaryranking/daily/captureChrome fullclears (includinghostCopilotChromeclear)
  canerasecachebetweenGeminijobs. NeedisolatedGeminischeduling/cacheisolation+
  differentbusiness/locationvalidation beforefleetdeploymentorprojecting2.91MB
  acrossstaleset. No nightly/fleetcostclaim yet. Daily/Copilotsettingsunchanged.
- tools/gemini_network_trace.py ispassiveonly (nointerception/cachechanges/target
  pauses), enabledinthisgatedtrialwithGOST_PHASE_LEDGER; ownedforwards+WSstopped.
  tools/gemini_cache_reset.py has14tests inclrealAndroidCDPcompatibilityregressions.
- Fullanalysis/research/caveats: cost_one_cache_verified_20260908/ANALYSIS.md.
  Currentbalance39604.881585MB; no topupneededfortonight's8.5GBdaily.

## 2026-09-08 14:07 — cache-preserving experiment IN PROGRESS

- User said proceed. Full stale queue remains disabled; NO restart authorized.
- Oversized card recovery now tries .65/.55/.50 whole-answer zoom, retaining all
  text/rank/geometry/OCR guards and restoring exact original style. Free replay
  direct_ui_20260908_phase_card_reframe_half passed at .50 on the last failed paid
  answer; root viewed all3businesses+Carrotrank4/4. No newpaidgeneration forrepair.
- Built testAPK82/0.9.65-gemini-cache-trial (source+healthconstants). New audit-only
  geminiCachePrepared bool defaultfalse; skips nativefullclear ONLY explicitGemini.
  Daily/otherplatforms unchanged. Only104 temporarilyinstalled by wrapper below;
  original79 backup retained and wrapper must restore79 whenmeasurementends.
- tools/gemini_cache_reset.py testonly104+singleattempt+env1: verifiesdefaultChrome
  profile/noGoogleauthcookies, createsfreshblank, closesoldtabs, clearsallcookies
  plusGemini/www.google.com originstate inclSW/CacheStorage, verifiesemptycookie
  list/quota/unique freshpage. DoesnotrequestHTTPcacheclear. AllowsGooglehomepage
  only(notsearch/accountURLs). Androidnumeric/jsonIDs vsTargethexIDs verified via
  Target.getTargetInfo; truthydefaultcontext is NOTincognito (getBrowserContexts).
- Host RANK_GEMINI_CACHE_TRIAL=1 gated104/Gemini/singleattempt/health82; foregrounds
  existingChromeMain(noURL), preparescache state thenbodyflagtrue; skips hostpmclear.
  COST_CACHE_TRIAL=1 enablesonlyonejobsupervisor; allflags defaultoff. First direct
  prep failedbeforeanyjob and restored79: direct_ui_20260908_cache_smoke.
- Active wrapper: COST_SPEND_BASELINE_MB=39607.931103 python3 tools/direct_audit_smoke.py
  --cache-trial --output direct_ui_20260908_cache_smoke_v2
  --metered-output cost_one_cache_20260908. Direct native success26sec, fresh2/3answer
  (prior4/4), rootviewed screenshot all3+rank. Now supervisor7minbaseline settling,
  thenONEpaidGemini attempt, no retries,100MBcumulativeguard, post>=300s+120stable.
  Do NOT end turn while running; monitorthroughfinish+APKrollback. Balanceunchanged
  39607.931103MB duringdirecttests. No paidcachejobstarted asof14:07.
- Agenttraffic_driver buildingoptionalpassive browserNetworktrace; rootonlyintegrate
  iftested beforepaidlaunch~14:12. No interceptor/cachebehaviorchangesallowed.

## 2026-09-08 13:43 — measured why a single Gemini attempt still costs ~20 MB

- User asked to find remaining20MB; ONE new bounded kw64/device104/v79 job finished,
  cost_one_phase_20260908/report.json COMPLETE: before39632.432320MB,
  after39607.931103MB, used24.501217MB, ZERO accepted successes (ocr_no_answer).
  No retry. Meter waited>=300s afterjob and>=120s stable; last charge arrivedlate.
- Fullqueuechain0906 remainsdisabled, no Gostprocess/fleetlock/phone tun0 aftertest.
  NoAPKchanges, nofleetdeployment, daily untouched. No extra paid jobs thisturn.
- Opt-in GOST_PHASE_LEDGER now records localhost live cumulative counters every1s
  and exact dispatcher phase snapshots including BEFOREdisconnect/stop. Enabled
  only with COST_PHASE_TELEMETRY=1 for this test. 4 isolated metrics tests including
  actual localhost-only open-socket32768byte transfer pass; summary3tests pass;
  existing reframe36+launcherdefault3 tests pass. Counters are NOT billedMB.
- Local24.859020MB breakdown: beforeGemininavigation0.591539; Geminiopen→submit
  16.925986; submit→native-return4.184962; postanswer/CDP/OCR/background3.156533.
  Warmup60sec alone0.004355MB. Mainexpensivephase is BEFOREpromptsubmission,
  notproxyidle. No per-host traffic attribution yet; background cannotbeexcluded.
- Existing page resource timings read WITHOUTreload/newrequests afterproxyoff:
  133entries,60Geminigstatic scripts (cross-origin sizes hidden/zero; donotclaim
  measuredscriptbytes), StreamGenerate response104684bytes, fonts467948bytes.
  tools/capture_existing_resource_timing.py saves sanitizedhost/path/noquery;
  tools/summarize_ranking_phases.py aligns nativefiletimestampswithphoneclock.
- IMPORTANT correction to previous single-success claim: current oversized rich
  place-card answer failed full_answer_clipped_or_changed. Rootviewedoriginal+final;
  neither showsallrankers+rank. RecoveryisNOTrobustforalllayouts. OriginalfailedCSV
  preserved. DoNOTweakenOCR/fullanswer guards orlabelthissuccessful/cheaper.
- Nexttarget: coldGeminiassets/resource-leveltrace beforeload; testpreservingonly
  safe staticcache while resettingidentity/conversation, plusoversizedcardsframefix.
  Neithercachepreservation nornewcapturefix implemented/validated. Bothdaily/rank
  nativeGemini fullclear; dailyaggregateismixedplatform, notmatchedGemini control.
- Detailed evidence/research/limitations: cost_one_phase_20260908/ANALYSIS.md.
  Currentbalance39607.931103MB. Previous20.97MB hour Evomi normal20.97/extra0.

## 2026-09-08 13:20 VERIFIED one-job recovery — latest

- Completed cost_one_reframe_verified_v79_20260908/report.json: ONE scheduled job,
  ONE accepted success, kw64/device104/v79, before39653.403012MB after39632.432320MB,
  used20.970692MB. Finalmeterwait>=300s afterjoband>=120sstable. OneGostsession,
  no proxyrotation/newgeneration/OCRregeneration. Rootviewedoriginal+finalPNGandOCR:
  all3businesses andrank4/4visible inactualrecoveredphonescreenshot.
- Rootenabled ONLY rankinglauncher's RANK_GEMINI_SAME_ANSWER_REFRAME default1 after
  measuredsuccess. Rollbackenv0. Auditmodule stilldefault0; dailyunchanged, proxygeo
  unchanged, normalretrylimitsunchanged, noAPKrollout. Allphonesremainv79; v81source
  input-evidence/submitguardbuildparked. Fullchain0906 STILLdisabled: NOqueue restart.
- IMPORTANT: This is a successfulsingle-job proof, NOT matchedfleet-average savings
  and NOT daily-levelcost. Testusedcityfirst1+singleattempt1; productionretainsoriginal
  targeting/retries. Newstrictnumericrankgate canrejectpreviouslyacceptedpartialshots,
  so boundedmulti-job cost/success validation remains before resumingthefullqueue.
- Recoveryrepairsgeometry BEFORE mutatingCDPcleanup: uniquevisibleGeminianswer,
  keyword+exactrank, smallestmatchingrankcontainer(inlinebusinesslinksallowed),
  wholeanswerscroll, temporaryanswerCSSzoom0.65onlyifneeded, nearestscrolleralignment,
  safe-bandexcludesvisible sign-in-nudge overlay. Exactinlinezoomvalue/priorityrestored.
  Requiresunchangedanswertext+fullanswerinview+OCRexactexpectednumericrank; list-only
  OCR cannotpassrecovery. Noanswer/promptregeneration orDOMtext/nodedeletion.
- Currentcontinuationpaidtests:18.816653MB artifacterror;31.638651MB selectormiss;
  20.970692MB verifiedsuccess. TOTAL71.425996MB. OriginalfailedCSVrowsNOTrelabeled.
  Freeactualproductionearlyblockreplays repairedbothsavedanswersduringdebugging.
- cost_one_reframe_verified_20260908 (without_v79) abortedBEFOREpaidtraffic because
  previousbaselineagedpast10min. Currentreusepolicy15min+freshunchangedmeterrecheck;
  stillrequiresprevious7stablepost-readingsandfullpost-testsettlement. Cumulative
 100MBguardwasactivefortheverified_v79job; nofurtherpaidtestsstarted.

## 2026-09-08 12:57 continuation — NOT yet end-to-end accepted

- Full stale queue still disabled. Do NOT claim ranking now costs like daily.
- cost_one_reframe_v81_20260908 completed:18.816653MB/0accepted. Native generated3/3;
  newhostartifact reframe_source was notwhitelisted. Fixedandrealwriterregressionadded;
  originalerrorCSVpreserved. Root recovered SAMEpaidanswer unproxied, no newprompt.
- Scroll-only recovery can clipitem1. TestedtemporaryCSSzoom0.65 on answer only:
  all3businesses+rankvisible, unchangedtext, originalzoomrestored. Helper nowrequires
  fullanswerbbox in safe160..innerHeight-130band, retains exactDOMnode for restoration,
  strictOCR and existingorigin/keyword/uniqueanswer/rank guards. No deletingnodes/text.
- Actualproductionearlyblock replay passed on3/3paidanswer:
  direct_ui_20260908_paid_dispatch_replay (rootviewedPNG+OCR). Recovery nowruns BEFORE
  mutatingCDPcleanupcanremovepromptidentity; successfulrepairskipsoldCDPpath.
- cost_one_reframe_final_20260908: nativegenerated2/3butocr_no_answer. Metercurrently
  31.638651MBdeduction, postsettlingstillrunning. Reproduced exactreason unproxied
  withoutbringingChromefront: ambiguous_rank_leaf. Actualrankparagraph contains inline
  businesslinkchildren,sochildElementCount===0 wronglyrejectsvalidrankdirecttext.
  Agentreview_measurement fixing smallestunique rankcontainer +regressions; rootmust
  replayexisting2/3response beforeanotherpaidjob. SavedresponseandDOMunder
  direct_ui_20260908_final_failure_observe and direct_ui_20260908_rank_markup.
- Bothpaidattemptsfailedautomatedacceptance; totalcurrently50.455304MB. Do not relabel
  themsuccessbecauseanswerwaslaterrecoveredlocally. Experimentalflagsstilldefaultoff.
- tools/direct_ui_probe supports --dispatch-replay SAVED_RESPONSE --validated-frame
  toexecuteREALearlycaptureblock/helper/writer withoutdispatch/importingfleetmodules.
- Latestpaidwrapperstillowns temporaryv81on104untilpostsettle; itrestoresv79andVPNoff
  automatically. Earlierwrapperrestored79/accessibilitytrue/noVPNverified.

## 2026-09-08 12:31 active bounded continuation

- User requires continuous debugging/monitoring, not ending turns while a test waits.
  Full chain0906 remains launchctl-disabled; no stale queue restart authorized.
- Earlier one-job report cost_one_reframe_20260908 completed: 2.898589 MB, input
  failed, zero accepted answers. This is NOT evidence of reduced cost per success.
- Actual failure log: normal EditText discovery exhausted, then blind lower-screen
  clipboard fallbacks failed. Later direct idle XML shows normal Ask Gemini EditText
  at [147,1384][553,1430], focusable. Thus selector-class mismatch is NOT established;
  transient loading/accessibility/network readiness remains unresolved.
- Source/APK candidate v81 0.9.64-audit-input-evidence: audit-only input failures now
  capture screenshot before returning; v80 rejected-submit guard retained. Daily and
  Copilot flow unchanged. Four source regressions pass; Gradle debug build successful.
- Direct v81 audit completed with input/submit/generation successful and rank4/4.
  First wrapper erroneously expected normalized success instead of native completed;
  it safely refused paidphase and restored79. Fixed gate accepts native completed.
- Root inspected direct_ui_20260908_v81_answer_reframe/validated_rank.png and actual
  OCR: all three numbered names and rank4/4 visible; same answer unchanged, zero new
  prompts/reloads. Large business cards caused initial screenshot to miss rank.
- Active tools/direct_audit_smoke.py --output direct_ui_20260908_input_evidence_v81b
  --metered-output cost_one_reframe_v81_20260908: direct completed51s; now one paid
  kw64/device104 job under reframe_single supervisor. Baseline39703.858316 MB.
  Exactly1paidjob, no rotations/OCR regeneration,100MBguard with lag caveat. Restores
  original79 at end. Root must inspect final result/image/meter, not stop at started.
- Experimental reframe now uses strict OCR: missing/disabled/error OCR fails closed;
  old callers retain default behavior. No experimental flag enabled for live queue.
- Review: full-session extras accounted for40.8%/56.7% of local recorded traffic in
  screenshot control/candidate10-job samples. NOT Evomi billed shares. Existing GOST
  ledger lacks host/phase attribution; duration alone does not explain traffic.

## 2026-09-08 11:49 one-job meter test — latest

- User explicitly authorizes ONE proxied job to measure screenshot recovery cost.
  com.deviceagent.onereframe0908 -> cost_one_reframe_20260908/report.json.
  Keyword64, device104 ONLY, MAX_JOBS1, one candidate leg, no baseline repeat.
- RANK_GEMINI_SAME_ANSWER_REFRAME1 plus RANK_SINGLE_ATTEMPT1 (new defaultoff guard)
  disables whole-session rotations/OCR regenerations. Same-answer local repair is
  allowed; failing screenshots remain ocr_no_answer. OCR/text consistency preserved.
- 100MBspendguard (lag overshootpossible),10minexecutionlimit,10GBreserve;cityfirst,
  warmup60 unchanged. Device104 is restoredv79, so this tests host-side screenshot
  recovery, NOT v80 APK submitguard. Full stale queue remains disabled.
- One result establishes actual one-job cost, not a causal/average savings claim.

## 2026-09-08 11:33 direct UI investigation — latest

- Completed11:36: tools/gemini_same_answer_reframe.py helper passed10 synthetic
  JS guards and a real direct phone check (direct_ui_20260908_validated_frame):
  oktrue,response_unchangedtrue,ocr_verifiedtrue,0newprompts/reloads/navigations.
  Discovers actual Chrome sockets using owned dynamic forwards, requires visible
  Gemini page/keyword/unique answer rank, scrolls existing rank node only, saves
  real screenshot and requires caller's unchanged OCR gate. Does not delete DOM.
- audit_dispatch_http has default-OFF RANK_GEMINI_SAME_ANSWER_REFRAME=1 hook before
  OCR full regeneration. It only attempts consistent parsed Gemini success with
  failed screenshot validation;8 guard exclusions/defaultoff tested. Not enabled
  live, no measured proxied savings claim. Some reframed shots show rank/lower
  answer but not entire top3; client deliverable QA remains before rollout.
- Final Evomi check39706.756905 unchanged. Fleetlock absent, fullchain disabled,
  no test job running. Submit failed branch still needs on-device negative-case
  validation; direct smoke verified successful path and originalAPK restoration.

- User requires NO proxy for UI tests. All proxy trials completed; stale chain
  still disabled. Evomi balance39706.756905 unchanged from last screenshot trial.
- Screenshot-only mode did NOT improve cost: control336.323823MB/5 successes,
  original-app-only382.940755MB/5. Not adopted.
- Root personally inspected failed images: answer business cards present, rank
  below viewport, banners/promo overlay. `ocr_no_answer` is misleading for partial
  answers. Gemini skips scroll_rank; failed submit return also used to be ignored.
- On device104, old answer from~10:50 was STILL in DOM at~11:26. No universal
  3-second wipe. Default Chrome devtools socket timed out, suffixed socket worked.
- Direct no-new-job proof: direct_ui_20260908_frame2. Before screenshot fails actual
  _screenshot_has_answer; rank_visible.png passes after answer-scoped rank node
  scrollIntoView. Answer text unchanged;0newprompts,0reloads. Shows rank and lower
  answer, not all top3 together. Full beyond-viewport clip attempt frame1/2 failed
  visually and must NOT be used as a deliverable.
- Submitguard implemented audit-only AgentHttpServer.kt: failedsend captures error
  screenshot and returns submit failed before waiting for generation. Three source
  regression tests pass; Gradle build passes. Sourceversion80 0.9.63-audit-submit-guard.
- One direct smoke on device104: version80,51.43s, submitOK+generationOK+rank4/4.
  direct_ui_20260908_submit_smoke_v2 contains request/response/PNG/report. This tests
  successful path, NOT a forced failedsend on hardware. Originalv79 APK backed up
  in direct_ui_20260908_apk then restored; dumpsys andhealth79/accessibilitytrue/
  tun0false verified. No other phone updated, tracked device-agent.apk untouched.
- Direct probe safety fixes: match exact tun0 (not inactive vowifi_tun0); use actual
  suffixed Chrome socket; empty accessibility-list reset uses settings delete.

## 2026-09-08 10:06 update — latest

- Idle test COMPLETE: device103, setup+180s hold cost0.048679 MB; does not support
  idle background traffic as main cause on this phone. No fleet-wide inference.
- Warmup test COMPLETE09:35, meter still40426.021483 at10:03. 60s control:
  428.196611MB/5 successes; 3s candidate357.450290MB/6 successes. Both had3 final
  OCR failures. Small serial sample, not proof that time alone caused saving.
- User authorizes screenshot comparison now. com.deviceagent.screenshottrial0908
  uses COST_DRIVER=gemini_app_screenshot; both legs city-first, warmup60,
  timeout/input rotations on, OCR on, text-only bypass off. Only candidate sets
  RANK_GEMINI_APP_SCREENSHOT=1 to skip late Gemini CDP and validate original app
  screenshot. This does not disable screenshot or rank-consistency validation.
- Output cost_screenshot_20260908/report.json; 10jobs/leg,1GB spendguard with
  lag caveat,10GBreserve,45minexecution/leg. No full stale queue restart.
- Offline original-vs-selected screenshot evidence review running independently;
  no concurrent proxy tests. All prior measured test controllers have completed.

## 2026-09-08 08:12 update — latest

- Timeout trial finished 07:59: control 298.534149 MB/6 successes (49.76 MB/success),
  timeout rotation off 275.114542 MB/4 successes (68.78 MB/success). Not adopted:
  fewer bytes per scheduled job but worse cost per success in this sample.
- User specifically asks whether connected idle time explains the gap and authorizes
  idle measurement then 60s-vs-3s ranking warmup comparison. Daily waits 3s after
  connecting, ranking 60s after tunnel checks; both disconnect in finally. Sleep
  itself sends no data but all-app VPN traffic means the wait is NOT known free.
- traffic_driver agent implementing/running one-phone 180s idle test under fleet
  lock, 100 MB guard, 10 GB reserve, delayed-meter settlement. No concurrent tests.
- Ranking warmup is now configurable via RANK_WARMUP_S (default remains60),
  validated finite0..120. Harness COST_DRIVER=warmup uses city-first for both legs
  and changes only warmup60->3, leaving OCR and retries enabled. Offline tests pass.
- Warmup supervisor com.deviceagent.warmuptrial0908 waits for a completed valid
  cost_idle_20260908/report.json, then for fleet idle and meter settlement BEFORE
  starting any jobs. Missing/invalid idle report aborts without ranking traffic.
  Output cost_warmup_20260908/report.json; 1 GB guard,45min/leg,10jobs/leg.

## 2026-09-08 06:57 update — latest

- Daily finished 05:21 with two unresolved pairs. Full stale chain remains disabled.
- City comparison completed 06:32; meter unchanged again 06:47. Ten Gemini jobs
  per leg: existing routing 543.618749 MB / 6 successes = 90.603125 MB/success;
  city-first 369.781804 MB / 8 successes = 46.222725 MB/success. This is not
  daily-level cost and is a small serial sample, not an all-platform guarantee.
- Logs explain amplification: control six OCR recaptures + four timeout rotations
  (20 setup cycles); candidate four OCR recaptures + two timeout + one input
  rotation (17 cycles). Zero OUTER retries does not disable these INNER retries.
- User authorizes fixing these expensive repeats, still NO full-queue restart.
- `com.deviceagent.timeouttrial0908` is now running a bounded comparison using
  `COST_DRIVER=generation_timeout`: both legs city-first, only candidate disables
  generation-timeout rotation. OCR validation and other controls unchanged.
  Status: `cost_timeout_20260908/report.json`. 10 jobs/leg, 1 GB guard (lag can
  overshoot), 45-minute execution limit/leg. Do not run concurrent proxy tests.
- Offline OCR evidence review underway. Do not enable text-only bypass or count
  an invalid screenshot as a success just to improve bandwidth metrics.
- Offline review: rejected images lack rank, response text contains it. Original
  inline app image was previously discarded when late CDP capture returned a path;
  we CANNOT prove retrospectively that the original image was valid. Trace mode
  now saves separate `*_app_original.png` before CDP for both timeout trial legs.
  `RANK_GEMINI_APP_SCREENSHOT=1` is a prepared, default-off fix to skip Gemini CDP
  and validate the immediate app image with unchanged OCR/consistency gates.
  Harness supports `COST_DRIVER=gemini_app_screenshot` but that test is NOT launched.

## Investigation update — 2026-09-07 evening (takes precedence)

- User explicitly requires the full stale queue to stay paused while cost is
  measured. `com.deviceagent.chain0906` is unloaded AND launchctl-disabled so a
  reboot cannot restart it. Do not kickstart/re-enable it as part of testing.
- Daily 2026-09-07 finished prompt build and started phone jobs at 21:01.
- `com.deviceagent.bandwidthtrial0907` runs only a matched 10-job Gemini control
  and 10-job city-first candidate after the daily finishes. No stale-queue resume.
  Status: `cost_trial_20260907_v3/report.json`, events in the same directory. Budget
  guard 1 GB (meter-lag overshoot possible), reserve 10 GB, per-leg limit 45 min.
  Post-traffic settlement waits at least five minutes and two minutes stable.
  City-download saving is provisional (~29%), NOT proven ranking MB/success;
  delayed billing invalidated the initial 36% figure. See PROXY_COST_SPEC.md.
- Verified macOS bug: `seq 1 0` produces 1 and 0, so prior "zero outer retries"
  tests ran two extra rounds. Fixed arithmetic loop and checked 0/1/2 values.
- Prior claims that 2–3 minutes without CSV output proved a startup stall were
  unsupported. The 60-second warmup and generation legitimately take time.
  RANK_PHASE_TRACE=1 now records actual phase progression.
- Reverted unproven launcher defaults (Gemini text-only bypass, skipped input
  rotation, reduced tunnel retries) to opt-in. Gemini bypass now also requires
  a parsed text rank and passes the consistency gate. No weakened validation live.
- Evomi API shows 4,861.18 MB extra charge during the six hourly ranking buckets,
  about 18% of 27,031.84 MB total. ZIP is a billed expert option; daily omits it.
  Direct ten-download ZIP sample: 10 MB delivered, 13.792797 MB deducted.
  Full comparison and corrections are recorded in PROXY_COST_SPEC.md.
- Optional GOST_COST_LEDGER saves sanitized byte summaries before cleanup; they
  are lower bounds from terminal connections. Provider meter remains authoritative.

**Project:** /Users/seolocalph/projects/device-agent
**Branch:** feat/top3-deepdive-ranking-geo-fix — `71936b9` pushed to **devicefarm1**

## THE JOB FOR THE NEXT SESSION (user's words, verbatim)

> "investigate how can we make this work like not expensive we will not waste bandwidth
> right? no mistake, you can scan /Users/seolocalph/Downloads/pdtk-trial-2026-erven-004
> and /Users/seolocalph/Downloads/pdtk-trial-2026-erven-003 see if it has skills that we
> can use, also research anything on the internet how we can improve, please deploy agent
> each, have each like test also, tell me what you need."

Concrete plan:
1. Scan both pdtk-trial folders for skills relevant to proxy bandwidth, retry policy,
   screenshot validation, fleet orchestration. `003` has ~202 `SKILL.md` files (dirs:
   commands/ docs/ hooks/ lib/ manifest.json), `004` has ~34 (plus DEPLOY-AWS.md,
   FUNCTIONS.md, LESSONS.md, METHODOLOGY.md). Both are TRIAL licenses (LICENSE-TRIAL.md,
   WATERMARK.txt) — read the license before copying anything into the repo.
2. Web research: residential-proxy bandwidth reduction for mobile browser automation —
   block images/fonts/analytics (CDP `Network.setBlockedURLs` on Chrome; a filtering
   layer on gost for Edge/Copilot where CDP is not attached), HTTP/2 + compression,
   session reuse instead of per-job tunnels, no re-render for the clean screenshot.
3. Quantify EACH bandwidth driver with the Evomi meter (`evomi_balance.py`), one at a
   time, small samples: per-job gost preflight (1431 builds in one leg), OCR
   "no answer" re-capture (247), session rotation (221), `cdp_strip_map_shot` re-render
   (ChatGPT/Gemini), Edge `pm clear` per Copilot job (doubled the daily: 3.3 -> 8.5 GB).
4. Quantify each FAILURE class the same way: `async start failed: TimeoutError` (phone
   HTTP server refusing connects — ChatGPT 34, Gemini 35), `generation timeout`
   (ChatGPT 30, Gemini 45), `input failed` (26/35 — proxy exit quality), Copilot
   `navigate failed` 44 and `reset_edge failed` 23.
5. Fleet hygiene before any measurement: **device-125** (`1490455572008742`, the
   com.farm test phone) got into the ranking pool and went 0/116 — it must be excluded
   (`DEVICE_EXCLUDE` or roster); **device-108** went 0/55 — diagnose.
6. One agent per driver: each runs a small measured sample (meter before/after, N jobs,
   one platform), reports MB/attempt and success rate, and proposes the change. No
   change ships to the live set without a number.
7. Update `PROXY_COST_SPEC.md` and the cost page
   (https://claude.ai/code/artifact/ed7e7f74-a918-4b39-9382-030554620832) with the
   with-retries numbers below.

**Ask the user for:** (a) Evomi top-up BEFORE 20:00 today (tonight's daily needs
~8.5 GB, balance is 3.6 GB); (b) whether fixes may be tried on the live stale set or
only on small measured samples; (c) whether to park Gemini in the stale set (47%,
most expensive per success) until its generation timeouts are understood.

## Completed This Session (2026-09-05 -> 09-07)
- Free-trial re-rank for clients 323-327 delivered: `~/Desktop/Rankings/ranking_freetrial_2026-09-05_consolidated.csv`, 75 rows dated 2026-09-05, all 25 Copilot shots on v79 (0 prompt leaks).
- **v79 `0.9.62-copilot-frame-top`** (`c9e3936`) fleet-wide: no clipped #1, no prompt text in Copilot shots (bubble re-query, drag-back, prompt-band splice).
- **Ranking path pm-clears Edge** before every Copilot job (`149403a`); 104/113/119/123 went 0/20 -> 4/4.
- **Validator fix** (`71936b9`): Copilot en-dash inside business names no longer reads as a fabricated rank (29/30 false rejections replayed); `_name_candidates` gets a strict " - "-prefix candidate.
- `build_ranking_dueset.py` honors `ADMIN_BASE` + `ADMIN_TIMEOUT_S` (App Runner 502s the keywords endpoint at 120 s; local build server answers in <1 min).
- Daily 2026-09-05 (1648/1648) and 2026-09-06 (100%) delivered.
- Boot-safe chain: LaunchAgent `com.deviceagent.chain0906` -> `_chain_0906_agent.sh`, log `_chain_0906.log` (repo). Resumes daily then ranking with SKIP_BASE, yields 19:45-20:30, floors at 4 GB.
- Landmine removed: `com.deviceagent.staleafter` (RunAtLoad, date 2026-08-08 baked in) -> plist renamed `.disabled`.
- `/tmp` inputs rebuilt after the 09-06 08:28 reboot; copies in `_snapshots_2026-09-02/`.
- Memory notes: `device-102-revived-by-deploy-rebind`, `reboot-wipes-ranking-inputs`.

## Current State
- **Evomi balance 3,623 MB.** Chain PAUSED at the floor (`CHAIN PAUSED` line in `_chain_0906.log`). Nothing running on the fleet.
- Stale ranking 2026-09-02: **1384 / 3492 pairs good**, ~2000 left (chatgpt 488, gemini 432, copilot 464).
- Resume after top-up: `launchctl kickstart gui/$(id -u)/com.deviceagent.chain0906`.
- Tonight 20:00: `com.deviceagent.dailyfull` fires for 2026-09-07 on its own.

## Measured cost (Evomi meter, not modelled)
| workload | MB/attempt | MB/success | basis |
|---|---:|---:|---|
| Daily (with Edge pm clear) | 3.96 | 5.2 | 09-05: 8,537 MB / 2,155 attempts / 1,648 sessions; 09-06: 8,492 MB |
| Daily, spec value (pre pm-clear) | 1.96 | ~2.2 | 09-02 |
| Ranking, single pass (spec) | 17 | ~25 | 09-03, retries off |
| **Ranking, production with retries** | **29.2** | **52.3** | 09-07 04:04-09:54: 26,836 MB / 920 attempts / 513 successes |

Ledger of the 51 GB top-up (09-06 05:43 -> 09-07 09:54): daily 09-05 8.5 GB, guard-bug
warmup loop 3.3 GB (fixed), daily 09-06 8.5 GB, ranking 26.8 GB, left 3.6 GB.

## Why ranking fails and costs (09-07 04:04-09:54, 15 phones)
- Success: chatgpt 176/290 (61%), gemini 147/314 (47%), copilot 190/316 (60%). The daily runs the same phones at 95-100%.
- Extra page loads in that leg: 1431 gost preflight builds, 247 OCR "no answer" re-captures, 221 session rotations, 96 generation-timeout retries, 78 input_failed retries, 43 navigate retries, 30 "fabricated rank" re-captures.
- Median job: chatgpt 206 s, gemini 299 s, copilot 201 s; failures run longer than successes.
- Worst phones: device-125 0/116 (must not be in pool), device-108 0/55, device-104 22/49.

## Key Decisions
- **Ranking must not waste bandwidth**: every change is measured at the meter on a small sample before touching the live set (user's instruction "no mistake").
- Copilot cap stays 4 in flight; Edge pm clear stays (it is what made Copilot work) until its bandwidth is measured against an alternative.
- Chains that must survive boots are LaunchAgents with repo-side logs, never nohup.
- Never judge a run with `tail -N` on a results CSV (multi-line `response_text`); parse rows.
- Evomi for ranking (100% state / 97% city accuracy vs Rayobyte 91% / 82%).

## Files Modified (tracked)
- `app/src/main/java/com/deviceagent/EdgeCopilotFlow.kt`, `AgentHttpServer.kt`, `app/build.gradle.kts` — v79.
- `audit_dispatch_http.py` — Edge pm clear on ranking path; `_rank_inconsistent` en-dash fix; `_name_candidates` " - " candidate.
- `build_ranking_dueset.py` — `ADMIN_BASE`, `ADMIN_TIMEOUT_S`.
- `CLAUDE.md` — v79 row.
Untracked ops scripts (repo root): `_chain_0906_agent.sh`, `_chain_0906_daily_then_rank.sh` (old, do not run), `_balance_guard.sh` (old, superseded by the agent's guard), `_rebuild_dueset_0902.sh`, `evomi_balance.py` (**hardcodes the Evomi API key — move to `EVOMI_API_KEY` in `.env.dev`**), `_snapshots_2026-09-02/`.
LaunchAgents: `~/Library/LaunchAgents/com.deviceagent.chain0906.plist` (active), `com.deviceagent.staleafter.plist.disabled`.

## Next Action
> Ask for the Evomi top-up first (deadline 20:00). Then start the investigation: read the
> LICENSE-TRIAL.md in both pdtk folders, inventory their skills against the six drivers
> above, and spawn one measuring agent per driver on a 10-20 job sample each.

---
## Session Opener (paste at start of next session)

```
device-agent. Read HANDOVER.md first (2026-09-07). Then CLAUDE.md "Copilot: cap it at 4".

Job: make ranking NOT waste bandwidth. Measured: ranking costs 29 MB/attempt and
52 MB/success with retries (26.8 GB for 513 pairs on 09-07); daily is 8.5 GB/night since
the Edge pm clear. Success 47-61% on ranking vs 95-100% on the daily with the same
phones. Drivers to measure one by one at the Evomi meter: per-job gost preflight (1431
in one leg), OCR "no answer" re-captures (247), session rotations (221), cdp strip
re-render, Edge pm clear. Failure classes: async-start timeouts, generation timeouts,
input failed, Copilot navigate/reset_edge. device-125 (com.farm test phone) is in the
pool and must be excluded; device-108 went 0/55.

Scan /Users/seolocalph/Downloads/pdtk-trial-2026-erven-003 (~202 SKILL.md) and
.../pdtk-trial-2026-erven-004 (~34) for usable skills (check LICENSE-TRIAL.md first),
research the internet for bandwidth reduction in proxied mobile browser automation, and
deploy one agent per driver to test with a measured sample. No change to the live set
without a meter number.

State: Evomi balance 3.6 GB; tonight's 20:00 daily needs ~8.5 GB — ASK FOR A TOP-UP
FIRST. Stale ranking 2026-09-02 is at 1384/3492, paused by LaunchAgent
com.deviceagent.chain0906 at the 4 GB floor; resume with
`launchctl kickstart gui/$(id -u)/com.deviceagent.chain0906` after top-up.
```
