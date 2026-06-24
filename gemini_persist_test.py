#!/usr/bin/env python3
"""Test whether logged-out Gemini's answer PERSISTS on a clean Bright Data US IP.

Drives a Mac Chrome (already launched through gost->Bright Data with
--ignore-certificate-errors) over CDP: confirm egress, submit a prompt, then poll
the DOM to see if the answer stays rendered or reverts to the welcome screen.

Usage: python3 gemini_persist_test.py [cdp_port] [prompt]
"""
import json, sys, time, urllib.request
import websocket

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
PROMPT = sys.argv[2] if len(sys.argv) > 2 else "best plumber in Las Vegas Nevada, list the top businesses"
INPUT_SEL = "div[contenteditable='true'], rich-textarea .ql-editor, [role='textbox'], textarea"
SEND_SEL = "button[aria-label='Send message'], button[aria-label*='Send'], button.send-button"


def page_ws():
    d = json.loads(urllib.request.urlopen(f"http://localhost:{PORT}/json", timeout=5).read())
    return next((t["webSocketDebuggerUrl"] for t in d if t.get("type") == "page"), None)


class C:
    def __init__(s, ws):
        s.ws = websocket.create_connection(ws, suppress_origin=True, timeout=15, max_size=None)
        s.i = 0
    def call(s, m, p=None, await_promise=False):
        s.i += 1; mid = s.i
        s.ws.send(json.dumps({"id": mid, "method": m, "params": p or {}}))
        while True:
            msg = json.loads(s.ws.recv())
            if msg.get("id") == mid:
                return msg
    def ev(s, expr, await_promise=False):
        r = s.call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                        "awaitPromise": await_promise})
        return r.get("result", {}).get("result", {}).get("value")


def main():
    c = C(page_ws())
    c.call("Page.enable")

    # 1) egress proof
    c.call("Page.navigate", {"url": "https://ipinfo.io/json"})
    time.sleep(5)
    ip = c.ev("document.body ? document.body.innerText.slice(0,200) : ''")
    print("EGRESS:", " ".join(ip.split())[:160])

    # 2) load gemini
    c.call("Page.navigate", {"url": "https://gemini.google.com/app"})
    ready = False
    for _ in range(25):
        time.sleep(1)
        if c.ev(f"!!document.querySelector(\"{INPUT_SEL}\")"):
            ready = True; break
    print("gemini input ready:", ready)
    if not ready:
        print("FAIL: gemini input never rendered (blocked?)"); return 1

    # 3) submit prompt
    c.ev(f"(()=>{{const e=document.querySelector(\"{INPUT_SEL}\");e.focus();"
         f"document.execCommand('insertText',false,{json.dumps(PROMPT)});}})()")
    clicked = "no_btn"
    for _ in range(8):
        time.sleep(0.7)
        clicked = c.ev("(()=>{const b=document.querySelector(" + json.dumps(SEND_SEL) +
                       ");if(!b)return 'no_btn';b.click();return 'clicked';})()")
        if clicked == "clicked":
            break
    print("submit:", clicked)

    # 4) poll persistence: is an answer on screen, or did it revert to welcome?
    print("\n  t(s) | welcome? | bodyLen | answer_visible")
    print("  -----+----------+---------+---------------")
    answer_seen = False
    for t in range(2, 41, 2):
        time.sleep(2)
        body = c.ev("document.body ? document.body.innerText : ''") or ""
        welcome = "Meet Gemini" in body
        # answer heuristic: substantial text that isn't just the welcome/prompt scaffolding
        has_ans = (len(body) > 1500 and not welcome)
        if has_ans:
            answer_seen = True
        print(f"  {t:4d} |   {('Y' if welcome else 'n')}      | {len(body):6d}  | {'YES' if has_ans else '-'}")
    print()
    # final state
    final_body = c.ev("document.body ? document.body.innerText : ''") or ""
    final_welcome = "Meet Gemini" in final_body
    if answer_seen and not final_welcome:
        print("RESULT: ✅ ANSWER PERSISTED (still rendered, no revert) — clean IP keeps it")
    elif answer_seen and final_welcome:
        print("RESULT: ⚠️ answer appeared then REVERTED to welcome — wipe still happens on clean IP")
    else:
        print("RESULT: ❌ no answer rendered (blocked or submit failed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
