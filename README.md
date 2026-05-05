# Device Agent

Android AccessibilityService agent that automates Chrome to run AI platform sessions (ChatGPT, Gemini, Perplexity). Receives commands via HTTP API on port 8765.

## How It Works

```
┌─────────────┐     HTTP POST      ┌──────────────────┐
│  Your Mac   │ ──────────────────▶│  Android Phone    │
│  (Python)   │  <phone-ip>:8765   │  (Accessibility   │
│             │◀────────────────── │   Service)        │
└─────────────┘     JSON response  └──────────────────┘
```

The phone runs a full HTTP server inside an AccessibilityService. It receives session commands and automates Chrome:
1. Reset Chrome (clear browsing data)
2. Navigate to AI platform (chatgpt.com, gemini.google.com, perplexity.ai)
3. Dismiss popups (login prompts, cookie banners)
4. Type the prompt into the input field
5. Submit and wait for AI response generation
6. Scroll through the response
7. Send follow-up question (optional)
8. Click backlinks in the response (optional)

**No ADB needed for sending commands** — the phone is a standalone HTTP server. ADB is only required for the proxy/VPN setup (socksdroid) which is optional for testing.

## Installation

### 1. Build the APK

```bash
cd device-agent
./gradlew assembleDebug
# APK at: app/build/outputs/apk/debug/app-debug.apk
```

### 2. Install on Phone

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Or transfer the APK to the phone and install directly.

### 3. Enable Accessibility Service

Settings → Accessibility → Installed apps → Device Agent → **ON**

This starts the HTTP server on port 8765.

## Sending Commands (No ADB Required)

Once installed and accessibility is enabled, the phone listens on port 8765 on the WiFi interface.

### Find the phone's IP

```bash
# On the phone: Settings → About → Status → IP address
# Or from Mac: ping the phone's hostname
```

### Ping the agent

```bash
curl http://<phone-ip>:8765/ping
# Response: {"pong": true}
```

### Run a session

```bash
curl -s -X POST http://<phone-ip>:8765/session \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "chatgpt",
    "prompt": "What is the best pizza in Brooklyn?",
    "followUp": "Any wood-fired options?",
    "backlinkDomain": "example.com"
  }'
```

### Check status

```bash
curl http://<phone-ip>:8765/status
# Response: {"status": "running", "platform": "chatgpt", "steps": "..."}
```

### API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ping` | GET | Health check. Returns `{"pong": true}` |
| `/status` | GET | Current/last session status, platform, steps |
| `/session` | POST | Start a new session (see body below) |
| `/mqtt/config` | POST | Configure MQTT broker for remote command dispatch |

### POST /session Body

```json
{
  "platform": "chatgpt|gemini|perplexity",
  "prompt": "The prompt text to send to the AI",
  "followUp": "Optional follow-up question after response",
  "backlinkDomain": "Optional domain to find and click in response"
}
```

### Session Flow

```
reset_chrome → navigate → dismiss_popups → input → submit → wait_generation → scroll → [follow_up] → [backlink]
```

Each step reports success/failure in the status response.

## Running Multiple Devices (Batch Mode)

The Python script `run_with_proxy.py` runs sessions across many devices in parallel using rolling dispatch:

```bash
python3 run_with_proxy.py <plan.json>
```

The plan JSON format:
```json
{
  "waves": [[
    {
      "platform": "chatgpt",
      "prompt": "...",
      "follow_up": "...",
      "backlinks": [{"url": "https://..."}],
      "client_id": 1,
      "keyword_text": "...",
      ...
    }
  ]]
}
```

Features:
- **Rolling dispatch**: jobs start immediately when a device is free (no waiting for slowest)
- **Per-job proxy**: fresh residential IP per job (gost + socksdroid + Decodo)
- **Campaign constraint**: no two jobs with same campaign run concurrently
- **Per-session CSV**: results saved after every session (crash-safe)
- **10 concurrent devices**: full utilization, no ADB bottleneck

## Requirements

- Android 7.0+ (API 24+)
- Chrome browser installed
- Accessibility Service enabled for Device Agent
- WiFi connection (for receiving HTTP commands)
- The phone must be unlocked (accessibility services work on unlocked screens)

## No-ADB Usage

The phone runs as a standalone HTTP server. Once the APK is installed and accessibility is enabled:

1. Connect phone to WiFi
2. Find phone IP: Settings → About Phone → Status → IP Address
3. Send HTTP requests directly to `<phone-ip>:8765`

No USB cable. No ADB. No wireless debugging. Just HTTP over WiFi.
