#!/usr/bin/env python3
"""Clean client-facing ChatGPT/Perplexity ranking screenshot, via CDP + DOM scan.

Three things, in order:
  1. SCAN the DOM to find the answer's ranked list (<ol>) and SCROLL so rank #1 is
     at the top of the viewport — using a real swipe gesture (ChatGPT ignores
     programmatic scrollTop, but its inner scroller responds to touch), closed-loop
     against the measured <ol> position. So the shot shows ranks 1-3 + the [RANK]
     line, not just the bottom of the answer.
  2. STRIP the auto-embedded Mapbox map widget (a plain <img>; ChatGPT ignores the
     'no maps' prompt).
  3. CAPTURE the cleaned, positioned viewport.

All Mac-side (no APK change). Usage:
  CDP_PORT=<port> python3 cdp_strip_map_shot.py <serial> <url_substr> <out_path>
Prints "SHOT <path>" on success.
"""
import base64, subprocess, sys, time

from gemini_cdp_capture import _forward, _cdp_json, CDP, _GEMINI_STRIP_PROMPT_JS

TARGET_TOP = 190   # desired <ol> top offset from viewport top (px) — margin below the
                   # header so rank #1 is never clipped at the very top
TOL = 90           # acceptable distance from target
MAX_ITERS = 8

STRIP_MAP_JS = r"""
(()=>{let n=0;
  document.querySelectorAll('img').forEach(img=>{
    if(/api\.mapbox\.com|\/maps\/|googleusercontent.*map|staticmap/.test(img.src||'')){
      let el=img;
      for(let i=0;i<4 && el.parentElement;i++){
        if(el.parentElement.clientHeight>img.clientHeight*1.3) break;
        el=el.parentElement;}
      el.remove(); n++;}});
  return n;})()
"""
OL_TOP_JS = "(()=>{const o=[...document.querySelectorAll('ol')].pop(); if(!o)return null; return Math.round(o.getBoundingClientRect().top);})()"


# Remove the user's prompt/query bubble so it doesn't leak at the top of the shot.
# ChatGPT tags its user turns ([data-message-author-role="user"]); Perplexity has no
# such tag, so fall back to the leaf holding a phrase that only ever appears in the
# prompt, then climb to its bubble container and drop it.
STRIP_PROMPT_JS = r"""
(()=>{let n=0;
  document.querySelectorAll('[data-message-author-role="user"]').forEach(e=>{e.remove();n++;});
  if(!n){const PH='numbered 1-3';
    for(const e of document.querySelectorAll('*')){
      if(e.childElementCount===0 && (e.textContent||'').includes(PH)){
        let el=e,k=0;
        while(el.parentElement && k<6){
          const p=el.parentElement;
          if((p.textContent||'').length > (e.textContent||'').length*2.5) break;
          el=p; k++;}
        el.remove(); n++; break;}}}
  return n;})()
"""


def _tab_ws(serial, substr):
    for p in _cdp_json(serial):
        if p.get("type") == "page" and substr in (p.get("url") or ""):
            return p.get("webSocketDebuggerUrl")
    return None


def main():
    if len(sys.argv) < 4:
        print("usage: cdp_strip_map_shot.py <serial> <url_substr> <out_path>", file=sys.stderr)
        return 2
    serial, substr, out = sys.argv[1], sys.argv[2], sys.argv[3]

    def swipe(y1, y2):
        subprocess.run(["adb", "-s", serial, "shell", "input", "swipe",
                        "360", str(int(y1)), "360", str(int(y2)), "260"],
                       capture_output=True)

    _forward(serial)
    ws = _tab_ws(serial, substr)
    if not ws:
        print(f"no Chrome tab matching '{substr}'", file=sys.stderr)
        return 2
    c = CDP(ws)
    try:
        c.call("Page.enable")

        def ev(expr):
            return c.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}) \
                    .get("result", {}).get("result", {}).get("value")

        # GUARD: logged-out ChatGPT/Perplexity don't always keep the conversation in the
        # DOM by the time we re-attach (the answer is gone → we'd capture a blank home
        # screen). If the answer isn't present, bail with a non-zero exit so the dispatcher
        # falls back to the app's own (live) screenshot instead of saving a blank.
        has_answer = ev(
            "(()=>{const t=document.body.innerText||'';"
            "return document.querySelector('ol')!==null || /\\[?RANK:/i.test(t) || t.length>500;})()"
        )
        if not has_answer:
            print("no answer in DOM (racy logged-out conversation) — fall back to app shot",
                  file=sys.stderr)
            return 1

        # 0) drop the leaked user-prompt bubble so the answer reflows up
        ev(STRIP_PROMPT_JS)
        # Gemini's logged-out page adds chrome the other two don't: the "available on
        # Google Play" promo, the sign-in promo, the desktop nav bar and a stale
        # composer draft. Same strip the CDP capture path used (commit 8bb5143).
        if "gemini" in substr:
            ev(_GEMINI_STRIP_PROMPT_JS)
        time.sleep(0.4)

        # 1) position rank #1 (the answer's <ol> top) a touch below the header so it is
        #    never clipped at the very top. ChatGPT ignores programmatic scroll but its
        #    inner scroller responds to a real swipe — closed-loop against the measured
        #    <ol> position. (captureBeyondViewport + getBoundingClientRect don't align on
        #    ChatGPT's inner scroll container, so we frame by scrolling, not clipping.)
        for i in range(MAX_ITERS):
            t = ev(OL_TOP_JS)
            if t is None:
                break  # no list found — capture wherever we are
            if abs(t - TARGET_TOP) < TOL:
                break
            if t < TARGET_TOP:        # list above target → scroll up (swipe down)
                swipe(500, 500 + min(700, TARGET_TOP - t))
            else:                      # list below target → scroll down (swipe up)
                swipe(900, 900 - min(700, t - TARGET_TOP))
            time.sleep(0.9)

        # 2) strip the map (re-run after the scroll in case it revealed one)
        removed = ev(STRIP_MAP_JS)
        if removed:
            print(f"map blocks removed: {removed}")
        time.sleep(0.4)

        # 3) capture the cleaned, positioned viewport
        data = c.call("Page.captureScreenshot", {"format": "png"}) \
                .get("result", {}).get("data", "")
    finally:
        c.close()
    if not data:
        print("no screenshot data", file=sys.stderr)
        return 1
    with open(out, "wb") as f:
        f.write(base64.b64decode(data))
    print(f"SHOT {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
