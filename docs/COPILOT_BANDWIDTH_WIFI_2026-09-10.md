# Copilot bandwidth: fresh-profile downloads and Wi-Fi preparation

## Second-phone checkpoint —05:09 Manila

Device106, same keyword5225, fresh Edge Wi-Fi settlement:

- APK86 attempt4:3.133920MB,0 successes. Real submitted/no-answer outcome.
- APK87 attempt5:0.655346MB,1 success, native screenshot reviewed (rank1/8,
  prompt excluded). Original79/accessibility/noVPN restored automatically.
- Attempt5 launcher errored AFTER success. Original report stays invalid;
  `copilot_bootstrap_wifi_20260910_device-106_attempt5_metered/recovered_settlement.json`
  records separate recovered measurement:29746.471228→29745.815882MB,16 stable
  readings across5minutes, no new job and no competing local proxy workload.
- New native guard confirms visible Network issues continuously for3seconds.
  It did not trigger on attempt5; success cannot be causally attributed to it.
- Host harness now executes a syntax-checked saved launcher, retains settlement
  despite nonzero launcher exit, and propagates wrapper failure correctly.
- This expands evidence to a second phone, NOT fleet-wide validation. Normal
  ranking launcher is fail-closed pending rollout, not enabled low-cost production.
  Keep stale queue paused. Daily production deployment also remains outstanding.

The preceding failure must count in economics: these two paid106 attempts total
3.789266MB for one finished pair, not0.655346MB including retries. Across the four
Wi-Fi-settled paid samples (two104 successes,106 failure+success), total4.959175MB
for3 successes =1.653058MB/success. This tiny selected sample is not a forecast.

Status at03:16 Manila: two automatically successful, settled low-cost samples.
Costs0.629016 and0.540893MB; average0.584955MB (~97% below19.652356MB control).
Both actual screenshots reviewed; both wrappers restored original79/accessibility/
noVPN. No fleet rollout or daily restart yet. The eight-run daily implementation
can now proceed; broader rollout is still a separate measured gate.

## What was measured

Same device104, keyword5225, Copilot, ZIP targeting, APK86, one attempt/no retries.
Each run clears Edge and prepares a fresh profile. Neither changes the delivered
YOKL report, which was already complete15/15.

| Measurement | Immediate proxy after reset | Wait for quiet Wi-Fi after reset |
|---|---:|---:|
| Evomi deduction |19.652356 MB|0.629016 MB|
| Successful answers / attempts |1/1|1/1|
| Actual screenshot reviewed |Yes, rank1/8|Yes, rank1/8|
| Gost lifetime |148.0 seconds|151.0 seconds|
| Paid-path cumulative bytes |about14.07 MB|0.404801 MB|
| Observed off-proxy Wi-Fi preparation bytes |Not recorded|14.874494 MB|

This matched pair shows **96.8% lower Evomi consumption**. It does not establish a
fleet-wide success rate, a monthly average, or reduced total internet traffic.
Preparation added approximately2.5minutes of ordinary Wi-Fi time. The paid proxy
duration barely changed; duration alone did not explain the large cost difference.

## Evidence and limits

- Immediate-proxy evidence: `copilot_bootstrap_trace_20260910_metered/report.json`
  and `candidate/{traffic_hosts,gost_phases}.jsonl`.
- Wi-Fi-settled evidence: `copilot_bootstrap_wifi_20260910_metered/report.json`,
  `candidate/offline_edge_kw5225.json`, CSV, and cumulative proxy counters.
- Both wrappers restored original APK79, accessibility enabled, no test VPN.
- Immediate-proxy trace:11.734250MB on HTTP port80 with unidentified hostname;
  1.943364MB from `edge.microsoft.com`;0.084736MB from `copilot.microsoft.com`.
  Do not label the unidentified HTTP download as MSN/news or a particular update.
  The next trace can identify HTTP Host as well as TLS SNI, without storing payloads.
- The new Wi-Fi wait observed bulk bursts of2.537MB,8.980MB and1.921MB before proxy
  connection. It then recorded51.2seconds without a large transfer.
- The earlier0.426MB terminal Gost ledger was incomplete: open sockets had not
  produced terminal records. Use cumulative counters including open connections.
  Never sum cumulative snapshots or add terminal and cumulative totals together.
- Evomi is account-wide, billing can lag, and target-tier billing can differ from
  socket bytes. The meter, not packet counts, is the cost comparison.

## Implemented, opt-in only

`tools/copilot_offline_bootstrap.py` performs the fresh Edge reset before Gost.
With `RANK_COPILOT_WIFI_SETTLE=1`, it samples wlan0 RX+TX every5seconds. It requires
at least150seconds and30seconds without a >16KB interval, with a300second limit.
Missing/reset counters, a VPN appearing, or continued bulk traffic abort before
the paid tunnel. It submits no AI prompt during this preparation.

The actual ranking still uses Evomi and its normal location setup. No security or
browser-update endpoints are blocked. `copilotEdgePrepared` avoids a second data
wipe after the proxy is connected. All trial switches remain off by default and
restricted to device104/Copilot; original fleet behavior and concurrency cap4 stay.

The passive observer preserves the original SOCKS route and DNS behavior; it is
not the earlier SNI-rewriting/DNS-bypass relay. It writes only destination hostname,
port and cumulative counts, not credentials, URLs, TLS contents or AI responses.

## Why not simply disable browser services?

Microsoft documents `edge.microsoft.com` and `*.dl.delivery.mp.microsoft.com` as
serving several browser support features, including component updates, certificate
revocation lists and protection data. Broad blocking could remove useful safeguards.
[Microsoft Edge endpoint documentation](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-security-endpoints).

Desktop advice is not automatically applicable to these phones: the documented
NewTabPageContentEnabled and BackgroundModeEnabled policies do not support Android.
[New-tab policy](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/newtabpagecontentenabled),
[background-mode policy](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/backgroundmodeenabled).

## Next gate

`copilot_bootstrap_wifi_confirm_20260910_wrapper/report.json` is complete. Its
meter report shows0.540893MB/one success,14.540680MB Wi-Fi preparation traffic,
and56.2seconds quiet before the paid proxy. Root reviewed its native PNG.
Implement/test daily/backend next; retain controlled rollout safeguards from
`TODO-ranking-and-daily-2026-09-10.md`. Do not extrapolate two samples to all phones.
