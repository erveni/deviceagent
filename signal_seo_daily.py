#!/usr/bin/env python3
"""Signal SEO — daily orchestrator.

For each client, every day, ties the existing pieces into one cycle:
  1. create a SERP run with the client's keywords   → POST /serp-runs   (run_id)
  2. measure it through the fleet                    → serp_fleet_worker --run-id
       (Decodo US IP + uule(client's location) → real SERP → parseSerp)
  3. pull the rank report + visibility trend         → GET /serp-runs/{id}/report,
                                                        GET /serp-trends?business=
Measurement only — the fleet reads SERPs, it never clicks a result.

Cron this once a day. Clients live in a JSON file:
  [
    {"business_name":"Ramos James Law","business_domain":"ramosjames.com",
     "location":"Austin, Texas","keywords":["personal injury lawyer","car accident attorney"],
     "device_idx":5}
  ]

  set -a; source .env.dev; set +a          # PROXY_*, EXECUTOR_TOKEN, ADMIN_TOKEN
  python3 signal_seo_daily.py clients.json
  DRY_RUN=1 python3 signal_seo_daily.py clients.json     # plan only, no calls
"""
import json
import os
import subprocess
import sys
import urllib.request

BASE = os.environ.get("SIGNAL_BASE", "http://localhost:8900")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
EXECUTOR_TOKEN = os.environ.get("EXECUTOR_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
OUT = os.environ.get("SIGNAL_OUT", "/tmp/signal_seo")
DEFAULT_IDX = os.environ.get("SIGNAL_DEVICE_IDX", "5")   # device-106
PYBIN = os.environ.get("SIGNAL_PY", sys.executable)
HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "serp_fleet_worker.py")
# Measurement source. 'serper' (DEFAULT) = SERP API: captcha-free, no phone, ~$0.001/search.
# 'gost' = the on-phone Decodo path (hits residential captcha; keep for spot-checks / AI engines).
SOURCE = os.environ.get("SIGNAL_SOURCE", "serper")
SERP_API_KEY = os.environ.get("SERP_API_KEY", "")
SERP_PROVIDER = os.environ.get("SERP_PROVIDER", "serper")


def _req(path, *, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Admin-Token" if token == ADMIN_TOKEN else "X-Executor-Token"] = token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def run_client(c: dict) -> dict:
    name = c["business_name"]
    location = c.get("location", "")
    domain = c.get("business_domain")
    keywords = c["keywords"]
    idx = str(c.get("device_idx", DEFAULT_IDX))
    print(f"\n=== {name} — {location} ({len(keywords)} keywords) ===", flush=True)

    body = {"business_name": name, "business_domain": domain,
            "location": location, "prompts": keywords}
    if DRY_RUN:
        print(f"  [dry] POST /serp-runs {body}")
        print(f"  [dry] bridge --location {location!r} --device-idx {idx}")
        return {"client": name, "dry": True}

    # 1) create the run
    run = _req("/serp-runs", method="POST", body=body, token=ADMIN_TOKEN)
    run_id = run.get("id") or run.get("run_id")
    print(f"  run_id={run_id}  queued={len(run.get('prompts') or [])} keywords", flush=True)

    # 2) measure through the fleet (Decodo + uule)
    # query-retries doubles as the captcha-rotation budget (each retry rotates the
    # exit IP). Decodo residential direct-nav has a non-trivial captcha rate, so give
    # it enough fresh IPs to land a clean one.
    retries = os.environ.get("SIGNAL_QUERY_RETRIES", "8")
    if SOURCE == "serper":
        # SERP API: no phone, no proxy, no captcha. The backend computes the rank
        # from organic_results by matching business_domain.
        cmd = [PYBIN, BRIDGE, "--base", BASE, "--run-id", str(run_id),
               "--proxy", "serper", "--serp-provider", SERP_PROVIDER,
               "--location", location, "--query-retries", "2", "--out", OUT]
        if SERP_API_KEY:
            cmd += ["--serp-api-key", SERP_API_KEY]
    else:
        cmd = [PYBIN, BRIDGE, "--base", BASE, "--run-id", str(run_id),
               "--proxy", "gost", "--gateway", "residential", "--device-idx", idx,
               "--country", "us", "--location", location, "--query-retries", retries,
               "--out", OUT]
        if domain:                     # so the device computes organic/local rank
            cmd += ["--target-domain", domain]
        if c.get("device_serial"):     # pin to a specific phone (robust to mDNS serial drift)
            cmd += ["--serial", c["device_serial"]]
    if EXECUTOR_TOKEN:
        cmd += ["--executor-token", EXECUTOR_TOKEN]
    print("  measuring via fleet…", flush=True)
    subprocess.run(cmd, check=False)

    # 3) report + trend
    summary = {"client": name, "run_id": run_id}
    try:
        run_after = _req(f"/serp-runs/{run_id}")
        ranks = []
        for p in run_after.get("prompts") or []:
            # Backend computes the rank onto the prompt (organic_position/local_position).
            # Fall back to the on-device serp.target shape for legacy/phone-path rows.
            serp = (p.get("serp") or {})
            tgt = serp.get("target") or {}
            org = (p.get("organic_position") or p.get("organicPosition")
                   or tgt.get("organic_rank") or tgt.get("organicRank"))
            loc = (p.get("local_position") or p.get("localPosition")
                   or tgt.get("local_rank") or tgt.get("localRank"))
            ranks.append((p.get("prompt"), org, loc))
        print("  ranks (keyword → organic / local):", flush=True)
        for kw, org, loc in ranks:
            print(f"    {kw}: organic={org or '—'}  local={loc or '—'}")
        summary["ranks"] = ranks
        rep = _req(f"/serp-runs/{run_id}/report")
        summary["report"] = rep
        acts = rep.get("actions") or []
        if acts:
            print(f"  top fixes ({len(acts)}):", flush=True)
            for a in acts[:3]:
                print(f"    • {a.get('action') or a.get('surface')}")
    except Exception as e:
        print(f"  report/trend fetch failed: {type(e).__name__}: {e}", flush=True)
    return summary


def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "clients.json")
    clients = json.load(open(cfg))
    print(f"Signal SEO daily — {len(clients)} client(s) | base={BASE} | dry={DRY_RUN}", flush=True)
    results = [run_client(c) for c in clients]
    ok = sum(1 for r in results if not r.get("dry"))
    print(f"\nDONE — {ok} client(s) measured", flush=True)


if __name__ == "__main__":
    main()
