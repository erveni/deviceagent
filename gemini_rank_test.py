#!/usr/bin/env python3
"""Validate Gemini ranking via CDP capture BEHIND DataImpulse, on real keywords.

Sets up the gost→DataImpulse(US) chain + socksdroid on one phone, then for each
real (keyword, business, city, state) runs gemini_cdp_capture and reports the
captured rank AND the IP-geo Gemini detected (the SWML location string in the
payload) — so we can confirm (a) geo is US now, not Manila, and (b) ranks vary.

Usage: PROXY_PASS=<dataimpulse pw> python3 gemini_rank_test.py "<serial>" [port_idx]
"""
import json, os, re, subprocess, sys, time

os.environ.setdefault("PROXY_PROVIDER", "dataimpulse")
os.environ.setdefault("PROXY_HOST", "gw.dataimpulse.com")
os.environ.setdefault("PROXY_PORT", "10000")
os.environ.setdefault("PROXY_USER", "78e340233fcc27a26b14")

from run_with_proxy import (  # noqa: E402
    gost_start, gost_stop, socksdroid_connect, socksdroid_disconnect,
    wait_tunnel, rsid, build_upstream_user, BASE_GOST,
)

SERIAL = sys.argv[1]
PORT_IDX = int(sys.argv[2]) if len(sys.argv) > 2 else 20
CASES = json.load(open("/tmp/gemini_test_cases.json"))

PROMPT_T = (
    "Top 3 businesses for {kw} in {city}, {state}. Format: numbered list, each "
    "entry: name and a one-sentence reason. After the list, rank {biz} "
    "({url}) among all businesses in this space. You MUST include this exact "
    "line on its own: [RANK: X/Y] where X is the position and Y is total "
    "businesses. Keep entire response under 160 words."
)
GEO_RE = re.compile(r'"([^"]+)","SWML_DESCRIPTION_FROM_YOUR_INTERNET_ADDRESS"')


def run_one(case):
    sid = rsid()
    spec = {"port": BASE_GOST + PORT_IDX, "upstream_user": build_upstream_user(sid), "sid": sid}
    gp = gc = None
    try:
        gp, gc = gost_start([spec])
        socksdroid_connect(SERIAL, spec["port"])
        time.sleep(3)
        if not wait_tunnel(SERIAL):
            return {**case, "rank": None, "geo": "TUNNEL_FAILED"}
        url = re.sub(r"[^a-z0-9]", "", case["biz"].lower())[:20] + ".com"
        prompt = PROMPT_T.format(kw=case["kw"], city=case["city"], state=case["state"],
                                 biz=case["biz"], url=url)
        for f in ("/tmp/gemini_result.json", "/tmp/gemini_answer.txt"):
            try: os.remove(f)
            except OSError: pass
        subprocess.run(["python3", "gemini_cdp_capture.py", SERIAL, prompt],
                       capture_output=True, timeout=120)
        res = json.load(open("/tmp/gemini_result.json")) if os.path.exists("/tmp/gemini_result.json") else {}
        ans = open("/tmp/gemini_answer.txt").read() if os.path.exists("/tmp/gemini_answer.txt") else ""
        gm = GEO_RE.search(ans)
        return {**case,
                "rank": f"{res.get('rank_position')}/{res.get('rank_total')}" if res.get("rank_position") else None,
                "geo": gm.group(1) if gm else "(not in snippet)"}
    finally:
        if gp: gost_stop(gp, gc)
        try: socksdroid_disconnect(SERIAL)
        except Exception: pass
        time.sleep(2)


def main():
    print(f"phone={SERIAL}  proxy=DataImpulse US  cases={len(CASES)}\n")
    for c in CASES:
        r = run_one(c)
        print(f"  {r['kw']!r:34s} {r['biz'][:22]:22s} {r['city']},{r['state']:3s} "
              f"-> RANK {str(r['rank']):>7s} | geo: {r['geo']}")


if __name__ == "__main__":
    main()
