"""Tests for serp_fleet_worker — the fleet rank-MEASUREMENT bridge.

PURE/orchestration only. No network, no phone, no seo_dispatch import:
process_run runs over INJECTED callables (fake get_run / dispatch_query /
post_result), so the whole flow is exercised with plain dicts.
"""
import builtins
import importlib

import serp_fleet_worker as w


# ── lazy-import invariant: module imports WITHOUT seo_dispatch ───────────────

def test_module_imports_without_seo_dispatch(monkeypatch):
    """Spec C: ``seo_dispatch`` must be LAZY-imported inside the real CLI path
    so the module imports for testing without it (no adb env). Guards against a
    regression that moves ``import seo_dispatch`` to module top-level — that
    would make the worker unimportable wherever seo_dispatch is unavailable.
    """
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "seo_dispatch" or name.startswith("seo_dispatch."):
            raise ImportError("seo_dispatch unavailable (no adb env)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    # Re-import from scratch with seo_dispatch import blocked.
    mod = importlib.reload(w)
    assert hasattr(mod, "process_run")
    assert hasattr(mod, "serpapi_to_ingest")


def _sample_serpapi():
    return {
        "organic_results": [
            {"position": 1, "link": "https://a.com", "title": "A"},
            {"position": 2, "link": "https://b.com", "title": "B"},
        ],
        "local_results": {"places": [{"position": 1, "title": "Biz One"}]},
    }


# ── serpapi_to_ingest: pass-through + nulls ─────────────────────────────────

def test_serpapi_to_ingest_passthrough():
    serpapi = _sample_serpapi()
    body = w.serpapi_to_ingest(serpapi)
    assert body["ai_overview"] is None
    assert body["answer_box"] is None
    assert body["organic_results"] == serpapi["organic_results"]
    assert body["local_results"] == serpapi["local_results"]


def test_serpapi_to_ingest_defaults_when_missing():
    body = w.serpapi_to_ingest({})
    assert body["ai_overview"] is None
    assert body["answer_box"] is None
    assert body["organic_results"] == []
    assert body["local_results"] == {"places": []}


def test_serpapi_to_ingest_local_results_null_defaults_to_empty_places():
    body = w.serpapi_to_ingest({"local_results": None, "organic_results": []})
    assert body["local_results"] == {"places": []}


# ── result_status mapping ───────────────────────────────────────────────────

def test_result_status_done():
    assert w.result_status({"status": "completed"}) == "done"


def test_result_status_failed_when_not_completed():
    assert w.result_status({"status": "blocked"}) == "failed"
    assert w.result_status({}) == "failed"


def test_result_status_failed_on_challenge():
    assert w.result_status({"status": "completed", "challenge": True}) == "failed"


# ── process_run orchestration over fakes ────────────────────────────────────

def test_process_run_dispatches_and_posts_each_queued_prompt():
    run = {
        "id": 7,
        "prompts": [
            {"id": 101, "prompt": "lawyer austin", "status": "queued"},
            {"id": 102, "prompt": "injury lawyer austin", "status": "queued"},
        ],
    }
    dispatched = []
    posted = []

    def fake_get_run():
        return run

    def fake_dispatch_query(prompt):
        dispatched.append(prompt)
        return {"serpapi": _sample_serpapi(), "status": "completed"}

    def fake_post_result(prompt_id, body):
        posted.append((prompt_id, body))

    summary = w.process_run(
        get_run=fake_get_run,
        dispatch_query=fake_dispatch_query,
        post_result=fake_post_result,
    )

    # both prompts dispatched once, in order
    assert dispatched == ["lawyer austin", "injury lawyer austin"]
    # both posted with mapped serp + status done
    assert [pid for pid, _ in posted] == [101, 102]
    for _pid, body in posted:
        assert body["status"] == "done"
        assert body["serp"]["ai_overview"] is None
        assert body["serp"]["answer_box"] is None
        assert body["serp"]["organic_results"] == _sample_serpapi()["organic_results"]
        assert body["serp"]["local_results"] == _sample_serpapi()["local_results"]
        assert body["error"] is None
    assert summary == {"done": 2, "failed": 0}


def test_process_run_skips_non_queued_prompts():
    run = {
        "id": 9,
        "prompts": [
            {"id": 1, "prompt": "a", "status": "done"},
            {"id": 2, "prompt": "b", "status": "queued"},
        ],
    }
    dispatched = []

    summary = w.process_run(
        get_run=lambda: run,
        dispatch_query=lambda p: (dispatched.append(p) or {"serpapi": {}, "status": "completed"}),
        post_result=lambda pid, body: None,
    )

    assert dispatched == ["b"]
    assert summary == {"done": 1, "failed": 0}


def test_process_run_counts_failed_and_passes_error():
    run = {"id": 3, "prompts": [{"id": 5, "prompt": "x", "status": "queued"}]}
    posted = []

    summary = w.process_run(
        get_run=lambda: run,
        dispatch_query=lambda p: {"serpapi": {}, "status": "blocked", "error": "bot challenge"},
        post_result=lambda pid, body: posted.append((pid, body)),
    )

    assert summary == {"done": 0, "failed": 1}
    assert posted[0][1]["status"] == "failed"
    assert posted[0][1]["error"] == "bot challenge"


def test_process_run_respects_limit():
    run = {
        "id": 4,
        "prompts": [
            {"id": 1, "prompt": "a", "status": "queued"},
            {"id": 2, "prompt": "b", "status": "queued"},
            {"id": 3, "prompt": "c", "status": "queued"},
        ],
    }
    dispatched = []

    summary = w.process_run(
        get_run=lambda: run,
        dispatch_query=lambda p: (dispatched.append(p) or {"serpapi": {}, "status": "completed"}),
        post_result=lambda pid, body: None,
        limit=2,
    )

    assert dispatched == ["a", "b"]
    assert summary == {"done": 2, "failed": 0}


# ── query_retries: ride out intermittent device-flow failures ───────────────
# The on-device search flow is flaky through the proxy ("input failed" ~2/3 of
# the time — handover defect #2). A failed dispatch is re-run up to query_retries
# times so a transient flow error doesn't waste a queued prompt. Only the FINAL
# result is posted (no duplicate ingests).


def test_process_run_retries_failed_then_succeeds_posts_once():
    run = {"id": 1, "prompts": [{"id": 9, "prompt": "childcare", "status": "queued"}]}
    posted = []
    results = iter([
        {"serpapi": {}, "status": "error", "error": "input failed"},   # try 1 fails
        {"serpapi": _sample_serpapi(), "status": "completed"},          # try 2 clean
    ])

    summary = w.process_run(
        get_run=lambda: run,
        dispatch_query=lambda p: next(results),
        post_result=lambda pid, body: posted.append((pid, body)),
        query_retries=2,
    )

    assert summary == {"done": 1, "failed": 0}
    assert len(posted) == 1                       # only the final (successful) result posted
    assert posted[0][1]["status"] == "done"


def test_process_run_retries_exhausted_posts_last_failure():
    run = {"id": 1, "prompts": [{"id": 9, "prompt": "childcare", "status": "queued"}]}
    posted = []
    calls = []

    def dq(p):
        calls.append(p)
        return {"serpapi": {}, "status": "error", "error": "input failed"}

    summary = w.process_run(
        get_run=lambda: run,
        dispatch_query=dq,
        post_result=lambda pid, body: posted.append((pid, body)),
        query_retries=2,
    )

    assert calls == ["childcare", "childcare", "childcare"]   # 1 + 2 retries
    assert summary == {"done": 0, "failed": 1}
    assert len(posted) == 1
    assert posted[0][1]["status"] == "failed"
    assert posted[0][1]["error"] == "input failed"


def test_process_run_no_retry_by_default():
    run = {"id": 1, "prompts": [{"id": 9, "prompt": "x", "status": "queued"}]}
    calls = []
    w.process_run(
        get_run=lambda: run,
        dispatch_query=lambda p: (calls.append(p) or {"serpapi": {}, "status": "error"}),
        post_result=lambda pid, body: None,
    )
    assert calls == ["x"]                          # default query_retries=0 -> single attempt


# ── run_with_lifecycle: proxy setup/teardown around the measurement ─────────
# Defect #1 from the live e2e: the bridge ran dispatch_one with NO proxy, so the
# phone searched from its real Philippine IP (results for Quezon City, not the US
# target). The fix wraps the run in a proxy lifecycle so every search egresses
# from the target country. These tests pin the ordering + the always-teardown
# guarantee with fakes — no phone, no superproxy import.


def test_run_with_lifecycle_orders_setup_measure_teardown():
    events = []

    def setup():
        events.append("setup")
        return {"tun0_ip": "1.2.3.4", "local_port": 8766}

    def measure(info):
        events.append(("measure", info["local_port"]))
        return {"done": 2, "failed": 0}

    def teardown():
        events.append("teardown")

    summary = w.run_with_lifecycle(setup=setup, measure=measure, teardown=teardown)

    assert summary == {"done": 2, "failed": 0}
    assert events == ["setup", ("measure", 8766), "teardown"]


def test_run_with_lifecycle_tears_down_even_when_measure_raises():
    events = []

    def boom(info):
        events.append("measure")
        raise RuntimeError("dispatch blew up mid-run")

    try:
        w.run_with_lifecycle(
            setup=lambda: events.append("setup") or {},
            measure=boom,
            teardown=lambda: events.append("teardown"),
        )
    except RuntimeError:
        pass

    # teardown MUST run so we never leak the proxy tunnel / VPN on the phone
    assert events == ["setup", "measure", "teardown"]


def test_run_with_lifecycle_tears_down_even_when_setup_raises():
    events = []

    def boom():
        events.append("setup")
        raise RuntimeError("superproxy setup failed: no_tun0")

    try:
        w.run_with_lifecycle(
            setup=boom,
            measure=lambda info: events.append("measure"),
            teardown=lambda: events.append("teardown"),
        )
    except RuntimeError:
        pass

    # measure never runs (setup failed); teardown still cleans up (pm clear is safe)
    assert events == ["setup", "teardown"]


# ── _dispatch_query_real: threads local_port into dispatch_one ───────────────
# When egressing via a proxy the agent's HTTP port is forwarded to a per-device
# local port (8765 + device_idx), NOT the default 8765. The real dispatch
# callable must pass that port through to seo_dispatch.dispatch_one, else the
# proxied search would target the wrong / unforwarded port.


def test_dispatch_query_real_threads_local_port(tmp_path, monkeypatch):
    import sys
    import types

    captured = {}
    fake = types.ModuleType("seo_dispatch")

    def fake_dispatch_one(serial, keyword, target, out_dir, location="",
                          local_port=8765, retries=2, **kw):
        captured.update(serial=serial, keyword=keyword, target=target,
                        location=location, local_port=local_port)
        json_path = tmp_path / "result.json"
        json_path.write_text('{"organic_results": [{"position": 1}], '
                             '"search_parameters": {"location_requested": "Austin, Texas"}}')
        return {"status": "completed", "challenge": False, "error": "",
                "json": str(json_path)}

    fake.dispatch_one = fake_dispatch_one
    monkeypatch.setitem(sys.modules, "seo_dispatch", fake)

    dq = w._dispatch_query_real(serial="S1", out_dir=tmp_path,
                                location="Austin, Texas", local_port=8766)
    res = dq("childcare near me")

    assert captured["serial"] == "S1"
    assert captured["keyword"] == "childcare near me"
    assert captured["local_port"] == 8766          # forwarded per-device port, not 8765
    assert captured["location"] == "Austin, Texas"
    assert captured["target"] is None              # default: no target unless threaded
    assert res["status"] == "completed"
    assert res["serpapi"]["organic_results"] == [{"position": 1}]
    assert res["serpapi"]["search_parameters"]["location_requested"] == "Austin, Texas"


def test_dispatch_query_real_threads_target_domain(tmp_path, monkeypatch):
    # The device computes organic/local rank from the target domain. If the bridge
    # doesn't thread it, dispatch_one gets target=None and every rank comes back
    # null (the bug behind "0 results" when the business clearly ranks).
    import sys
    import types

    captured = {}
    fake = types.ModuleType("seo_dispatch")

    def fake_dispatch_one(serial, keyword, target, out_dir, location="",
                          local_port=8765, retries=2, **kw):
        captured.update(target=target)
        json_path = tmp_path / "result.json"
        json_path.write_text('{"organic_results": []}')
        return {"status": "completed", "challenge": False, "error": "",
                "json": str(json_path)}

    fake.dispatch_one = fake_dispatch_one
    monkeypatch.setitem(sys.modules, "seo_dispatch", fake)

    dq = w._dispatch_query_real(serial="S1", out_dir=tmp_path, location="",
                                target_domain="maeschildcare.com")
    dq("bilingual childcare near me")

    assert captured["target"] == "maeschildcare.com"   # passed through, not None


# ── bring_up_tunnel: rotate fresh US IPs until one is captcha-clean ──────────
# The SuperProxy app path is broken fleet-wide (form-fill leaves Server/Port
# empty). The working US egress is the socksdroid path (gost/relay -> socksdroid
# VPN -> Decodo): proven live to give US IPs + a clean SERP. Google sometimes
# challenges a fresh exit IP, so bring-up rotates IPs and keeps the first clean
# one — mirrors seo_proxy_run.py. Pure orchestration over injected callables
# (start_attempt/precheck/stop_attempt) so it unit-tests with no gost/adb/phone.


def test_bring_up_tunnel_keeps_first_clean_attempt():
    events = []

    def start_attempt(i):
        events.append(("start", i))
        return {"attempt": i, "exit_ip": f"10.0.0.{i}", "proc": f"p{i}"}

    def precheck(info):
        events.append(("precheck", info["attempt"]))
        return "clean"

    def stop_attempt(info):
        events.append(("stop", info["attempt"]))

    info = w.bring_up_tunnel(start_attempt=start_attempt, precheck=precheck,
                             stop_attempt=stop_attempt, attempts=3)

    assert info["exit_ip"] == "10.0.0.1"
    # first attempt clean -> kept (NOT stopped), no further attempts
    assert events == [("start", 1), ("precheck", 1)]


def test_bring_up_tunnel_rotates_past_blocked_ip():
    events = []
    prechecks = {1: "blocked", 2: "clean"}

    def start_attempt(i):
        events.append(("start", i))
        return {"attempt": i, "exit_ip": f"10.0.0.{i}", "proc": f"p{i}"}

    def stop_attempt(info):
        events.append(("stop", info["attempt"]))

    info = w.bring_up_tunnel(
        start_attempt=start_attempt,
        precheck=lambda info: prechecks[info["attempt"]],
        stop_attempt=stop_attempt,
        attempts=3,
    )

    assert info["exit_ip"] == "10.0.0.2"
    # blocked attempt 1 torn down; attempt 2 clean and KEPT
    assert events == [("start", 1), ("stop", 1), ("start", 2)]


def test_bring_up_tunnel_raises_and_tears_down_when_all_blocked():
    stopped = []

    def start_attempt(i):
        return {"attempt": i, "exit_ip": f"10.0.0.{i}", "proc": f"p{i}"}

    try:
        w.bring_up_tunnel(
            start_attempt=start_attempt,
            precheck=lambda info: "blocked",
            stop_attempt=lambda info: stopped.append(info["attempt"]),
            attempts=3,
        )
        assert False, "expected RuntimeError after exhausting attempts"
    except RuntimeError as e:
        assert "no clean" in str(e).lower()

    # every failed attempt's tunnel was torn down — no leaked gost/socksdroid
    assert stopped == [1, 2, 3]


def test_bring_up_tunnel_tears_down_attempt_when_start_fails_midway():
    # start_attempt may bring up gost then fail at wait_tunnel; it signals that
    # by returning None (already cleaned its own partial state) — bring_up moves on.
    starts = []

    def start_attempt(i):
        starts.append(i)
        return None if i == 1 else {"attempt": i, "exit_ip": "10.0.0.2", "proc": "p2"}

    info = w.bring_up_tunnel(
        start_attempt=start_attempt,
        precheck=lambda info: "clean",
        stop_attempt=lambda info: None,
        attempts=3,
    )
    assert info["exit_ip"] == "10.0.0.2"
    assert starts == [1, 2]
