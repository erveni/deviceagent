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
