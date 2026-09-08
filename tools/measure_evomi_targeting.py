"""Measure billed ZIP versus city traffic with fixed-size downloads, no phones.

Source .env.dev first. Each invocation downloads ten 1 MB responses through
Evomi and settles the account meter. It never launches a ranking queue.
"""
import argparse
import ast
import json
import os
import secrets
from pathlib import Path
import ssl
import subprocess
import time
import urllib.request

import certifi

ROOT = Path(__file__).resolve().parents[1]
CTX = ssl.create_default_context(cafile=certifi.where())


def meter_headers():
    # Reuse the existing local meter credential without printing/copying it.
    tree = ast.parse((ROOT / "evomi_balance.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            try:
                value = ast.literal_eval(node)
                if "x-apikey" in value:
                    return value
            except (ValueError, TypeError):
                pass
    raise RuntimeError("Meter credentials unavailable")


def balance():
    req = urllib.request.Request("https://api.evomi.com/public", headers=meter_headers())
    with urllib.request.urlopen(req, timeout=25, context=CTX) as response:
        return float(json.load(response)["products"]["rpc"]["balance_mb"])


def idle():
    rows = subprocess.check_output(["ps", "-axo", "comm=,args="], text=True)
    return not any("gost -C" in row or "Python -u run_ranking.py" in row
                   or "Python -u run_rolling_plan.py" in row for row in rows.splitlines())


def settle(before=None):
    previous = None
    stable = 0
    began = time.monotonic()
    for _ in range(60):
        if not idle():
            raise RuntimeError("Another proxy workload started; sample not attributable")
        value = balance()
        print(json.dumps({"time": time.time(), "balance_mb": value}), flush=True)
        stable = stable + 1 if value == previous else 0
        old_enough = before is None or time.monotonic() - began >= 300
        if stable >= 6 and old_enough and (before is None or value < before - 0.5):
            return value
        previous = value
        time.sleep(10)
    raise RuntimeError("Meter did not settle; no savings claim")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tier", choices=("zip", "city"))
    p.add_argument("--output", required=True)
    args = p.parse_args()
    target = "_zip-10001" if args.tier == "zip" else "_city-new.york"
    start = settle()
    completed = 0
    for i in range(10):
        if not idle():
            raise RuntimeError("Another proxy workload started")
        password = os.environ["EVOMI_PASS"] + "_country-US" + target + "_session-" + secrets.token_hex(5)
        # curl configuration on stdin keeps proxy credentials out of argv/logs.
        config = ('proxy = "http://core-residential.evomi.com:1000"\n'
                  'proxy-user = ' + json.dumps(os.environ["EVOMI_USER"] + ":" + password) + '\n')
        run = subprocess.run(["curl", "--config", "-", "--silent", "--fail",
                              "--max-time", "30", "--output", "/dev/null",
                              "--write-out", "%{http_code} %{size_download} %{http_connect}",
                              "https://speed.cloudflare.com/__down?bytes=1000000"],
                             input=config, text=True, capture_output=True, timeout=35)
        ok = run.returncode == 0 and run.stdout.strip() == "200 1000000 200"
        completed += ok
        print(json.dumps({"tier": args.tier, "request": i + 1, "ok": ok,
                          "rc": run.returncode, "response": run.stdout}), flush=True)
    end = settle(before=start if completed else None)
    result = {"tier": args.tier, "requests": 10, "completed": completed,
              "downloaded_mb": completed, "start_mb": start, "end_mb": end,
              "billed_mb": round(start - end, 2),
              "billed_per_downloaded_mb": round((start-end)/completed, 3) if completed else None}
    with open(args.output, "x") as output:
        json.dump(result, output, indent=2)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
