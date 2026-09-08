# Session Handover — 2026-09-07 10:45 PST

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
