"""Real-lock continuation serialization, bounded refusal, and explicit replay."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

import harness.continuation_route as route
import harness.journey_lock as locks
from harness.evidence_json import canonical_sha256
from continuation_contention_probe import AcquisitionClock, ContentionProbe, collect_results
from test_native_continuation_agent_handoff import (
    OWNER, _continuation_post, _export, _git_root,
)

CALLERS = 12
# Fixture liveness only; the production acquisition budget remains 2.0 seconds.
WATCHDOG = 10


def _durable_snapshot(state):
    return {str(path.relative_to(state)): path.read_bytes()
            for directory in (state / "journeys", state / "continuation" / "starts")
            for path in directory.rglob("*.json")}


def _exercise(tmp_path, monkeypatch, *, different_ids, expires):
    root, state = _git_root(tmp_path), tmp_path / "state"
    preview, status = _continuation_post("/api/continuation/preview", {
        "root": str(root), "export_path": str(_export(tmp_path))}, state, root)
    assert status == 200
    lock_key = canonical_sha256({"owner_ref": OWNER, "preview_ref": preview["preview_ref"]})
    outer_path = state / "continuation" / "starts" / "locks" / f"{lock_key}.lock"
    requests = [{**{key: preview[key] for key in (
        "preview_ref", "preview_sha256", "source_state_sha256")},
        "client_request_id": f"continuation-start-{index}" if different_ids
        else "continuation-start"} for index in range(CALLERS)]
    clock = AcquisitionClock()
    probe = ContentionProbe()
    real_try_lock, real_run = locks._try_lock, route._grant_and_run
    real_acquire = locks.ExclusiveJourneyLock.acquire
    real_time, real_thread = time.monotonic, threading.Thread
    release, owner_entered = threading.Event(), threading.Event()
    contended, refused = threading.Event(), threading.Event()
    guard = threading.Lock()
    callers_ready = threading.Barrier(CALLERS)
    contenders, early_results = set(), []
    creates = 0

    @contextmanager
    def observed_acquire(path, timeout_s=2.0):
        lock = str(Path(path).relative_to(state))
        probe.record("lock.waiting", lock=lock)
        with clock.acquire(real_acquire, path, timeout_s, outer_path=outer_path):
            probe.record("lock.acquired", lock=lock)
            try:
                yield
            finally:
                probe.record("lock.releasing", lock=lock)

    def observed_try_lock(stream):
        acquired = real_try_lock(stream)
        if not acquired and Path(stream.name) == outer_path:
            with guard:
                contenders.add(threading.get_ident())
                if len(contenders) == CALLERS - 1:
                    contended.set()
            if expires:
                clock.expire()
        return acquired

    def held_create(action, request, **kwargs):
        nonlocal creates
        if action == "create":
            with guard:
                creates += 1
            owner_entered.set()
            probe.record("create.awaiting_release")
            assert release.wait(3 * WATCHDOG), "fixture owner was never released"
        probe.record(action + ".running")
        result = real_run(action, request, **kwargs)
        probe.record(action + ".returned")
        return result

    def start_one(index):
        probe.record("caller.barrier", caller=index)
        callers_ready.wait(timeout=WATCHDOG)
        result = _continuation_post("/api/continuation/start", requests[index], state)
        probe.record("caller.returned", status=result[1])
        if not release.is_set():
            with guard:
                early_results.append(result)
                if len(early_results) == CALLERS - 1:
                    refused.set()
        return result

    # Only a pending outer acquisition uses the controlled caller-local clock.
    monkeypatch.setattr(locks, "time", SimpleNamespace(
        monotonic=clock.monotonic, sleep=time.sleep))
    monkeypatch.setattr(locks.ExclusiveJourneyLock, "acquire", observed_acquire)
    monkeypatch.setattr(locks, "_try_lock", observed_try_lock)
    monkeypatch.setattr(route, "_grant_and_run", held_create)
    with ThreadPoolExecutor(max_workers=CALLERS) as pool:
        futures = [pool.submit(start_one, index) for index in range(CALLERS)]
        try:
            assert owner_entered.wait(WATCHDOG), "owner never reached create"
            assert contended.wait(WATCHDOG), "all peers must fail a real outer lock attempt"
            if expires:
                assert refused.wait(WATCHDOG), "expired contenders did not return"
                assert all(status == 503 and body["error"] == {
                    "code": "STORE_BUSY", "message": "continuation start is busy"}
                    for body, status in early_results)
            else:
                assert not early_results
                assert not any(future.done() for future in futures)
            assert creates == 1
            assert not list((state / "journeys").rglob("jrn_*"))
            assert not list((state / "continuation" / "starts").rglob("*.json"))
        finally:
            release.set()
        results = collect_results(futures, timeout=WATCHDOG, probe=probe)

    assert time.monotonic is real_time and threading.Thread is real_thread
    accepted = [(index, body) for index, (body, status) in enumerate(results) if status == 200]
    assert len(accepted) == (1 if expires else CALLERS)
    assert sum(not body["journey"].get("idempotent_replay") for _, body in accepted) == 1
    refs = {body["journey"]["journey_ref"] for _, body in accepted}
    assert len(refs) == 1
    journey_ref = refs.pop()
    owner_dir = state / "journeys" / "v2" / "owners" / OWNER
    assert [path.name for path in owner_dir.glob("jrn_*")] == [journey_ref]
    binding_path = state / "continuation" / "starts" / OWNER / f"{preview['preview_ref']}.json"
    binding = json.loads(binding_path.read_bytes())
    assert binding["owner_ref"] == OWNER and binding["preview_ref"] == preview["preview_ref"]
    assert binding["preview_sha256"] == preview["preview_sha256"]
    assert binding["source_state_sha256"] == preview["source_state_sha256"]
    assert binding["journey_ref"] == journey_ref
    first_index = next(index for index, body in accepted
                       if not body["journey"].get("idempotent_replay"))
    assert binding["start_client_request_id"] == requests[first_index]["client_request_id"]
    assert len(list((state / "continuation" / "starts").rglob("*.json"))) == 1
    before = _durable_snapshot(state)
    for index, (body, status) in enumerate(results):
        if status == 200:
            continue
        assert expires and status == 503 and body["error"]["code"] == "STORE_BUSY"
        # The owner is settled, and refusal was observed before any create mutation.
        # This is one explicit caller replay, not a transport retry after unknown send.
        replay, replay_status = _continuation_post(
            "/api/continuation/start", requests[index], state)
        assert replay_status == 200
        assert replay["journey"]["journey_ref"] == journey_ref
        assert replay["journey"]["idempotent_replay"] is True
    assert creates == 1 and _durable_snapshot(state) == before


@pytest.mark.parametrize("expires", (False, True), ids=("overlap", "busy_then_replay"))
def test_duplicate_start_serializes_one_journey_without_orphan(tmp_path, monkeypatch, expires):
    _exercise(tmp_path, monkeypatch, different_ids=False, expires=expires)


@pytest.mark.parametrize("expires", (False, True), ids=("overlap", "busy_then_replay"))
def test_duplicate_start_different_request_ids_replay_one_preview_journey(tmp_path, monkeypatch, expires):
    _exercise(tmp_path, monkeypatch, different_ids=True, expires=expires)
