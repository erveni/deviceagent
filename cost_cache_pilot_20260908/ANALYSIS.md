# Gemini cache pilot — 2026-09-08, pre-nightly partial run

FINAL: provider settlement complete, pilot PARTIAL (not ten completed jobs).
Before 39604.881585 MB; after 39580.175681 MB; billed 24.705904 MB including the
interrupted seventh attempt. Six accepted successes => 4.117651 MB/success,
80.365% below the previous 20.970692 MB successful single-job observation.
This is an observed cross-keyword pilot comparison, not a controlled fleet estimate.
Wrapper restored device-104 to v79 with accessibility healthy and tun0 absent.
No GOST process or fleet lock remained; full chain0906 stays disabled.

The authorized ten-ID pilot stopped at the 19:52 Asia/Manila deadline to protect
the scheduled 20:00 daily. Six accepted CSV successes: 399, 573, 564, 538, 357,
617. Keyword 340 started and returned its native answer but was interrupted
during screenshot processing; it is NOT counted as an accepted success.
Keywords 553, 589, and 372 did not start. Remaining IDs: [553,589,340,372].
Do not claim ten jobs completed or a 100% success rate for all initiated attempts.

## Quality and traffic evidence

Root personally viewed all six accepted final PNGs. Each shows the complete
three-business answer and the corresponding rank: 399=4/4, 573=4/4, 564=4/4,
538=1/3, 357=4/4, 617=2/3. Seven paid preparations passed the strict fresh-tab,
empty-cookie/origin-state checks. No internal/outer retries were enabled.
The six jobs span six businesses and six cities/states on device-104 only.
Provider targeting can fall back: kw617 used region, kw564 and kw340 used ZIP;
do not claim all exit IPs precisely matched the requested city.

| Keyword | Finished browser encoded MB | Disk/cache hits | Trace stopped |
|---|---:|---:|---|
| 399 | 4.819159 | 20 | yes |
| 573 | 2.139769 | 26 | yes |
| 564 | 2.491977 | 34 | yes |
| 538 | 1.084284 | 74 | yes |
| 357 | 2.054899 | 32 | yes |
| 617 | 1.766529 | 41 | yes |
| 340, interrupted | 0.315160 | 64 | no |

These are browser encoded bytes, NOT Evomi billed MB. Resource failures and
early attachment gaps exist; kw399 and kw617 each retain one unfinished request,
and kw340 has no clean trace-stop receipt. Do not count canceled browser requests
as failed ranking jobs or add browser bytes to the provider bill.

Compared with the earlier kw64 browser trace (2.045188 MB), kw399 transferred
2.773971 MB more: +2.260905 MB Gemini JavaScript and +0.437389 MB fonts, explaining
97.3% of the increase. This demonstrates cache-miss/asset-volume variation,
not that location caused different assets (sanitized traces omit asset paths).

## Limits and next work

This is warmed-cache, Gemini-only, selected for historical completion, on one
phone. A free direct-network smoke warmed the browser first. It is not a matched
daily-versus-ranking trial, randomized fleet estimate, or a cold-start test.
Other platforms/daily still fully clear Chrome and can erase the benefit.
The normal 60-second warmup was unchanged; savings cannot be credited to
shortening it. Full stale queue remains disabled; no fleet rollout is authorized
by this partial result. APK 82 was temporary on 104; wrapper must restore 79.

One FREE pre-check failed `unexpected_page_after_reset` before any job/proxy;
the retry passed, without a behavior change. That original receipt lacks target
identity evidence, so its exact cause is not proved. A post-pilot bounded
old-target teardown wait passed 18 offline tests separately and cannot receive
credit for this pilot's savings. It has not yet been re-tested on the phone.

The close-target acknowledgement and target-destroyed event are distinct in the
[Chrome Target protocol](https://chromedevtools.github.io/devtools-protocol/tot/Target/).
This supports a possible asynchronous close race, not proof of this occurrence.

Next: finish the four remaining IDs in a separate measured window; validate
first-cold versus warm cost and mixed-platform cache retention before deployment.
Never resume the full stale queue merely because this pilot is cheaper.
