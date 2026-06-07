#!/usr/bin/env python3
"""Fleet rank-MEASUREMENT bridge — pull a SERP run's queued prompts from the
tracker, run each as a real Google search on a fleet phone via
``seo_dispatch.dispatch_one``, map the SerpApi-shaped result to the tracker's
ingest body, and POST it back (executor token). The tracker then detects +
trends.

MEASUREMENT + EVIDENCE ONLY. This worker runs Google searches to *observe*
rank/visibility and captures proof screenshots. It performs NO engagement, NO
CTR manipulation, and NO clicking on results — it never interacts with any
listing beyond reading the SERP. Look-but-don't-touch.

Design:
  - PURE helpers ``serpapi_to_ingest`` (SerpApi result -> tracker serp body)
    and ``result_status`` (-> "done"|"failed") have no IO and unit-test with
    plain dicts.
  - ``process_run`` orchestrates over INJECTED callables (get_run /
    dispatch_query / post_result), so the flow tests with fakes — no network,
    no phone, no ``seo_dispatch`` import.
  - ``main`` wires the real callables (urllib GET/POST + ``seo_dispatch``).
    ``seo_dispatch`` is LAZY-imported inside the real path so this module
    imports for testing without it (and without adb on PATH).
"""
import argparse
import json
import os
import urllib.request
from pathlib import Path


# ── PURE: SerpApi result -> tracker ingest serp body ────────────────────────

def serpapi_to_ingest(serpapi: dict) -> dict:
    """Map a SerpApi-shaped result to the tracker's ingest ``serp`` body.

    organic_results + local_results pass through; ai_overview/answer_box are
    null (the on-device parse does not surface them). local_results defaults to
    ``{"places": []}`` when missing/None so the detector always sees a shape.
    """
    return {
        "ai_overview": None,
        "answer_box": None,
        "organic_results": serpapi.get("organic_results", []),
        "local_results": serpapi.get("local_results") or {"places": []},
    }


# ── PURE: dispatch result -> ingest status ──────────────────────────────────

def result_status(res: dict) -> str:
    """"done" only on a clean completed search; anything else is "failed".

    A bot/reCAPTCHA challenge (``challenge`` truthy) is a failed measurement
    even if status says completed.
    """
    if res.get("status") == "completed" and not res.get("challenge"):
        return "done"
    return "failed"


# ── orchestration over INJECTED callables ───────────────────────────────────

def process_run(*, get_run, dispatch_query, post_result, limit=None) -> dict:
    """Measure each queued prompt of a run and post the mapped result back.

    Callables (injected so this unit-tests with fakes — no network/phone):
      get_run()                -> run dict with ``prompts`` (each id/prompt/status)
      dispatch_query(prompt)   -> {"serpapi": <SerpApi result>, "status": ...}
      post_result(prompt_id, body) -> ingest one prompt's {serp,status,error}

    Returns ``{"done": n, "failed": m}`` over the prompts processed.
    """
    run = get_run()
    counts = {"done": 0, "failed": 0}
    processed = 0
    for prompt in run["prompts"]:
        if prompt.get("status") != "queued":
            continue
        if limit is not None and processed >= limit:
            break
        processed += 1

        res = dispatch_query(prompt["prompt"])
        serp = serpapi_to_ingest(res["serpapi"])
        status = result_status(res)
        post_result(prompt["id"], {
            "serp": serp,
            "status": status,
            "error": res.get("error"),
        })
        counts[status] += 1
    return counts


# ── real callables (CLI wiring) ─────────────────────────────────────────────

def _get_run_http(base: str, run_id: int) -> dict:
    req = urllib.request.Request(f"{base}/serp-runs/{run_id}", method="GET")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_result_http(base: str, run_id: int, executor_token: str):
    def post_result(prompt_id: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/serp-runs/{run_id}/prompts/{prompt_id}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Executor-Token": executor_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            r.read()
    return post_result


def _dispatch_query_real(serial: str, out_dir: Path, location: str):
    """Real measurement: run one Google search on a phone and read its JSON.

    LAZY-imports ``seo_dispatch`` so this module imports without it (tests).
    ``dispatch_one`` writes a SerpApi-shaped JSON to ``out_dir``; we read it
    back so ``serpapi_to_ingest`` gets the full result. Measurement only — no
    engagement/clicking happens anywhere in this path.
    """
    import seo_dispatch  # lazy: only needed on the real phone path

    def dispatch_query(prompt: str) -> dict:
        summary = seo_dispatch.dispatch_one(
            serial, prompt, None, out_dir, location=location,
        )
        serpapi = json.loads(Path(summary["json"]).read_text())
        return {
            "serpapi": serpapi,
            "status": summary.get("status"),
            "challenge": summary.get("challenge"),
            "error": summary.get("error"),
        }
    return dispatch_query


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fleet rank-MEASUREMENT bridge (no engagement/CTR/clicking)")
    ap.add_argument("--base", required=True, help="Tracker base URL, e.g. http://localhost:8000")
    ap.add_argument("--run-id", type=int, required=True, help="serp-run id to measure")
    ap.add_argument("--serial", help="adb serial of the fleet phone (default: first device)")
    ap.add_argument("--out", default="seo_results", help="Output dir for evidence JSON/PNG")
    ap.add_argument("--location", default="", help="Geo proxied to (search_parameters.location_requested)")
    ap.add_argument("--limit", type=int, default=None, help="Max prompts to measure this run")
    ap.add_argument("--executor-token", default=os.environ.get("EXECUTOR_TOKEN"),
                    help="X-Executor-Token (default: $EXECUTOR_TOKEN)")
    args = ap.parse_args()

    if not args.executor_token:
        ap.error("provide --executor-token or set $EXECUTOR_TOKEN")

    serial = args.serial
    if not serial:
        import seo_dispatch
        serial = seo_dispatch._first_device()

    out_dir = Path(args.out)

    summary = process_run(
        get_run=lambda: _get_run_http(args.base, args.run_id),
        dispatch_query=_dispatch_query_real(serial, out_dir, args.location),
        post_result=_post_result_http(args.base, args.run_id, args.executor_token),
        limit=args.limit,
    )
    print(f"run {args.run_id}: measured {summary['done']} done, {summary['failed']} failed")


if __name__ == "__main__":
    main()
