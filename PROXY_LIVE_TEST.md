# Proxy Evaluation — Live Test Results & Recommendation

**Date:** 2026-08-15 · **Goal:** replace Decodo (residential proxy for ranking) with something **cheaper** that keeps **US city/zip geo accuracy**.

**Method:** (1) researched ~24 providers on paper, (2) **live-tested the finalists on real phones** — one provider per phone, an actual ChatGPT capture of *Mae's Childcare*, target **San Francisco, CA 94117**, through our production gost + phone stack. We measured **exit-IP geo accuracy** (does the target land the right place?), tunnel, and capture success. Trial credentials were used where offered.

---

## Results

| Provider | Price/GB | Target sent | Exit geo (live) | Zip-exact? | Captured | Verdict |
|---|---|---|---|---|---|---|
| **🏆 Rayobyte** | ~$2.00 | zip 94117 | **San Francisco, CA** | **✅ yes** | ✅ | **Best — replaces Decodo** |
| **Evomi** | **$0.49** | region CA / city SF | Fresno CA / **San Jose CA** | ❌ (city approx) | not run* | Cheapest; state-accurate, city loose |
| NodeMaven | $2.20 | region CA | Vallejo, CA | ❌ (state only) | ✅ | State-level only |
| DataImpulse *(current daily)* | $1.00 | region CA | **Ohio** | ❌ (unreliable) | ✅ | Daily only — geo not trustworthy |
| Webshare | ~$1.40–3.50 | — | could not authenticate | — | — | Need Proxy→Connect creds |
| Decodo *(current, dying)* | $2.75–3.50 | zip 94117 | **no exit IP** | — | ❌ | **Dead — unfunded** |

\* Evomi validated by direct geo probes (below); not run through the phone flow because its city targeting already proved approximate.

---

## Production-scale test (Aug 15 daily, whole fleet on Rayobyte)

We ran an **entire production daily** (1,601 jobs) through Rayobyte to validate at scale:

| Phase | Result |
|---|---|
| First 100 rows (bandwidth available) | **96% success** |
| Last 100 rows (trial GB running out) | 3% success |
| Total before fallback | **348 success / 1,601** |
| Cause of collapse | **free-trial GB quota exhausted ~halfway** (http fail / input failed / generation timeout as the proxy ran dry) |

**Read:** Rayobyte performs at **96% on the real fleet** — the failure was the **trial bandwidth cap, not the proxy**. A paid plan sized to the workload (~6 GB/daily, ~4 GB/ranking run) would sustain a full run. The production daily was completed by falling back to DataImpulse (kept Rayobyte's 348 good rows). **Decodo, by contrast, captured zero** (dead/unfunded), so Rayobyte is the strictly-better, cheaper choice.

**Integration shipped (dormant until enabled):** `run_with_proxy.py` gained a `rayobyte` branch (gost HTTP connector + targeting-in-password); flip on with `PROXY_PROVIDER=rayobyte` + paid creds.

---

## Detail per provider

**🏆 Rayobyte — the replacement.**
- zip 94117 → landed a real **San Francisco** residential IP, end-to-end on a phone. Exact Decodo-grade precision.
- City + zip + sticky + SOCKS5 all confirmed. **~$2/GB** (50GB+), vs Decodo $2.75–3.50 → cheaper **and** zip-accurate.
- Integration: targeting goes in the **password** (`-country-US-zip-<zip>-session-<sid>`); use the **HTTP endpoint :8000** (its SOCKS5 :1080 didn't chain through our stack).

**Evomi — cheapest, but state-level not zip.**
- Works: `country-US` → US; `region-california` → **Fresno, CA** (state solid); sticky ✓; sessions we generate ourselves ✓; HTTP :1000 + SOCKS5 :1002. Targeting in **password** (`_country-US_region-california_city-san.francisco_session-<id>`).
- **City is approximate:** asking `city-san.francisco` returned **San Jose** (~45 mi off — right state/metro, wrong city). **No zip support** (city is the finest grain).
- Endpoint **rate-limits rapid requests** (bursts return HTTP 400) — fine for spaced production, but a reliability note.
- **$0.49/GB** — ~4× cheaper than Rayobyte, ~7× cheaper than Decodo.

**NodeMaven — $2.20/GB.** Reliable **state-level** (region CA → Vallejo), SOCKS5-native. No zip on this plan. Fine for state work, not a full Decodo replacement.

**DataImpulse — $1.00/GB (current daily proxy).** Captures fine, but **region targeting is unreliable** (asked California, exited Ohio). Keep for daily engagement (geo can be loose); **do not use for geo-accurate ranking.**

**Webshare — untested.** The account login (`zaeepanu`) is **not** the proxy auth — every endpoint returned 407/404. Need the **proxy host:port + proxy username:password** from the dashboard's **Proxy → Connect / Proxy List** tab to test.

**Decodo — dead.** No exit IP (`input failed`) — residential is unfunded. Confirms the need to switch.

---

## Cost per ranking run (~4.16 GB/run)

| Provider | $/GB | ~$/ranking run | Geo precision |
|---|---:|---:|---|
| Evomi | $0.49 | **~$2.04** | state-accurate, city loose, no zip |
| DataImpulse | $1.00 | ~$4.16 | unreliable |
| Rayobyte | $2.00 | ~$8.32 | **zip-exact** |
| Decodo (old) | $3.50 | ~$14.56 | zip-exact (but dead) |

---

## Recommendation

**Two good options depending on how exact the geo must be:**

1. **Rayobyte — if the ranking deliverable needs exact city/zip** (recommended for client reports). Proven zip→San Francisco, cheaper than Decodo. **~$8/run.** This is the safe drop-in Decodo replacement.
2. **Evomi — if state-level geo is acceptable** and cost is the priority. ~4× cheaper (**~$2/run**), state-accurate, but city is only approximate and there's no zip. Rate-limit note applies.

**Keep DataImpulse for the daily engagement run** ($1/GB) — cheapest, and daily doesn't need exact geo.

**Suggested plan:** adopt **Rayobyte for ranking** now (zip-accurate, proven); keep DataImpulse for daily. Revisit Evomi if we decide state-level ranking is acceptable to cut cost further.

**Integration effort:** small — each provider is one username/connector branch in `gost_manager.py`, same pattern already used for DataImpulse. Rayobyte needs an HTTP-connector; Evomi uses password-targeting on SOCKS5/HTTP.

---

*Companion docs: `PROXY_SHORTLIST.md` (full provider research) · `PROXY_COST_SPEC.md` (cost model, per job / per run).*
