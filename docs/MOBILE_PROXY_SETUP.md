# Mobile Proxy Setup (SocksDroid → sni_relay → gost → Decodo)

How the 10-phone fleet routes each Android phone's traffic through a **mobile**
(not residential) proxy so AI platforms (ChatGPT / Gemini / Perplexity) see a
real US mobile IP at the target geo.

This is the chain the daily sessions and ranking audits run on. If you're
onboarding a new Mac into the fleet, this is the doc.

---

## 1. The problem this solves

We drive real Android phones via `adb`. Each phone must reach the AI platforms
from a **US mobile IP geolocated to the business being audited** — otherwise the
ranking/answer reflects the wrong location.

Two hard constraints make this non-trivial:

1. **SocksDroid (tun2socks) can only IP-CONNECT.** It resolves DNS locally (on
   the phone's real network, e.g. the Philippines) and asks the upstream SOCKS
   proxy to connect to a **raw IP**.
2. **Mobile Decodo rejects IP-CONNECT** to non-anycast destinations
   (`0x02 not allowed by ruleset` / `0x03 host unreachable`). It also can't
   route to geo-specific Google edge IPs. Net result on the phone:
   *"site can't be reached"*.

The fix is a small **SNI-rewriting relay** that sits between the phone and the
proxy, recovers the real hostname from the TLS handshake, and re-dials the
upstream **by hostname** (so DNS resolution happens at the Decodo US exit).

---

## 2. The chain

```
┌─────────────────────────┐
│  Android phone          │
│  ┌───────────────────┐  │   SOCKS5, IP-CONNECT
│  │ SocksDroid (VPN)  │──┼────────────────────────────┐
│  │ tun2socks, routes │  │   to MAC_IP:<phone_port>    │
│  │ ALL phone traffic │  │                             │
│  └───────────────────┘  │                             ▼
│  ┌───────────────────┐  │                  ┌─────────────────────────┐
│  │ device-agent APK  │  │                  │  Mac: sni_relay.py      │
│  │ HTTP :8765        │◄─┼── adb forward ───│  listens :<phone_port>  │
│  │ (browser flows)   │  │   8765→8765+i    │  peeks TLS ClientHello  │
│  └───────────────────┘  │                  │  → recovers SNI host    │
└─────────────────────────┘                  └───────────┬─────────────┘
                                                          │ SOCKS5, hostname-CONNECT
                                                          ▼
                                              ┌─────────────────────────┐
                                              │  Mac: gost              │
                                              │  listens :<phone_port+  │
                                              │         GOST_PORT_OFFSET>│
                                              │  chains to Decodo with  │
                                              │  per-session creds      │
                                              └───────────┬─────────────┘
                                                          │ SOCKS5 + session user
                                                          ▼
                                              ┌─────────────────────────┐
                                              │  Decodo mobile gateway  │
                                              │  gate.decodo.com:7000   │
                                              │  resolves host at US    │
                                              │  exit, geo = target zip │
                                              └─────────────────────────┘
```

**One sentence:** the phone's VPN sends everything to a per-phone relay on the
Mac, the relay rewrites the connect to use a hostname, gost wraps it with the
phone's Decodo session credentials, and Decodo exits from a US mobile IP at the
requested geo.

**Why the relay matters:** `hostname-CONNECT` to `gemini.google.com` returns
`200` where `IP-CONNECT` fails. Non-TLS / no-SNI connections fall back to plain
IP-CONNECT, so nothing else breaks.

---

## 3. Port scheme (per phone slot `i`, 0-based)

| Component | Port | Notes |
|---|---|---|
| Phone-facing relay listener | `BASE_GOST + i` = `11001 + i` | what SocksDroid connects to |
| gost listener (upstream) | `BASE_GOST + i + GOST_PORT_OFFSET` = `11101 + i` | only the relay talks to it |
| device-agent app on phone | `8765` | `adb forward tcp:(8765+i) tcp:8765` |

So phone 0 → relay `:11001` → gost `:11101`; phone 9 → relay `:11010` → gost
`:11110`. With `USE_SNI_RELAY=0` the relay is skipped and gost listens directly
on `11001+i` (legacy residential path).

---

## 4. Prerequisites

### Mac (per fleet host)
```bash
# gost (SOCKS5 multiplexer/chainer)
brew install go-gost/gost/gost          # or: brew install gost
which gost                              # → /opt/homebrew/bin/gost

# Python deps for the relay
pip3 install PySocks                    # provides `import socks`

# adb
brew install --cask android-platform-tools
```

### Each phone (Android 13+)
1. Install **SocksDroid** — package `net.typeblog.socks` (the tun2socks VPN app).
2. Install the **device-agent APK** and enable its AccessibilityService
   (Settings → Accessibility → DeviceAgent). See repo `SETUP.md`.
3. Connect to the Mac over adb (Wi-Fi pairing / mDNS-TLS, or `adb connect <ip:port>`).
4. Phone and Mac must be on the **same LAN** as `MAC_IP` (below).

### Decodo
A **mobile** Decodo account. Gateway: `gate.decodo.com:7000` (mobile; `10001`
was the old residential port). You need the proxy username + password.

---

## 5. Configuration (env vars)

All set via environment; defaults shown. The runner sources `.env.dev` first
(`set -a; source .env.dev; set +a`).

| Env var | Default | What it is |
|---|---|---|
| `MAC_IP` | `192.168.0.102` | **EDIT THIS** — the fleet host's LAN IP that phones dial. Set in `run_with_proxy.py`. |
| `GOST_BIN` | `/opt/homebrew/bin/gost` | gost binary path |
| `PROXY_HOST` | `gate.decodo.com` | Decodo gateway host |
| `PROXY_PORT` | `7000` | Decodo **mobile** port (residential was 10001) |
| `PROXY_USER` | *(empty)* | **REQUIRED** — Decodo username. Empty ⇒ every job dies with TLS RST. |
| `PROXY_PASS` | *(empty)* | **REQUIRED** — Decodo password |
| `PROXY_TARGET` | `country-us` | geo target, e.g. `country-us`, `asn-21928` (T-Mobile), `asn-20057` (AT&T) |
| `PROXY_DURATION` | `60` | Decodo sticky session minutes |
| `USE_SNI_RELAY` | `1` | `1` = mobile (relay on); `0` = legacy residential (gost direct) |
| `GOST_PORT_OFFSET` | `100` | gap between relay port and gost port |
| `BASE_GOST` | `11001` | first phone slot's relay port (constant in code) |
| `MAX_PARALLEL` | `3` (rolling) | concurrent phones — **set `10` for the full fleet** |

### Sample `.env.dev` (gitignored — create per host)
```bash
# Decodo MOBILE proxy
PROXY_HOST=gate.decodo.com
PROXY_PORT=7000
PROXY_USER=user-xxxxxxxxxx          # ← your Decodo mobile username
PROXY_PASS=xxxxxxxxxxxxxxxx          # ← your Decodo mobile password

# (only if also driving the RabbitMQ consumer)
RABBITMQ_HOST=...
RABBITMQ_USERNAME=...
RABBITMQ_PASSWORD=...
ADMIN_BASE=https://<aeoadmin-host>
```

The per-job Decodo session username is built automatically as:
```
{PROXY_USER}-session-{sid}-sessionduration-{PROXY_DURATION}-{PROXY_TARGET}
```
e.g. `user-spx491gvtx-session-4k2tbyp4ad-sessionduration-60-country-us`.

### Device list — `run_with_proxy.py` `DEVICES`
Maps each `device-1NN` slot to its **adb serial**. Edit for your fleet:
```python
DEVICES = [
    ("device-101", "adb-R83L112EVWK-PydBnX._adb-tls-connect._tcp"),  # mDNS-TLS serial
    ("device-106", "192.168.0.165:34779"),                           # or a TCP/IP serial
    # ...
]
```
> **Gotcha:** mDNS serials drift on reconnect (the random suffix and the
> macOS `(2)` collision marker change). If a phone shows offline but is in
> `adb devices`, re-copy its current serial here. Serials with `(2)` MUST be
> shell-quoted: `adb -s "<serial>"`.

---

## 6. How a phone gets connected (what the runner does per job)

```bash
# 1. Mac side: start gost (listens 11101+i, chains to Decodo) + relay (listens 11001+i)
#    — done by gost_start() which writes /tmp/gost_<pid>_<port>.yaml

# 2. Point the phone's SocksDroid VPN at the Mac relay:
adb -s "<serial>" shell am force-stop net.typeblog.socks
adb -s "<serial>" shell appops set net.typeblog.socks ACTIVATE_VPN allow
adb -s "<serial>" shell am start -n net.typeblog.socks/.AdbStartActivity \
  -a net.typeblog.socks.ACTION_START_VPN \
  --es SOCKSSERV "<MAC_IP>" --ei SOCKSPORT <11001+i> \
  --es SOCKSUNAME "anon" --es SOCKSPASSWD "anon" \
  --es SOCKSDNS "8.8.8.8" --es SOCKSROUTE "all"
```
`anon/anon` are placeholder SOCKS creds — the relay accepts any (the real auth
is Decodo's, applied at the gost hop).

### Sample generated gost config (`/tmp/gost_<pid>_<port>.yaml`)
```yaml
services:
  - name: s0
    addr: ":11101"                       # gost listener (relay dials this)
    handler: {type: socks5, chain: c0, auth: {username: anon, password: anon}}
    listener: {type: tcp}
chains:
  - name: c0
    hops:
      - name: h0
        nodes:
          - name: d0
            addr: gate.decodo.com:7000
            connector:
              type: socks5
              auth: {username: "user-...-session-...-country-us", password: "<PROXY_PASS>"}
            dialer: {type: tcp}
```

---

## 7. Running it

```bash
cd device-agent
set -a; source .env.dev; set +a       # MANDATORY — loads PROXY_USER/PASS
export PROXY_TARGET=country-us
export MAX_PARALLEL=10                 # use all 10 phones (default is 3)

# Wave-based fleet runner (production daily):
python3 run_with_proxy.py /path/to/daily_plan.json

# Rolling runner (1 IP per job, no wave barrier):
python3 run_rolling_plan.py /path/to/daily_plan.json
```

Validate one phone end-to-end before a full run:
```bash
# After the runner brings a phone up, the relay/gost preflight curls ifconfig.me.
# A healthy slot logs:  [preflight-ip] ... rc=0 ... <a US mobile IP>
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every job fails instantly, `RuntimeError: gost died … bind: address already in use` | Orphaned `sni_relay`/`gost` from a previous run hold ports 11001–11110 | `pkill -f sni_relay.py ; pkill -f 'gost -C'` **before** every run. Killing gost alone is NOT enough — sni_relay is a separate process. |
| Every job dies with TLS RST | `PROXY_USER` empty (forgot `source .env.dev`) | `set -a; source .env.dev; set +a`; verify `ps -p <pid> -E | tr ' ' '\n' | grep PROXY_USER` |
| `RuntimeError: sni_relay died` | PySocks missing, or port already bound | `pip3 install PySocks`; check `/tmp/sni_relay_<port>.log` |
| Phone "site can't be reached", Gemini blank | `USE_SNI_RELAY=0` on mobile Decodo (IP-CONNECT rejected) | Set `USE_SNI_RELAY=1` (default) |
| A phone never gets jobs though it's in `adb devices` | `DEVICES` serial doesn't match live adb (mDNS drift / TCP reconnect) | Re-copy the current serial into `DEVICES` |
| Runner only uses 3 phones | `MAX_PARALLEL` unset | `export MAX_PARALLEL=10` |
| Audits all route to NY zip 10001 | Non-catalog business with unparsed address (see `audit_dispatch_http.py`) | Ensure business `publishedAddress` is `Street, City, ST 12345` (comma before state) |

**Cleanup before any wave (copy/paste):**
```bash
pkill -f run_rolling_plan ; pkill -f run_with_proxy ; pkill -f sni_relay.py ; pkill -f 'gost -C'
sleep 2
lsof -nP -iTCP:11001-11110 -sTCP:LISTEN     # must be empty
adb devices                                 # confirm fleet count
```

---

## 9. Files

| File | Role |
|---|---|
| `run_with_proxy.py` | wave runner; `gost_start`/`gost_stop`, `socksdroid_connect`, `DEVICES`, port scheme |
| `run_rolling_plan.py` | rolling runner (1 IP/job) |
| `sni_relay.py` | the SNI-rewriting SOCKS5 relay (`python3 sni_relay.py <listen_port> <gost_port>`) |
| `audit_dispatch_http.py` | ranking-audit dispatch + per-business geo/zip resolution |
| `.env.dev` | per-host secrets (gitignored) — create from §5 sample |

---

*Architecture: SNI-rewriting relay landed in commit `77790c1`
(`feat: SNI-rewriting relay for mobile Decodo + round-robin device acquire`).*
