"""Falsifiers for the background-run registry (async_runs.RunRegistry).

A phone starts a long agent run and polls it: start must return at once, status
must show live progress before completion, result must gate until done, a raising
work must be captured (never a lost traceback), and the registry must stay
bounded.
"""
import threading
import time

from relay.async_runs import DONE, ERROR, INTERRUPTED, RUNNING, RunRegistry


def _wait(reg, run_id, want, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if reg.status(run_id).get("state") == want:
            return True
        time.sleep(0.005)
    return False


def test_start_returns_id_at_once_then_completes():
    reg = RunRegistry(id_source=lambda: "run-1", clock=lambda: 42)

    def work(ledger):
        ledger.append("assistant", "did the thing")
        return {"final": "ok"}

    run_id = reg.start(work)
    assert run_id == "run-1"
    assert _wait(reg, run_id, DONE)
    res = reg.result(run_id)
    assert res["state"] == DONE and res["result"] == {"final": "ok"}
    assert reg.status(run_id)["started"] == 42


def test_status_shows_live_progress_before_completion():
    reg = RunRegistry()
    started, release = threading.Event(), threading.Event()

    def work(ledger):
        ledger.append("assistant", "step one")
        started.set()
        release.wait(3.0)  # hold the run open so the test observes it running
        ledger.append("assistant", "step two")
        return {"final": "done"}

    run_id = reg.start(work)
    assert started.wait(3.0)
    mid = reg.status(run_id)
    assert mid["state"] == RUNNING and mid["steps"] >= 1
    assert mid["latest"] and mid["latest"][-1]["kind"] == "assistant"
    assert reg.result(run_id)["state"] == RUNNING  # not ready while running
    release.set()
    assert _wait(reg, run_id, DONE)
    assert reg.status(run_id)["steps"] == 2


def test_error_in_work_is_captured_not_raised():
    reg = RunRegistry()

    def work(ledger):
        raise RuntimeError("every backend died")

    run_id = reg.start(work)
    assert _wait(reg, run_id, ERROR)
    res = reg.result(run_id)
    assert res["state"] == ERROR and "every backend died" in res["error"]


def test_unknown_run_id_is_typed_not_a_crash():
    reg = RunRegistry()
    assert "error" in reg.status("nope")
    assert "error" in reg.result("nope")


def test_registry_evicts_the_oldest_beyond_max():
    reg = RunRegistry(max_runs=2)

    def work(ledger):
        return {"ok": True}

    ids = [reg.start(work) for _ in range(3)]
    # the third start pushes the registry over the cap; the oldest record is gone
    assert "error" in reg.status(ids[0])
    assert _wait(reg, ids[2], DONE)


# --- durability: a run_id survives a restart when a run_root is set ---

import json  # noqa: E402


def test_a_finished_run_survives_a_restart(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-keep", run_root=root)

    def work(ledger):
        ledger.append("assistant", "did it")
        return {"final": "kept"}

    run_id = reg.start(work)
    assert _wait(reg, run_id, DONE)

    # a restarted process (a fresh registry on the same root) must see the run again;
    # poll because persistence lands a hair after the in-memory DONE transition.
    end = time.time() + 3.0
    while time.time() < end and RunRegistry(run_root=root).result(run_id)["state"] != DONE:
        time.sleep(0.02)
    reborn = RunRegistry(run_root=root)
    res = reborn.result(run_id)
    assert res["state"] == DONE and res["result"] == {"final": "kept"}
    assert reborn.status(run_id)["steps"] == 1   # the witnessed ledger survived too


def test_list_returns_recent_runs_newest_first(tmp_path):
    clock = [1]
    reg = RunRegistry(run_root=str(tmp_path / "runs"), clock=lambda: clock[0])

    def work(ledger):
        return {"ok": True}

    a = reg.start(work)
    clock[0] = 2
    b = reg.start(work)
    assert _wait(reg, a, DONE) and _wait(reg, b, DONE)
    listing = reg.list()
    ids = [r["run_id"] for r in listing["runs"]]
    assert ids[0] == b and a in ids          # newest first
    assert listing["count"] == 2


def test_a_run_cut_off_mid_flight_reloads_as_interrupted(tmp_path):
    from relay.async_runs import INTERRUPTED
    root = tmp_path / "runs"
    root.mkdir()
    (root / "run-x.json").write_text(json.dumps({
        "run_id": "run-x", "state": "running", "result": None, "error": None,
        "started": 5, "finished": None, "ledger_jsonl": ""}), encoding="utf-8")
    reg = RunRegistry(run_root=str(root))
    assert reg.result("run-x")["state"] == INTERRUPTED
    assert reg.list()["runs"][0]["state"] == INTERRUPTED


def test_persistence_is_off_without_a_run_root():
    reg = RunRegistry()

    def work(ledger):
        return {"ok": True}

    rid = reg.start(work)
    assert _wait(reg, rid, DONE)
    assert "error" in RunRegistry().result(rid)   # a fresh registry shares nothing


def test_request_binding_survives_status_result_and_restart(tmp_path):
    from relay.async_runs import DONE
    root = str(tmp_path / "runs")
    binding = {"schema": "relay.mcp-run-request/v1", "backend": "stub",
               "goal_sha256": "a" * 64}
    reg = RunRegistry(id_source=lambda: "run-bound", clock=lambda: 9, run_root=root)

    def work(ledger):
        ledger.append("assistant", "done")
        return {"final": "kept", "request_binding": binding}

    run_id = reg.start(work, request_binding=binding)
    assert _wait(reg, run_id, DONE)
    assert reg.status(run_id)["request_binding"] == binding
    assert reg.result(run_id)["request_binding"] == binding
    assert reg.result(run_id)["result"]["request_binding"] == binding
    reborn = RunRegistry(run_root=root)
    assert reborn.status(run_id)["request_binding"] == binding
    assert reborn.result(run_id)["request_binding"] == binding
    assert reborn.list()["runs"][0]["request_binding"] == binding


def test_checkpoint_during_blocked_worker_survives_restart_with_partial_ledger(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-partial", run_root=root)
    checkpointed, release = threading.Event(), threading.Event()

    def work(ledger):
        ledger.append("assistant", "meaningful progress before the worker blocks")
        written = ledger.persist_checkpoint()
        assert written["persisted"] is True
        checkpointed.set()
        release.wait(3.0)
        return {"final": "done later"}

    run_id = reg.start(work, request_binding={"schema": "test-binding/v1"})
    assert checkpointed.wait(3.0)
    reborn = RunRegistry(run_root=root)
    status = reborn.status(run_id)
    assert status["state"] == INTERRUPTED
    assert status["entries"] == 1
    assert status["steps"] == 1
    assert status["latest"][-1]["summary"] == "meaningful progress before the worker blocks"
    assert reborn.result(run_id)["state"] == INTERRUPTED

    release.set()
    assert _wait(reg, run_id, DONE)
    assert RunRegistry(run_root=root).result(run_id)["state"] == DONE


def test_repeated_checkpoint_updates_the_partial_snapshot(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-repeat", run_root=root)
    checkpointed, release = threading.Event(), threading.Event()

    def work(ledger):
        ledger.append("assistant", "first durable progress")
        first = ledger.persist_checkpoint()
        ledger.append("tool_result", "second durable progress", {"tool": "read_file", "ok": True})
        second = ledger.persist_checkpoint()
        assert first["persisted"] is True and first["entries"] == 1
        assert second["persisted"] is True and second["entries"] == 2
        checkpointed.set()
        release.wait(3.0)
        return {"final": "done later"}

    run_id = reg.start(work)
    assert checkpointed.wait(3.0)
    status = RunRegistry(run_root=root).status(run_id)
    assert status["state"] == INTERRUPTED
    assert status["entries"] == 2
    assert status["latest"][-1]["kind"] == "tool_result"
    assert status["latest"][-1]["summary"] == "second durable progress"
    release.set()


def test_checkpoint_unknown_run_id_is_typed_not_a_crash(tmp_path):
    reg = RunRegistry(run_root=str(tmp_path / "runs"))
    result = reg.checkpoint("missing-run")
    assert result["persisted"] is False
    assert "unknown run_id" in result["error"]


def test_checkpoint_refuses_finished_run_without_rewriting_it_as_running(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-done", run_root=root)

    def work(ledger):
        ledger.append("assistant", "finished work")
        return {"final": "done"}

    run_id = reg.start(work)
    assert _wait(reg, run_id, DONE)
    result = reg.checkpoint(run_id)
    assert result["persisted"] is False
    assert "state 'done'" in result["error"]
    reborn = RunRegistry(run_root=root)
    assert reborn.result(run_id)["state"] == DONE
    assert reborn.status(run_id)["entries"] == 1


def test_failed_checkpoint_write_does_not_report_persisted_success(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-fail-write", run_root=root)
    appended, release = threading.Event(), threading.Event()

    def work(ledger):
        ledger.append("assistant", "not yet durable")
        appended.set()
        release.wait(3.0)
        return {"final": "done later"}

    run_id = reg.start(work)
    assert appended.wait(3.0)
    reg._persist = lambda *args, **kwargs: False

    result = reg.checkpoint(run_id)
    assert result["persisted"] is False
    assert result["entries"] == 1
    assert "persistence failed" in result["error"]
    assert RunRegistry(run_root=root).status(run_id)["entries"] == 0
    release.set()


def test_concurrent_finish_after_checkpoint_leaves_disk_done_not_running(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-race", run_root=root)
    progress_appended = threading.Event()
    release_finish = threading.Event()
    checkpoint_write_entered = threading.Event()
    release_checkpoint_write = threading.Event()
    original_persist = reg._persist

    def slow_running_checkpoint_persist(run, **kwargs):
        if kwargs.get("state", run.state) == RUNNING and len(run.ledger.entries) == 1:
            checkpoint_write_entered.set()
            release_checkpoint_write.wait(3.0)
        return original_persist(run, **kwargs)

    reg._persist = slow_running_checkpoint_persist

    def work(ledger):
        ledger.append("assistant", "race progress")
        progress_appended.set()
        release_finish.wait(3.0)
        return {"final": "done after checkpoint"}

    run_id = reg.start(work)
    assert progress_appended.wait(3.0)
    checkpoint_result = {}
    checkpoint_thread = threading.Thread(
        target=lambda: checkpoint_result.update(reg.checkpoint(run_id)))
    checkpoint_thread.start()
    assert checkpoint_write_entered.wait(3.0)

    release_finish.set()
    time.sleep(0.02)
    release_checkpoint_write.set()
    checkpoint_thread.join(3.0)

    assert checkpoint_result["persisted"] is True
    assert _wait(reg, run_id, DONE)
    reborn = RunRegistry(run_root=root)
    assert reborn.result(run_id)["state"] == DONE
    assert reborn.status(run_id)["entries"] == 1


def test_checkpoint_receipt_is_bound_to_serialized_snapshot_when_worker_appends_after_write(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-snapshot", run_root=root)
    progress_appended = threading.Event()
    release_finish = threading.Event()
    checkpoint_file_written = threading.Event()
    appended_after_write = threading.Event()
    original_persist = reg._persist
    delayed_once = {"done": False}

    def delay_after_checkpoint_write(run, **kwargs):
        persisted = original_persist(run, **kwargs)
        if (not delayed_once["done"] and kwargs.get("state", run.state) == RUNNING
                and len(run.ledger.entries) == 1):
            delayed_once["done"] = True
            checkpoint_file_written.set()
            appended_after_write.wait(3.0)
        return persisted

    reg._persist = delay_after_checkpoint_write

    def work(ledger):
        ledger.append("assistant", "serialized in checkpoint")
        progress_appended.set()
        release_finish.wait(3.0)
        return {"final": "done after checkpoint"}

    run_id = reg.start(work)
    assert progress_appended.wait(3.0)
    checkpoint_result = {}
    checkpoint_thread = threading.Thread(
        target=lambda: checkpoint_result.update(reg.checkpoint(run_id)))
    checkpoint_thread.start()
    assert checkpoint_file_written.wait(3.0)

    reg._get(run_id).ledger.append("assistant", "live after checkpoint serialization")
    appended_after_write.set()
    checkpoint_thread.join(3.0)

    saved = json.loads((tmp_path / "runs" / "run-snapshot.json").read_text(encoding="utf-8"))
    saved_entries = [json.loads(line) for line in saved["ledger_jsonl"].splitlines() if line.strip()]
    assert len(saved_entries) == 1
    assert checkpoint_result["persisted"] is True
    assert checkpoint_result["entries"] == len(saved_entries)
    assert checkpoint_result["steps"] == 1
    assert checkpoint_result["chain_head"] == saved_entries[-1]["entry_hash"]
    assert reg.status(run_id)["entries"] == 2

    release_finish.set()
    assert _wait(reg, run_id, DONE)


def test_done_result_is_not_exposed_before_final_persist_finishes(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-durable", run_root=root)
    original_persist = reg._persist
    final_persist_entered = threading.Event()
    release_final_persist = threading.Event()

    def slow_final_persist(run, **kwargs):
        state = kwargs.get("state", run.state)
        if state == DONE:
            final_persist_entered.set()
            release_final_persist.wait(3.0)
        return original_persist(run, **kwargs)

    reg._persist = slow_final_persist

    def work(ledger):
        ledger.append("assistant", "done")
        return {"final": "durable"}

    run_id = reg.start(work)
    assert final_persist_entered.wait(3.0)
    assert reg.result(run_id)["state"] == RUNNING
    assert RunRegistry(run_root=root).result(run_id)["state"] == INTERRUPTED

    release_final_persist.set()
    assert _wait(reg, run_id, DONE)
    assert RunRegistry(run_root=root).result(run_id)["state"] == DONE
