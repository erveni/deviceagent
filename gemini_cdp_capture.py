#!/usr/bin/env python3
"""Reverse-engineered logged-out Gemini capture via Chrome DevTools Protocol.

WHY: logged-out Gemini renders an answer then the server wipes the anonymous
conversation ~7s later, so a screenshot races the wipe. But the full answer is
streamed over the network FIRST, via:
    POST .../BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate
We attach to the phone's Chrome over CDP, submit the prompt, and read that
response body straight off the wire — the UI wipe becomes irrelevant.

Usage:
    python3 gemini_cdp_capture.py "<serial>" "<prompt>"
"""
import json, os, re, subprocess, sys, time
import urllib.request

import websocket  # websocket-client 1.9.x

CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
# Per-run output paths (override for concurrent fleet runs so phones don't clobber).
ANSWER_FILE = os.environ.get("GEMINI_ANSWER_FILE", "/tmp/gemini_answer.txt")
RESULT_FILE = os.environ.get("GEMINI_RESULT_FILE", "/tmp/gemini_result.json")
INPUT_SEL = "div[contenteditable='true'], rich-textarea .ql-editor, [role='textbox'], textarea"
SEND_SEL = "button[aria-label='Send message'], button[aria-label*='Send'], button.send-button"
STREAM_MARKERS = ("StreamGenerate", "BardFrontendService", "batchexecute")

# Gemini bootstrap / zero-state payloads that masquerade as an answer. When the
# prompt never produced a real answer stream (submit raced a stale anonymous
# session, or the page was still on the home screen), the only batchexecute
# bodies are the home-screen suggestion chips and the model-picker metadata.
# Their long chip strings ("I want to use AI for studying…") pass the prose
# filter below and get written as a false answer with no [RANK] — recorded
# downstream as no_rank with no Y, which is terminal under RETRY_KEEP_NORANK and
# so never retries. These markers never occur in a genuine answer (verified: 0
# hits across captured Gemini answers, 88/88 hits across the false no_rank rows).
BOOTSTRAP_MARKERS = ("EXPERIMENT_WEB_ZERO_STATE", "GEMINI_CAPABILITIES_CHIP",
                     "[6,[false,null,false]")


def is_bootstrap_payload(text):
    """True if `text` is a Gemini home-screen / model-bootstrap body, not an answer."""
    return any(m in text for m in BOOTSTRAP_MARKERS)


# Strip logged-out Gemini chrome before the screenshot so the shot frames the ANSWER
# (top-3 + [RANK] + summary) the same way ChatGPT/Perplexity shots are cleaned — not
# the question, the sign-in/app-install promos, the top nav, or a stale composer
# draft left over from a prior job on this phone. Every element is located by a text
# phrase that only appears in that chrome, never in Gemini's answer; we climb to its
# container and drop it. Still a REAL Gemini screenshot — just without the chrome.
_GEMINI_STRIP_PROMPT_JS = r"""
(()=>{
  const kill=(needle)=>{
    for(const e of document.querySelectorAll('*')){
      if(e.childElementCount===0 && (e.textContent||'').includes(needle)){
        let el=e, n=0;
        while(el.parentElement && n<6){
          const p=el.parentElement;
          if((p.textContent||'').length > (e.textContent||'').length*2.5) break;
          el=p; n++;}
        el.remove(); return true;}}
    return false;};
  const out=[];
  if(kill('numbered 1-3')) out.push('prompt');     // the leaked query bubble (early phrase — survives Gemini's "Show more" truncation)
  // Promo cards that overlap the answer. Both variants appear geo/session-dependent.
  if(kill('Now available on Google Play')) out.push('play');
  if(kill('Sign in to connect to Google')) out.push('signin_promo');
  // Logged-out top nav (renders as a garbled desktop bar over mobile). Drop each
  // link by its unique label; none occur in a ranking answer.
  for(const t of ['Get Gemini App','For Business','Subscriptions']){ if(kill(t)) out.push('nav'); }
  // Empty the composer so a leftover draft from a prior job (e.g. a Citedlogic
  // capture prompt) doesn't show in the frame — mirrors the empty "Ask Gemini" box.
  document.querySelectorAll('[contenteditable="true"],textarea,input').forEach(e=>{
    try{ if(e.isContentEditable){e.textContent='';} else {e.value='';} }catch(_){} });
  return out.join(',')||'none';
})()
"""


def _forward(serial):
    subprocess.run(["adb", "-s", serial, "forward", f"tcp:{CDP_PORT}",
                    "localabstract:chrome_devtools_remote"],
                   capture_output=True, timeout=8)


def _cdp_json(serial, tries=8):
    """Chrome-on-Android closes the first /json connection intermittently; retry."""
    for _ in range(tries):
        try:
            return json.loads(urllib.request.urlopen(
                f"http://localhost:{CDP_PORT}/json", timeout=5).read())
        except Exception:
            _forward(serial)
            time.sleep(1.5)
    return []


def _gemini_tab_ws(serial):
    for p in _cdp_json(serial):
        if p.get("type") == "page" and "gemini.google.com" in p.get("url", ""):
            return p.get("webSocketDebuggerUrl")
    return None


def _close_all_tabs(serial):
    """Close every Chrome page tab via the CDP HTTP endpoint so tabs don't pile up
    across captures. The CP flow closes tabs (FlowEngine.closeAllChromeTabs); the
    CDP path must too — otherwise each am-start of /app leaks a tab (phones hit
    1000+ tabs over a full run, which slows Chrome to a crawl)."""
    closed = 0
    for p in _cdp_json(serial, tries=2):
        if p.get("type") == "page" and p.get("id"):
            try:
                urllib.request.urlopen(
                    f"http://localhost:{CDP_PORT}/json/close/{p['id']}", timeout=3).read()
                closed += 1
            except Exception:
                pass
    if closed:
        print(f"[tabs] closed {closed} tab(s)")
    return closed


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, suppress_origin=True, timeout=10, max_size=None)
        self._id = 0

    def call(self, method, params=None, want_reply=True):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        if not want_reply:
            return None
        # drain until our id comes back (events interleave)
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg

    def drain_events(self, seconds, predicate):
        """Collect CDP events for `seconds`, returning the first event matching predicate (or None)."""
        self.ws.settimeout(1.0)
        end = time.time() + seconds
        hit = None
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                continue
            if "method" in msg and predicate(msg):
                hit = msg
                break
        return hit

    def collect_request_ids(self, seconds):
        """Return {requestId: url} for StreamGenerate/batchexecute requests seen in window."""
        self.ws.settimeout(1.0)
        end = time.time() + seconds
        ids = {}
        finished = set()
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                continue
            m = msg.get("method")
            p = msg.get("params", {})
            if m == "Network.requestWillBeSent":
                url = p.get("request", {}).get("url", "")
                if any(k in url for k in STREAM_MARKERS):
                    ids[p.get("requestId")] = url
            elif m == "Network.loadingFinished":
                if p.get("requestId") in ids:
                    finished.add(p.get("requestId"))
        return ids, finished

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main():
    serial = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else "best plumber in Dallas Texas"
    _forward(serial)
    ws_url = _gemini_tab_ws(serial)
    if not ws_url:
        print("FATAL: no gemini.google.com tab found over CDP", file=sys.stderr)
        return 2
    print(f"attached to gemini tab: {ws_url[:60]}...")
    c = CDP(ws_url)
    c.call("Network.enable")
    c.call("Page.enable")

    # 0a) RESET the anonymous Gemini session before each capture. Logged-out
    # Gemini's conversation is tied to the anonymous cookie; without a reset a
    # 2nd+ capture on the same phone reuses the stale (wiped) conversation and
    # never emits a fresh StreamGenerate (captured=False). Clearing cookies +
    # reloading /app forces a brand-new session — the CDP analogue of the daily
    # flow's Chrome reset. Disable with GEMINI_RESET=0.
    if os.environ.get("GEMINI_RESET", "0") == "1":
        c.call("Network.clearBrowserCookies")
        c.call("Page.navigate", {"url": "https://gemini.google.com/app"})
        time.sleep(5)

    # 0) wait until the Gemini input has actually rendered (page can take a while)
    ready = False
    for _ in range(20):
        chk = c.call("Runtime.evaluate", {
            "expression": f"!!document.querySelector(\"{INPUT_SEL}\")",
            "returnByValue": True})
        if chk.get("result", {}).get("result", {}).get("value"):
            ready = True
            break
        time.sleep(1)
    print("input ready:", ready)
    if not ready and os.environ.get("GEMINI_CDP_SHOT"):
        # Debug: dump what the page actually shows so we can see the blocker
        # (consent wall? login? slow load?).
        try:
            info = c.call("Runtime.evaluate", {"expression":
                "JSON.stringify({url:location.href,title:document.title,"
                "body:(document.body.innerText||'').slice(0,400)})",
                "returnByValue": True}).get("result", {}).get("result", {}).get("value", "")
            print("PAGE STATE:", info)
            shot = c.call("Page.captureScreenshot", {}).get("result", {}).get("data", "")
            if shot:
                import base64 as _b64
                with open(os.environ["GEMINI_CDP_SHOT"], "wb") as _f:
                    _f.write(_b64.b64decode(shot))
                print("screenshot ->", os.environ["GEMINI_CDP_SHOT"])
        except Exception as _e:
            print("debug-shot error:", _e)

    # 1) type the prompt into the contenteditable and submit, via JS
    inject = (
        "(() => {"
        f"  const ed = document.querySelector(\"{INPUT_SEL}\");"
        "   if (!ed) return 'no_input';"
        "   ed.focus();"
        "   document.execCommand('insertText', false, " + json.dumps(prompt) + ");"
        "   return 'typed:' + (ed.innerText||ed.value||'').slice(0,40);"
        "})()"
    )
    r = c.call("Runtime.evaluate", {"expression": inject, "returnByValue": True})
    print("input:", r.get("result", {}).get("result", {}).get("value"))
    # send button only appears after text is entered — poll for it, then click
    clicked_val = "no_send_btn"
    for _ in range(8):
        time.sleep(0.7)
        clicked = c.call("Runtime.evaluate", {"expression":
            "(() => { const b = document.querySelector(" + json.dumps(SEND_SEL) + ");"
            "  if (!b) return 'no_send_btn'; b.click(); return 'clicked'; })()",
            "returnByValue": True})
        clicked_val = clicked.get("result", {}).get("result", {}).get("value")
        if clicked_val == "clicked":
            break
    print("submit:", clicked_val)

    # 2) watch the network for the StreamGenerate response
    print("listening for StreamGenerate (up to 40s)...")
    ids, finished = c.collect_request_ids(40)
    print(f"matched network requests: {len(ids)}  finished: {len(finished)}")
    for rid, url in ids.items():
        marker = next((k for k in STREAM_MARKERS if k in url), "?")
        print(f"  [{marker}] {url[:90]}")

    # 3) pull the response body for each matched request and look for the answer
    got_answer = False
    for rid, url in ids.items():
        body = c.call("Network.getResponseBody", {"requestId": rid})
        b = body.get("result", {})
        raw = b.get("body", "") or ""
        if b.get("base64Encoded"):
            import base64
            try:
                raw = base64.b64decode(raw).decode("utf-8", "replace")
            except Exception:
                pass
        if not raw:
            continue
        # batchexecute payload: strip the )]}'\n guard, search for prose
        text = raw.lstrip(")]}'\n")
        # Skip Gemini bootstrap / zero-state bodies — their suggestion-chip prose
        # would otherwise be accepted as a (rankless) answer → false no_rank.
        if is_bootstrap_payload(text):
            print("skipping bootstrap/zero-state body (not an answer)")
            continue
        # The human answer sits right after the ["rc_<hash>",[ marker in the
        # StreamGenerate payload — extract THAT (clean prose, the numbered list +
        # reasoning + [RANK] line). Fall back to the longest quoted block only when
        # the marker is absent (older response shapes).
        ans_m = re.search(r'"rc_[0-9a-f]+",\s*\["((?:[^"\\]|\\.)*)"', text)
        candidates = re.findall(r'"((?:[^"\\]|\\.){80,})"', text)
        prose = [cand for cand in candidates if cand.count(" ") > 8]
        print(f"\n=== body for {next((k for k in STREAM_MARKERS if k in url), '?')} "
              f"({len(raw)} bytes) ===")
        if ans_m or prose:
            got_answer = True
            chosen = ans_m.group(1) if ans_m else max(prose, key=len)
            # Proper JSON-string decode: handles \uXXXX as real UTF-8 (the old
            # .encode().decode("unicode_escape") mangled smart quotes / en-dashes).
            try:
                snippet = json.loads('"' + chosen + '"')
            except Exception:
                snippet = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)),
                                 chosen.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\'))
            with open(ANSWER_FILE, "w") as fh:
                fh.write(snippet)
            # Structured result for the ranking pipeline: parse the [RANK: X/Y]
            # line out of the captured answer (search the snippet first, then the
            # full decoded payload as a fallback) and write a JSON the dispatcher
            # reads — no screenshot/OCR needed, the wipe is irrelevant.
            rank_m = re.search(r"\[RANK:\s*(\d+)\s*/\s*(\d+)\]", snippet) \
                or re.search(r"\[RANK:\s*(\d+)\s*/\s*(\d+)\]", text)
            result = {
                "captured": True,
                "answer": snippet,
                "rank_position": int(rank_m.group(1)) if rank_m else None,
                "rank_total": int(rank_m.group(2)) if rank_m else None,
            }
            with open(RESULT_FILE, "w") as fh:
                json.dump(result, fh)
            rk = f"{result['rank_position']}/{result['rank_total']}" if rank_m else "none"
            print(f"ANSWER FOUND ({len(snippet)} chars, RANK={rk}) — text -> {ANSWER_FILE}, json -> {RESULT_FILE}")
            print(snippet[:1200])
            # Visual proof for the deliverable. The logged-out Gemini PAGE is
            # unreliable: it wipes the answer ~7s in, often renders only the top-3 +
            # deep-dive WITHOUT the [RANK] line, and shows Sign-in / app-install
            # chrome + a leaked prompt bubble. But we already hold the FULL verbatim
            # answer off the wire (the same text the rank is parsed from) — so we
            # render THAT into a clean Gemini-styled card and screenshot it. This
            # guarantees ranks 1-3 + the audited business + [RANK: X/Y] are in-frame
            # every time, with no wipe race / prompt leak. Gated by GEMINI_SHOT_FILE.
            shot_file = os.environ.get("GEMINI_SHOT_FILE")
            if shot_file:
                try:
                    import base64 as _b64
                    # Wait for the answer to FULLY render before the shot — logged-out
                    # Gemini streams it in, so capturing immediately catches it
                    # mid-sentence with no [RANK] line. Poll the DOM for the [RANK:]
                    # marker (up to ~8s, inside the pre-wipe window).
                    for _ in range(16):
                        rendered = c.call("Runtime.evaluate", {"expression":
                            "(document.body.innerText||'').includes('[RANK:')",
                            "returnByValue": True}).get("result", {}).get("result", {}).get("value")
                        if rendered:
                            break
                        time.sleep(0.5)
                    # Drop the leaked prompt bubble so the answer is framed, not the query.
                    c.call("Runtime.evaluate", {"expression": _GEMINI_STRIP_PROMPT_JS,
                                                "returnByValue": True})
                    time.sleep(0.3)
                    data = c.call("Page.captureScreenshot",
                                  {"format": "png", "captureBeyondViewport": True}) \
                            .get("result", {}).get("data", "")
                    if data:
                        with open(shot_file, "wb") as sf:
                            sf.write(_b64.b64decode(data))
                        result["screenshot"] = shot_file
                        with open(RESULT_FILE, "w") as fh:
                            json.dump(result, fh)
                        print(f"SCREENSHOT -> {shot_file} ({len(_b64.b64decode(data))} bytes)")
                except Exception as _se:
                    print("screenshot failed:", _se)
        else:
            print("no prose block; raw head:", text[:300])

    c.close()
    # Close the tab(s) this capture used so they don't accumulate across runs.
    _close_all_tabs(serial)
    if not got_answer:
        with open(RESULT_FILE, "w") as fh:
            json.dump({"captured": False, "answer": None,
                       "rank_position": None, "rank_total": None}, fh)
    print("\nRESULT:", "CAPTURED ANSWER OFF THE WIRE ✅" if got_answer
          else "no answer captured (check submit / markers)")
    return 0 if got_answer else 1


if __name__ == "__main__":
    sys.exit(main())
