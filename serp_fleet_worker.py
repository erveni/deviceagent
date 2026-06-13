#!/usr/bin/env python3
"""Fleet rank-MEASUREMENT bridge — pull a SERP run's queued prompts from the
tracker, run each as a real Google search on a fleet phone via
``seo_dispatch.dispatch_one``, map the SerpApi-shaped result to the tracker's
ingest body, and POST it back (executor token). The tracker then detects +
trends.

Default mode is MEASUREMENT + EVIDENCE ONLY: observe rank/visibility and capture
proof screenshots. ``--engage`` is the explicit daily SEO mode from the service
flow: after measurement, the phone clicks the target listing and scrolls/dwells.

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
  - Egress geo: by default the run is wrapped in ``run_with_lifecycle`` around a
    socksdroid tunnel (``--proxy gost``, the PROVEN path) so every search egresses
    from the target country (``--country``, default us) — NOT the phone's real IP.
    Without this the first live e2e returned Philippine results (the phone's real
    location), useless for US local SEO. ``bring_up_tunnel`` rotates fresh exit
    IPs until one prechecks captcha-clean. ``--gateway residential`` (default) is
    fast (~5s page nav, proven to scrape a clean US SERP); ``mobile`` egresses
    cellular IPs but loads pages too slowly for the flow. ``--proxy superproxy``
    is the SuperProxy-app path (broken fleet-wide: form-fill leaves Server/Port
    empty). ``--proxy none`` keeps the old direct path for offline debugging. All
    proxy modules are LAZY-imported so the module still imports for unit tests.
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

def process_run(*, get_run, dispatch_query, post_result, limit=None,
                query_retries=0, rotate=None) -> dict:
    """Measure each queued prompt of a run and post the mapped result back.

    Callables (injected so this unit-tests with fakes — no network/phone):
      get_run()                -> run dict with ``prompts`` (each id/prompt/status)
      dispatch_query(prompt)   -> {"serpapi": <SerpApi result>, "status": ...}
      post_result(prompt_id, body) -> ingest one prompt's {serp,status,error}

    ``query_retries``: extra dispatch attempts when a query comes back "failed".
    The on-device flow is intermittently flaky through the proxy ("input failed"
    ~2/3 of the time — device defect #2), so a transient flow error is re-run
    rather than wasting the queued prompt. Only the FINAL attempt is posted (no
    duplicate ingests); a clean result short-circuits the remaining retries.

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

        for attempt in range(query_retries + 1):
            res = dispatch_query(prompt["prompt"])
            status = result_status(res)
            if status == "done" or attempt == query_retries:
                break
            # A bot/reCAPTCHA challenge (status "blocked" / challenge flag) means this
            # exit IP is flagged — retrying the SAME IP just re-fails. Rotate to a fresh
            # sticky US IP and retry, so a flagged IP is never recorded as a measurement.
            if (res.get("challenge") or res.get("status") == "blocked") and rotate is not None:
                try:
                    rotate()
                except Exception as e:
                    print(f"[bridge] rotate failed: {type(e).__name__}: {e}", flush=True)
        serp = serpapi_to_ingest(res["serpapi"])
        post_result(prompt["id"], {
            "serp": serp,
            "status": status,
            "error": res.get("error"),
        })
        counts[status] += 1
    return counts


# ── proxy lifecycle around a measurement run ────────────────────────────────

def run_with_lifecycle(*, setup, measure, teardown):
    """Run ``measure(info)`` between ``setup()`` and a guaranteed ``teardown()``.

    The bridge's first live e2e ran searches with NO proxy, so the phone egressed
    from its real (Philippine) IP and Google returned results for the wrong
    country — useless for US local SEO. This wraps the whole run in a proxy
    lifecycle: ``setup()`` brings the egress tunnel up (returns an info dict, e.g.
    tun0 ip + forwarded ``local_port``), ``measure(info)`` does the dispatch loop
    over that tunnel, and ``teardown()`` ALWAYS runs — even if setup or measure
    raises — so we never leak the VPN/tunnel on the phone.

    Injected callables so this unit-tests with fakes (no phone, no superproxy).
    Returns whatever ``measure`` returns.
    """
    try:
        info = setup()
        return measure(info)
    finally:
        teardown()


# ── rotate fresh exit IPs until one is captcha-clean ────────────────────────

def bring_up_tunnel(*, start_attempt, precheck, stop_attempt, attempts):
    """Bring up a proxy tunnel, rotating exit IPs until ``precheck`` says clean.

    Google challenges some fresh exit IPs ("unusual traffic"), so each attempt
    gets a new sticky IP and we keep the FIRST that prechecks clean. Mirrors
    ``seo_proxy_run.py``'s rotation; pure over injected callables (no gost/adb):
      start_attempt(i) -> info dict (with proc handles for teardown), or None if
                          the bring-up failed and already cleaned its own partial
                          state (move to the next attempt)
      precheck(info)   -> "clean" | "blocked" | "unknown"  (only "blocked" rotates)
      stop_attempt(info)-> tear down THIS attempt's tunnel

    Returns the winning attempt's info (kept up — caller's teardown stops it).
    Raises ``RuntimeError`` after exhausting attempts (each torn down).
    """
    for i in range(1, attempts + 1):
        info = start_attempt(i)
        if info is None:
            continue
        status = precheck(info)
        # Only an EXPLICIT captcha rotates; "unknown" usually just means the SERP
        # is still loading behind a Chrome dialog — keep it and let the flow run.
        if status == "blocked":
            stop_attempt(info)
            continue
        return info
    raise RuntimeError(f"no clean exit IP found in {attempts} attempts")


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


def _dispatch_query_real(serial: str, out_dir: Path, location: str,
                         local_port: int = 8765, target_domain: str | None = None,
                         engage: bool = False, target_name: str = "",
                         lat: float | None = None, lng: float | None = None):
    """Real measurement: run one Google search on a phone and read its JSON.

    LAZY-imports ``seo_dispatch`` so this module imports without it (tests).
    ``dispatch_one`` writes a SerpApi-shaped JSON to ``out_dir``; we read it
    back so ``serpapi_to_ingest`` gets the full result. When ``engage`` is true,
    the phone performs the daily click + scroll/dwell step after rank parsing.

    ``local_port`` is the adb-forwarded port for the phone's agent (:8765). On
    the proxy path it is the per-device port (8765 + device_idx) that
    ``superproxy_dispatch.POOL.setup_forwards`` maps, so each phone's traffic
    egresses through ITS tunnel; on the no-proxy path it stays the default 8765.

    ``target_domain`` is the client's domain; passed to the device so ``parseSerp``
    can compute ``organic_rank``/``local_rank``. Without it the device has nothing
    to match against and every result comes back rank-null (the SERP still parses).
    """
    import seo_dispatch  # lazy: only needed on the real phone path

    def dispatch_query(prompt: str) -> dict:
        summary = seo_dispatch.dispatch_one(
            serial, prompt, target_domain, out_dir, location=location,
            local_port=local_port, retries=0,   # bridge rotates the exit IP on captcha
            engage=engage,
            target_name=target_name,
            lat=lat, lng=lng,
        )
        serpapi = json.loads(Path(summary["json"]).read_text())
        return {
            "serpapi": serpapi,
            "status": summary.get("status"),
            "challenge": summary.get("challenge"),
            "error": summary.get("error"),
            "engaged": summary.get("engaged"),
        }
    return dispatch_query


def _setup_superproxy(serial: str, device_idx: int, country: str) -> dict:
    """Bring up the Decodo Mobile tunnel on ``serial`` via the SuperProxy app so
    Chrome egresses from ``country`` (mirrors ``seo_superproxy_run.py``).

    LAZY-imports the superproxy modules (they pull adb/run_with_proxy) so this
    bridge still imports for unit tests without them. Returns an info dict with
    the verified ``tun0_ip`` plus the per-device ``local_port`` to drive the
    agent through. Raises ``RuntimeError`` if the tunnel never comes up.
    """
    import superproxy_proxy as sp
    import superproxy_dispatch as spd

    spd.POOL.setup_forwards()                       # map 8765+idx -> phone :8765
    ok, info = sp.setup(serial, device_idx, country=country)
    if not ok:
        raise RuntimeError(f"superproxy setup failed: {info.get('reason')}")
    info["local_port"] = spd._old_agent_local_port(device_idx)
    return info


def _teardown_superproxy(serial: str) -> None:
    """Drop the tunnel + reset SuperProxy (``pm clear``). Idempotent/safe to call
    even if setup never fully succeeded — so it's the lifecycle's finally step."""
    import superproxy_proxy as sp
    sp.teardown(serial)


def _build_geo_suffix(geo: dict | None) -> str:
    """Decodo username geo-targeting segment, e.g. '-state-california-city-san_francisco-zip-94117'.
    Empty when no geo given (→ random in-country exit, the prior behavior). Pins the
    EXIT IP to the client's city/zip so a local SERP (e.g. 'childcare Alamo Square')
    actually surfaces the client instead of an out-of-town IP's results."""
    if not geo:
        return ""
    parts = []
    for key in ("state", "city", "zip"):                 # Decodo order: state → city → zip
        val = (geo.get(key) or "").strip().lower().replace(" ", "_")
        if val:
            parts.append(f"-{key}-{val}")
    return "".join(parts)


def _setup_gost(serial: str, gateway: str, country: str, attempts: int,
                keyword: str, state: dict, geo: dict | None = None) -> dict:
    """Bring up a clean US egress tunnel via the socksdroid path and stash the
    process handles in ``state`` for teardown. Mirrors ``seo_proxy_run.py``.

    This is the WORKING US-egress path (the SuperProxy-app path is broken
    fleet-wide). Chain: Mac gost/SNI-relay -> socksdroid VPN on the phone ->
    Decodo. ``residential`` (gost-direct) is the proven, FAST path (page nav ~5s)
    and the default; ``mobile`` (SNI relay straight to Decodo Mobile) egresses
    cellular IPs but loads pages far slower. ``bring_up_tunnel`` rotates fresh
    sticky IPs and keeps the first that prechecks captcha-clean.

    All heavy imports are LAZY so this module still imports for unit tests.
    Agent traffic rides adb-forward on the default :8765 (a local USB/TLS channel,
    NOT the VPN), so ``local_port`` stays 8765 — only Chrome egresses via the VPN.
    Raises ``RuntimeError`` if no clean IP is found.
    """
    import run_with_proxy as rwp
    import seo_proxy_run as spr

    # socksdroid on the phone dials back to the Mac's LAN IP for the gost tunnel.
    # run_with_proxy.MAC_IP defaults to a hardcoded address that goes stale on every
    # DHCP/Wi-Fi change; if it's wrong the phone's VPN can't reach the Mac and Chrome
    # shows "site can't be reached" on EVERY exit IP (looks like captcha-rotation but
    # isn't). Pin it to $MAC_IP (the canonical knob) so socksdroid_connect dials the
    # right Mac. Mirrors spike_locale_captcha.py's override.
    env_mac = os.environ.get("MAC_IP")
    if env_mac and env_mac != rwp.MAC_IP:
        print(f"[bridge] MAC_IP {rwp.MAC_IP} -> {env_mac} (socksdroid dials this)", flush=True)
        rwp.MAC_IP = env_mac

    host, port, user_prefix, password = spr._gateway(gateway)
    if not user_prefix or not password:
        raise RuntimeError(f"{gateway} gateway creds missing — source .env.dev"
                           + ("; set SUPERPROXY_PASS for mobile" if gateway == "mobile" else ""))
    direct_decodo = gateway == "mobile"
    state.setdefault("procs", [])

    geo_suffix = _build_geo_suffix(geo)

    def start_attempt(i: int):
        sid = spr._sid()
        spec = {"port": spr.GOST_PORT, "sid": sid,
                "upstream_user": f"{user_prefix}-country-{country}{geo_suffix}-session-{sid}"
                                 f"-sessionduration-{spr.SESSION_DURATION}"}
        rwp.PROXY_HOST, rwp.PROXY_PORT, rwp.PROXY_PASS = host, int(port), password
        gost_proc = gost_cfg = relay_proc = None
        try:
            if direct_decodo:
                # mobile: Decodo Mobile is a SOCKS5 gateway — relay dials it directly
                # by hostname (gost's chain to mobile Decodo is broken, 0x03).
                relay_proc = spr._relay_start(spr.RELAY_PORT, int(port), up_host=host,
                                              up_user=spec["upstream_user"], up_pass=password)
                exit_ip = spr._decodo_exit_ip(host, int(port), spec["upstream_user"], password)
                phone_port = spr.RELAY_PORT
            else:
                # residential: gost HTTP-CONNECTs to Decodo BY HOSTNAME (the only thing
                # residential :10001 accepts). SocksDroid can only IP-CONNECT, which
                # Decodo 522-rejects → "site can't be reached" on every page. So put the
                # SNI relay IN FRONT of gost (up_host=None → forwards to local gost): the
                # relay recovers the hostname from the TLS SNI and re-dials gost, turning
                # the phone's raw IP-CONNECT into the hostname-CONNECT gost needs.
                gost_proc, gost_cfg = rwp.gost_start([spec])
                relay_proc = spr._relay_start(spr.RELAY_PORT, spr.GOST_PORT)
                exit_ip = rwp.resolve_proxy_ip(spr.GOST_PORT)
                phone_port = spr.RELAY_PORT
            rwp.socksdroid_connect(serial, phone_port)
            if not rwp.wait_tunnel(serial):
                raise RuntimeError("tunnel never came up")
        except Exception as e:
            # Clean THIS attempt's partial state and signal "skip" to bring_up_tunnel.
            print(f"[bridge] gost attempt {i} bring-up failed: {e} — rotating")
            _stop_procs(serial, [gost_proc, gost_cfg, relay_proc])
            return None
        info = {"attempt": i, "exit_ip": exit_ip or "?", "local_port": 8765,
                "_gost_proc": gost_proc, "_gost_cfg": gost_cfg, "_relay_proc": relay_proc}
        return info

    def precheck(info: dict) -> str:
        return spr._precheck_serp(serial, keyword)

    def stop_attempt(info: dict) -> None:
        _stop_procs(serial, [info.get("_gost_proc"), info.get("_gost_cfg"),
                             info.get("_relay_proc")])

    info = bring_up_tunnel(start_attempt=start_attempt, precheck=precheck,
                           stop_attempt=stop_attempt, attempts=attempts)
    # Remember the WINNING attempt's procs so teardown stops them.
    state["procs"] = [info.get("_gost_proc"), info.get("_gost_cfg"), info.get("_relay_proc")]
    state["serial"] = serial
    return info


def _stop_procs(serial: str, procs: list) -> None:
    """Stop one attempt's gost/relay procs + drop the phone's socksdroid VPN.
    Each piece is best-effort so a partial bring-up still cleans up fully."""
    import run_with_proxy as rwp
    gost_proc, gost_cfg, relay_proc = (procs + [None, None, None])[:3]
    try:
        rwp.socksdroid_disconnect(serial)
    except Exception:
        pass
    if relay_proc is not None:
        try:
            relay_proc.terminate()
            relay_proc.wait(timeout=5)
        except Exception:
            try:
                relay_proc.kill()
            except Exception:
                pass
    if gost_proc is not None:
        try:
            rwp.gost_stop(gost_proc, gost_cfg)
        except Exception:
            pass


def _teardown_gost(state: dict) -> None:
    """Lifecycle finally-step: drop the winning tunnel (socksdroid VPN + gost/relay).
    No-op-safe when setup never populated ``state`` (e.g. setup raised early)."""
    serial = state.get("serial")
    if not serial:
        return
    _stop_procs(serial, state.get("procs", []))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fleet rank bridge; optional daily engagement with --engage")
    ap.add_argument("--base", default=None,
                    help="Tracker base URL, e.g. http://localhost:8000 (measurement mode). "
                         "Not needed in engagement-only mode (--keyword).")
    ap.add_argument("--run-id", type=int, default=None,
                    help="serp-run id to measure (measurement mode). Omit and pass --keyword "
                         "for engagement-only daily mode.")
    ap.add_argument("--proxy", choices=["gost", "superproxy", "none", "serper"], default="gost",
                    help="Egress path. 'serper' (RECOMMENDED for Google rank) = SERP API, "
                         "NO phone/proxy/captcha — server-side, returns structured JSON; "
                         "needs --serp-api-key. 'gost' (PROVEN on-phone) = socksdroid VPN -> "
                         "Decodo, US-located results; needs --device-idx + .env.dev creds "
                         "(hits residential captcha on a burned pool). "
                         "'superproxy' = SuperProxy-app Decodo Mobile tunnel (BROKEN fleet-wide). "
                         "'none' = phone's real IP (DANGER: searches from the phone's real "
                         "location, e.g. PH — only for local/offline debugging).")
    ap.add_argument("--serp-api-key", default=os.environ.get("SERP_API_KEY"),
                    help="SERP API key for --proxy serper (default: $SERP_API_KEY)")
    ap.add_argument("--serp-provider", default=os.environ.get("SERP_PROVIDER", "serper"),
                    help="SERP API provider for --proxy serper (default: serper)")
    ap.add_argument("--gateway", choices=["residential", "mobile"], default="residential",
                    help="For --proxy gost: 'residential' (DEFAULT, gost-direct, fast ~5s page "
                         "nav) or 'mobile' (SNI relay -> Decodo Mobile cellular, slower loads).")
    ap.add_argument("--attempts", type=int, default=4,
                    help="For --proxy gost: max fresh-IP attempts to find a captcha-clean exit.")
    ap.add_argument("--probe-keyword", default="coffee near me",
                    help="For --proxy gost: cheap keyword used to precheck an exit IP for captcha.")
    ap.add_argument("--device-idx", type=int, default=None,
                    help="Index into run_with_proxy.DEVICES (required for --proxy gost/superproxy)")
    ap.add_argument("--serial", help="adb serial (used only for --proxy none; default: first device)")
    ap.add_argument("--country", default="us", help="Proxy egress country for gost/superproxy (default: us)")
    ap.add_argument("--out", default="seo_results", help="Output dir for evidence JSON/PNG")
    ap.add_argument("--location", default="", help="Geo metadata (search_parameters.location_requested)")
    ap.add_argument("--target-domain", default=None,
                    help="Client domain to rank (e.g. maeschildcare.com). Passed to the device "
                         "so parseSerp computes organic/local rank. If omitted, falls back to the "
                         "run's business_domain. Without either, results come back rank-null.")
    ap.add_argument("--engage", action="store_true",
                    help="Click the target SERP listing and dwell after the search. "
                         "Only valid with phone-backed sources, not --proxy serper.")
    ap.add_argument("--keyword", action="append", dest="keywords", default=[],
                    help="Engagement-ONLY daily mode: search + click + scroll/dwell this keyword "
                         "(repeatable). Keywords come from here, NOT a tracker run — implies "
                         "--engage, creates no serp-run and posts NO rank back. Phone source only; "
                         "requires --target-domain (the listing to click).")
    ap.add_argument("--target-name", default="",
                    help="Optional business name hint for local-pack engagement fallback.")
    ap.add_argument("--zip", dest="zip_code", default="",
                    help="Pin the Decodo exit IP to this ZIP (e.g. 94117). Localizes the SERP to "
                         "the client's area so local keywords surface the client. gost only.")
    ap.add_argument("--city", default="",
                    help="Pin the Decodo exit IP to this city (e.g. san_francisco). gost only.")
    ap.add_argument("--geo-state", dest="geo_state", default="",
                    help="Pin the Decodo exit IP to this US state (e.g. california). gost only.")
    ap.add_argument("--lat", type=float, default=None,
                    help="Street-level mock-GPS latitude pushed to the phone (on top of the IP geo).")
    ap.add_argument("--lng", type=float, default=None,
                    help="Street-level mock-GPS longitude pushed to the phone.")
    ap.add_argument("--limit", type=int, default=None, help="Max prompts to measure this run")
    ap.add_argument("--query-retries", type=int, default=2,
                    help="Extra dispatch attempts when a query fails (rides out the device "
                         "flow's intermittent 'input failed'; default 2 = up to 3 tries).")
    ap.add_argument("--executor-token", default=os.environ.get("EXECUTOR_TOKEN"),
                    help="X-Executor-Token (default: $EXECUTOR_TOKEN)")
    args = ap.parse_args()

    # Engagement-only daily mode: keywords supplied locally (--keyword), no tracker.
    # The fleet searches + clicks + dwells; it records nothing back. The whole
    # get_run/post_result measurement contract is satisfied with a synthetic run
    # and a no-op poster, so the proxy/tunnel/IP-rotation path is reused untouched.
    engage_only = bool(args.keywords)
    if engage_only:
        args.engage = True
        if not args.target_domain:
            ap.error("engagement-only mode (--keyword) requires --target-domain "
                     "(the listing to click)")
        _kw = list(args.keywords)
        get_run = lambda: {"prompts": [
            {"id": i, "prompt": kw, "status": "queued"} for i, kw in enumerate(_kw)]}
        def post_result(_prompt_id, _body):   # daily engagement records nothing
            return None
        target_domain = args.target_domain
        print(f"[bridge] ENGAGEMENT-ONLY — {len(_kw)} keyword(s), target={target_domain}, "
              f"no tracker run, no rank recorded", flush=True)
    else:
        if args.run_id is None or not args.base:
            ap.error("measurement mode requires --base and --run-id "
                     "(or use --keyword for engagement-only mode)")
        if not args.executor_token:
            ap.error("provide --executor-token or set $EXECUTOR_TOKEN")
        get_run = lambda: _get_run_http(args.base, args.run_id)
        post_result = _post_result_http(args.base, args.run_id, args.executor_token)

        # Resolve the target domain once: explicit flag wins, else read it off the run
        # (signal_seo_daily POSTs business_domain into the run). Without it the device
        # parses the SERP fine but has nothing to match → every rank comes back null.
        target_domain = args.target_domain
        if not target_domain:
            try:
                run0 = get_run()
                target_domain = run0.get("business_domain") or run0.get("businessDomain")
            except Exception as e:
                print(f"[bridge] could not read run for business_domain: "
                      f"{type(e).__name__}: {e}", flush=True)
        if target_domain:
            print(f"[bridge] target_domain={target_domain} (ranks will be computed)", flush=True)
        else:
            print("[bridge] WARNING no target_domain — ranks will come back null "
                  "(pass --target-domain or set the run's business_domain)", flush=True)

    out_dir = Path(args.out)

    if args.proxy == "serper":
        if args.engage:
            ap.error("--engage requires a phone-backed proxy path; --proxy serper cannot click listings")
        # SERP API path: no phone, no tunnel, no captcha. The provider runs the
        # proxy/browser/captcha handling server-side and returns structured JSON,
        # which we map to the same SerpApi shape the on-phone parse produces — so
        # ingest + the report engine are identical. The backend computes the rank
        # from organic_results by matching the run's business_domain.
        import serp_api_source
        if not args.serp_api_key:
            ap.error("--proxy serper requires --serp-api-key or $SERP_API_KEY")
        print(f"[bridge] SERP API source: provider={args.serp_provider} "
              f"location={args.location!r} (no phone / no captcha)", flush=True)
        summary = process_run(
            get_run=get_run,
            dispatch_query=serp_api_source.make_dispatch_query(
                args.location, provider=args.serp_provider, api_key=args.serp_api_key),
            post_result=post_result,
            limit=args.limit,
            query_retries=args.query_retries,
        )
    elif args.proxy == "gost":
        if args.device_idx is None:
            ap.error("--proxy gost requires --device-idx (the run_with_proxy.DEVICES index)")
        from run_with_proxy import DEVICES
        device_id, serial = DEVICES[args.device_idx]
        if args.serial:                       # explicit serial wins (robust to mDNS drift)
            serial = args.serial
        geo = {"state": args.geo_state, "city": args.city, "zip": args.zip_code}
        geo_desc = _build_geo_suffix(geo) or "(random in-country)"
        print(f"[bridge] {device_id} ({serial}) — socksdroid {args.gateway} tunnel "
              f"(Decodo {args.country}{geo_desc}); searches egress US, not the phone's real IP")
        state: dict = {}

        def setup():
            info = _setup_gost(serial, args.gateway, args.country, args.attempts,
                               args.probe_keyword, state, geo=geo)
            print(f"[bridge] tunnel UP — exit_ip={info.get('exit_ip')} "
                  f"gateway={args.gateway} local_port={info['local_port']}")
            return info

        def measure(info):
            def rotate():
                # Flagged exit IP → drop this data-plane tunnel and bring up a fresh
                # sticky US IP. The agent's control forward (local_port) is stable, so
                # dispatch keeps working on the new IP.
                _stop_procs(serial, state.get("procs", []))
                new = _setup_gost(serial, args.gateway, args.country, args.attempts,
                                  args.probe_keyword, state, geo=geo)
                print(f"[bridge] rotated exit IP → {new.get('exit_ip')}", flush=True)

            return process_run(
                get_run=get_run,
                dispatch_query=_dispatch_query_real(
                    serial, out_dir, args.location, local_port=info["local_port"],
                    target_domain=target_domain, engage=args.engage,
                    target_name=args.target_name, lat=args.lat, lng=args.lng),
                post_result=post_result,
                limit=args.limit,
                query_retries=args.query_retries,
                rotate=rotate,
            )

        summary = run_with_lifecycle(
            setup=setup,
            measure=measure,
            teardown=lambda: _teardown_gost(state),
        )
    elif args.proxy == "superproxy":
        if args.device_idx is None:
            ap.error("--proxy superproxy requires --device-idx (the run_with_proxy.DEVICES index)")
        from run_with_proxy import DEVICES
        device_id, serial = DEVICES[args.device_idx]
        print(f"[bridge] {device_id} ({serial}) — bringing up Decodo Mobile ({args.country}) "
              f"tunnel; searches will egress US, not the phone's real IP")

        def setup():
            info = _setup_superproxy(serial, args.device_idx, args.country)
            print(f"[bridge] tunnel UP — tun0={info.get('tun0_ip')} "
                  f"user={info.get('username')} local_port={info['local_port']}")
            return info

        def measure(info):
            return process_run(
                get_run=get_run,
                dispatch_query=_dispatch_query_real(
                    serial, out_dir, args.location, local_port=info["local_port"],
                    target_domain=target_domain, engage=args.engage,
                    target_name=args.target_name, lat=args.lat, lng=args.lng),
                post_result=post_result,
                limit=args.limit,
                query_retries=args.query_retries,
            )

        summary = run_with_lifecycle(
            setup=setup,
            measure=measure,
            teardown=lambda: _teardown_superproxy(serial),
        )
    else:
        # --proxy none: legacy direct path. Searches run from the phone's REAL IP
        # (its real location) — measurement geo is whatever the phone sits in.
        serial = args.serial
        if not serial:
            import seo_dispatch
            serial = seo_dispatch._first_device()
        print("[bridge] WARNING --proxy none: searching from the phone's REAL IP/location "
              "(results may be geo-wrong; use --proxy gost for US results)")
        summary = process_run(
            get_run=get_run,
            dispatch_query=_dispatch_query_real(
                serial, out_dir, args.location, target_domain=target_domain,
                engage=args.engage, target_name=args.target_name, lat=args.lat, lng=args.lng),
            post_result=post_result,
            limit=args.limit,
            query_retries=args.query_retries,
        )

    print(f"run {args.run_id}: measured {summary['done']} done, {summary['failed']} failed")


if __name__ == "__main__":
    main()
