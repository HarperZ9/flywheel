"""Admission durability and false-success controls, using inert drivers only."""
import json

import pytest

from harness import browser_control as browser
from harness import browser_control_store as store

NOW = "2026-09-09T00:00:00Z"
NAV = {"kind": "navigate", "url": "https://example.test/"}


@pytest.fixture(autouse=True)
def no_driver():
    browser.clear_drivers()
    yield
    browser.clear_drivers()


def opened(root, cap=5):
    browser.open_session(root, run_id="r", at=NOW,
                         policy={"origins": ["https://example.test"], "max_actions": cap})


def act(root, request_id="a", action=None):
    return browser.attempt(root, run_id="r", request_id=request_id,
                           action=action or NAV, at=NOW)


def test_driver_sees_durable_budget_reservation(tmp_path):
    opened(tmp_path, cap=1)
    def driver(action):
        snapshot = browser.session(tmp_path, run_id="r")
        assert snapshot["attempted"] == 1
        assert snapshot["actions"][0]["phase"] == "admitted"
        assert snapshot["actions"][0]["performed"] is None
        return {"ok": True, "performed": True}
    browser.register_driver("fixture", driver)
    result = act(tmp_path)
    assert result["performed"] is True
    assert browser.session(tmp_path, run_id="r")["attempted"] == 1
    refused = act(tmp_path, "b")
    assert refused["admitted"] is False and "cap" in refused["reason"]


def test_admission_persistence_failure_prevents_driver(tmp_path, monkeypatch):
    opened(tmp_path)
    calls = []
    browser.register_driver("fixture", lambda action: calls.append(action))
    monkeypatch.setattr(store.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError()))
    with pytest.raises(store.BrowserStoreError):
        act(tmp_path)
    assert calls == []


def test_exception_is_unknown_and_same_request_never_redispatches(tmp_path):
    opened(tmp_path)
    calls = []
    def driver(action):
        calls.append(action)
        raise RuntimeError("PRIVATE_EXCEPTION_CANARY")
    browser.register_driver("fixture", driver)
    result = act(tmp_path)
    assert result["delivery_status"] == "unknown"
    assert result["performed"] is None
    assert act(tmp_path) == result
    assert len(calls) == 1
    assert act(tmp_path, "different")["admitted"] is False
    assert len(calls) == 1
    assert "PRIVATE_EXCEPTION_CANARY" not in browser.chain_path(tmp_path, "r").read_text()


def test_completion_write_failure_leaves_nonreplayable_admission(tmp_path, monkeypatch):
    opened(tmp_path)
    calls = []
    browser.register_driver("fixture", lambda action: calls.append(action) or {"ok": True, "performed": True})
    original = store.append
    def fail_terminal(path, records, record):
        if record["kind"] == "completion":
            raise store.BrowserStoreError("BROWSER_STORE_UNAVAILABLE")
        return original(path, records, record)
    monkeypatch.setattr(store, "append", fail_terminal)
    with pytest.raises(store.BrowserStoreError):
        act(tmp_path)
    assert act(tmp_path)["performed"] is None
    assert len(calls) == 1
    assert browser.session(tmp_path, run_id="r")["delivery_unknown"] is True


@pytest.mark.parametrize("outcome", [{}, None, {"ok": True}, {"ok": False, "performed": True}])
def test_missing_or_contradictory_acknowledgement_is_not_success(tmp_path, outcome):
    opened(tmp_path)
    browser.register_driver("fixture", lambda action: outcome)
    result = act(tmp_path)
    assert result["performed"] is None
    assert result["delivery_status"] == "unknown"
    assert browser.session(tmp_path, run_id="r")["performed"] == 0


def test_explicit_no_action_acknowledgement_is_recorded_without_success(tmp_path):
    opened(tmp_path)
    browser.register_driver("fixture", lambda action: {"ok": False, "performed": False})
    assert act(tmp_path)["performed"] is False


def test_simulated_navigation_cannot_authorize_later_driver_click(tmp_path):
    opened(tmp_path)
    assert act(tmp_path)["simulated"] is True
    calls = []
    browser.register_driver("fixture", lambda action: calls.append(action))
    result = act(tmp_path, "click", {"kind": "click", "selector": "#go"})
    assert result["admitted"] is False
    assert calls == []


def test_conflicting_duplicate_and_missing_identifier_refused(tmp_path):
    opened(tmp_path)
    calls = []
    browser.register_driver("fixture", lambda action: calls.append(action) or {"ok": True, "performed": True})
    act(tmp_path)
    with pytest.raises(browser.Refused, match="request_id"):
        act(tmp_path, action={"kind": "screenshot"})
    with pytest.raises(browser.Refused, match="request_id"):
        browser.attempt(tmp_path, run_id="r", action=NAV, at=NOW)
    assert len(calls) == 1


def test_interrupt_retains_unknown_delivery_and_does_not_retry(tmp_path):
    opened(tmp_path)
    calls = []
    def driver(action):
        calls.append(action)
        raise KeyboardInterrupt()
    browser.register_driver("fixture", driver)
    with pytest.raises(KeyboardInterrupt):
        act(tmp_path)
    assert act(tmp_path)["performed"] is None
    assert len(calls) == 1


@pytest.mark.parametrize("corrupt", ["{", "{}", "null"])
def test_malformed_history_is_not_an_empty_new_session(tmp_path, corrupt):
    opened(tmp_path)
    browser.chain_path(tmp_path, "r").write_text(corrupt)
    with pytest.raises((browser.Refused, store.BrowserStoreError)):
        browser.open_session(tmp_path, run_id="r", policy={"origins": ["https://example.test"]}, at=NOW)


def test_a_valid_hash_does_not_make_unknown_delivery_a_performed_success(tmp_path):
    opened(tmp_path)
    browser.register_driver("fixture", lambda action: {"ok": True, "performed": True})
    act(tmp_path)
    path = browser.chain_path(tmp_path, "r")
    records = json.loads(path.read_text())
    terminal = records[-1]
    terminal["delivery_status"] = "unknown"
    from harness.hash_chain import seal
    records[-1] = seal(terminal, digest_key=browser.DIGEST_KEY)
    assert browser.chain_intact(records)
    path.write_text(json.dumps(records))
    assert browser.session(tmp_path, run_id="r")["chain_intact"] is False
    with pytest.raises(browser.Refused, match="broken"):
        act(tmp_path, "another")


def test_existing_route_forwards_identifier_and_returns_unknown_without_replay(tmp_path):
    from harness.browser_route import handle_browser_post
    opened(tmp_path)
    calls = []
    def driver(action):
        calls.append(action)
        raise RuntimeError("PRIVATE_ROUTE_CANARY")
    browser.register_driver("fixture", driver)
    request = {"run_id": "r", "action": NAV, "request_id": "same"}
    first, code = handle_browser_post("/api/browser/action", request, run_root=tmp_path, clock=lambda: NOW)
    second, replay_code = handle_browser_post("/api/browser/action", request, run_root=tmp_path, clock=lambda: NOW)
    assert code == replay_code == 200
    assert first == second
    assert first["recorded"] is True and first["event"]["performed"] is None
    assert first["session"]["delivery_unknown"] is True
    assert len(calls) == 1


def test_route_reports_persistence_failure_without_claiming_recorded(tmp_path, monkeypatch):
    from harness.browser_route import handle_browser_post
    opened(tmp_path)
    calls = []
    browser.register_driver("fixture", lambda action: calls.append(action))
    def fail(*args):
        raise store.BrowserStoreError("PRIVATE_PATH_CANARY")
    monkeypatch.setattr(store, "append", fail)
    body, code = handle_browser_post("/api/browser/action", {
        "run_id": "r", "action": NAV, "request_id": "same"}, run_root=tmp_path, clock=lambda: NOW)
    assert code == 503 and not body.get("recorded")
    assert "PRIVATE_PATH_CANARY" not in json.dumps(body)
    assert calls == []


def test_phase_less_new_record_cannot_downgrade_to_legacy_success(tmp_path):
    from harness.hash_chain import seal
    opened(tmp_path)
    calls = []
    browser.register_driver("fixture", lambda action: calls.append(action))
    act(tmp_path)
    path = browser.chain_path(tmp_path, "r")
    records = json.loads(path.read_text())[:-1]
    admission = records[-1]
    admission.pop("phase")
    admission.update(performed=True, delivery_status="driver_reported_performed",
                     result_sha256="a" * 64)
    records[-1] = seal(admission, digest_key=browser.DIGEST_KEY)
    assert browser.chain_intact(records)
    path.write_text(json.dumps(records))
    snapshot = browser.session(tmp_path, run_id="r")
    assert snapshot["chain_intact"] is False
    assert snapshot["performed"] == 0
    assert snapshot["driver_open_origin"] is None
    with pytest.raises(browser.Refused, match="broken"):
        act(tmp_path, "click", {"kind": "click", "selector": "#go"})
    assert len(calls) == 1


def test_genuine_legacy_driver_record_is_retained_but_not_authoritative(tmp_path):
    from harness.hash_chain import seal
    opened(tmp_path)
    path = browser.chain_path(tmp_path, "r")
    records = json.loads(path.read_text())
    legacy = dict(schema=store.SCHEMA, kind="action", at=NOW, run_id="r", seq=1,
                  action=NAV, admitted=True, reason="allowed", origin="https://example.test",
                  driver="fixture", performed=True, result_sha256="a" * 64,
                  prev_sha256=records[-1][store.DIGEST])
    records.append(seal(legacy, digest_key=store.DIGEST))
    path.write_text(json.dumps(records))
    calls = []
    browser.register_driver("fixture", lambda action: calls.append(action))
    snapshot = browser.session(tmp_path, run_id="r")
    assert snapshot["chain_intact"] is True
    assert snapshot["performed"] == 0
    assert snapshot["actions"][0]["performed"] is None
    assert snapshot["driver_open_origin"] is None
    assert snapshot["delivery_unknown"] is True
    assert act(tmp_path, "click", {"kind": "click", "selector": "#go"})["admitted"] is False
    assert calls == []
    assert json.loads(path.read_text())[1]["performed"] is True
