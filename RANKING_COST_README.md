# Ranking bandwidth investigation checkpoint

This commit saves experimental code and measured reports. It does not deploy an
APK, resume ranking, or change the daily LaunchAgent.

## Companion dependency

The sibling `aeo-appium` repository must include commit `126e890` for the optional
GOST phase metrics and Evomi routing controls. Its unrelated working-tree edits
are not part of this checkpoint. Both repositories still use the existing local
environment/catalog setup; this is not a self-contained farm installation.

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
