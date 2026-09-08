# Ranking bandwidth investigation checkpoint

This commit saves experimental code and measured reports. It does not deploy an
APK, resume ranking, or change the daily LaunchAgent.

## Repository ownership

All ranking-cost implementation, telemetry tests, measured reports and the HTML
forecast now live in `device-agent`. The proxy manager is
`device_agent_proxy/gost_manager.py`; callers import that explicit package.
It includes the routing/telemetry work originally saved in sibling commit
`126e890`, but that sibling commit is no longer required. Edit this local module
for future device-agent work; do not maintain a second fix in aeo-appium.

Export proxy settings from the existing launcher environment (`.env.dev` where
applicable). The module only loads this repository's optional `.env` as a fallback;
it never loads sibling credentials. No credentials were copied. The Rayobyte
no-pool seed is included locally. Existing shared client catalogs, audit output
paths and legacy Appium workflows are unchanged: this is code consolidation,
not a migration of the entire farm's data or the aeo-appium application.

## Deployment state

- Source builds test version 82; production phones remain on version 79.
- The tracked root APK is intentionally not replaced by the experimental APK.
- Gemini cache preservation defaults off and the host restricts it to device104,
  Gemini, a single attempt, and verified version82 health.
- Same-answer screenshot recovery is enabled by the ranking launcher; set
  `RANK_GEMINI_SAME_ANSWER_REFRAME=0` to disable it. This differs from the cache flag.
- Keep Copilot cap4 and Edge clearing unchanged. Never put device125 in the pool.
- Post-pilot old-target teardown waiting has offline tests but no subsequent
  paid measurement; it cannot receive credit for the recorded pilot savings.

## Reproduce checks without phones or paid traffic

```bash
python3 -m unittest discover -s tests
python3 -m unittest discover -s tools -p 'test_*.py'
bash -n run_ranking_auto.sh tools/run_ranking_cost_pair.sh measure_ranking_cost.sh
```

The localhost GOST integration test is skipped unless
`RUN_LOCAL_GOST_INTEGRATION=1` is explicitly set. Do not enable it during fleet
work. Ordinary test discovery makes no paid requests or phone changes.

The Apple Vision OCR executable is a local build, not committed. Its source is
included. On macOS, build it with `swiftc tools/ocr_vision.swift -o tools/ocr_vision`.
The test APK is built using the project's existing Gradle setup; building is not
permission to install it or run paid jobs.

Meter helpers use the existing local `evomi_balance.py` credential configuration,
which is deliberately untracked. Test wrappers additionally need a verified
device104 original-v79 APK backup at the documented local path before running.
No credentials or APK backups are included here.

## Evidence and team report

- `cost_cache_pilot_20260908/report.json`: partial pilot, six accepted results,
  24.705904 MB total including a seventh interrupted attempt (4.117651 MB/success).
- Meter JSONL provides delayed-charge settlement evidence; raw client CSVs,
  browser traces, screenshots and proxy logs remain local and untracked.
- `proxy_forecast_20260908/proxy_forecast_20260908.html`: standalone internal team report.
- `HANDOVER.md`: safety constraints, remaining four IDs and next validation steps.

No commit in this checkpoint authorizes a fleet-wide claim of 80% savings.
