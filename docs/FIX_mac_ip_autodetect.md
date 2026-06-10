# Fix: auto-detect the Mac's LAN IP (SocksDroid → gost host)

## The bug this fixes
The phones run all traffic through the Mac via **SocksDroid (phone VPN) → gost (on the Mac) →
Decodo → target site**. SocksDroid dials the Mac at `run_with_proxy.py:MAC_IP`, which used to be
**hardcoded** (`192.168.0.102`).

When the Mac's LAN IP changed (DHCP moved it `192.168.0.102 → 192.168.0.105` on 2026-06-10), every
phone was dialing a **dead host**. Symptom: **"This site can't be reached" on every phone** and
**`input failed` / 0% success on every job** — for **both the daily and the ranking** (both paths call
`run_with_proxy.socksdroid_connect`, which uses `MAC_IP`).

Telltale: the Mac's own internet (`curl https://ifconfig.me`) and Decodo handshakes both work fine,
but every phone job fails — i.e. the **phone → Mac-gost leg** is pointed at the wrong address.

## The fix
`run_with_proxy.py` now **auto-detects** the Mac's LAN IP instead of hardcoding it:

```python
MAC_IP = os.environ.get("MAC_IP") or _detect_mac_lan_ip()   # ipconfig getifaddr en0/en1; .102 fallback
```

- Picks up the live LAN IP on every run → a DHCP change can't break the fleet again.
- `MAC_IP=<ip>` env var overrides if you ever need to force it.
- Falls back to `192.168.0.102` only if auto-detect returns nothing.

Because both runners import `socksdroid_connect`/`MAC_IP` from `run_with_proxy`, this single fix
covers **daily (`run_rolling_plan.py`) and ranking (`audit_dispatch_http.py`)**.

## How to run (with the fix)
No new steps — just run as normal; `MAC_IP` resolves itself.

**Verify the Mac IP it will use:**
```bash
python3 -c "from run_with_proxy import MAC_IP; print(MAC_IP)"   # should equal:
ipconfig getifaddr en0                                         # the Mac's current LAN IP
```

**Daily (residential, rolling, 10 phones):**
```bash
cd device-agent
MAX_PARALLEL=10 DEVICE_EXCLUDE="<down phones>" ./run_daily_auto.sh <DATE>
# or force the host explicitly: MAC_IP=192.168.0.105 ./run_daily_auto.sh <DATE>
```

**Ranking:**
```bash
./run_ranking_auto.sh <DATE> never_ranked     # same MAC_IP auto-detect applies
```

## If "site can't be reached" ever returns — quick triage
1. **Mac IP moved?** `python3 -c "from run_with_proxy import MAC_IP;print(MAC_IP)"` vs
   `ipconfig getifaddr en0`. With this fix they should match; if not, `export MAC_IP=<ip>`.
2. **SocksDroid stuck on a dead gost after a halt** → force-stop it so phones aren't routed through a
   dead port: `adb -s "<serial>" shell am force-stop net.typeblog.socks` (do this on every phone when
   you stop a run).
3. **Phones missing from `adb devices` or showing `… (2)._adb-tls-connect._tcp`** = wireless-adb/mDNS
   churn (often the same Wi-Fi event that moved the Mac IP). Phones that reconnect under a `(2)` name
   need their serial updated in `run_with_proxy.py:DEVICES`; phones gone entirely need a physical
   wake / Wi-Fi check.

## Scope of this branch
Contains **only** the `MAC_IP` auto-detect change. Network-specific tweaks (e.g. temporary `(2)`
device serials) are intentionally NOT included — they differ per Mac/fleet.
