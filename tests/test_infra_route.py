"""The infrastructure controls, reached the way anything else is reached.

Six routes over `harness/infra/`. Three read the boundary the agent runs
inside and answer plainly. Three act on it, and each one goes through the
operator grant: a bare body is refused with 422 before the scanner opens a
file, before the probe leaves the machine, and before the kill switch is
asked anything at all.

The credential route is the one worth reading twice. It returns the
scanner's own sealed receipt, and a finding carries a type, a location, and
a fingerprint. The planted secret below must not appear anywhere in what the
route hands back, and one test asserts exactly that over the whole body.
"""
from __future__ import annotations

import io
import json

import pytest

from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation import GRANTABLE_ACTIONS, action_for_path
from harness.journey_store import JourneyStore, MutationCommand

NOW = "2026-09-03T01:00:00Z"
OWNER = "owner_" + "c" * 32
JOURNEY = "jrn_" + "c" * 32
PLANTED = "sk-abcdefghijklmnopqrstuvwxyz1234567890"


class _Headers:
    def __init__(self, length: str) -> None:
        self._length = length

    def get(self, key, default=None):
        return self._length if key == "Content-Length" else default


@pytest.fixture
def call(tmp_path, monkeypatch):
    """POST and GET against the real handler, with its roots under tmp."""
    import harness.gateway as gateway

    for attr, val in (("run_root", str(tmp_path)),
                      ("owner_ref", OWNER),
                      ("flywheel_home", tmp_path),
                      ("clock", lambda *a: NOW)):
        monkeypatch.setattr(gateway._Handler, attr, val, raising=False)

    def _invoke(method: str, path: str, body=None):
        raw = json.dumps(body or {}).encode()
        handler = gateway._Handler.__new__(gateway._Handler)
        handler.path = path
        handler.headers = _Headers(str(len(raw)))
        handler.rfile = io.BytesIO(raw)
        sent: dict = {}
        handler._json = lambda b, code=200: sent.update(body=b, code=code)
        getattr(handler, f"_{method}")()
        return sent

    return _invoke


@pytest.fixture
def granted(tmp_path):
    """Prepare and approve one operation, returning the dispatch body."""
    state = tmp_path / "state"
    head = JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "infra", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    envelope = {"schema": "flywheel.gateway-operation/v1",
                "journey_ref": JOURNEY, "expected_event_head": head,
                "client_request_id": "infra-1"}

    def _grant(action: str, operation: dict, *, expect_destination=None,
               expect_scopes=None):
        prepared, code = gateway_grant_post(
            f"/api/gateway-grants/prepare/{action}",
            json.dumps({**envelope, "operation": operation}).encode(),
            owner_ref=OWNER, state_root=state, clock=lambda: NOW)
        if code != 200:
            return None, prepared, code
        if expect_destination is not None:
            assert prepared["destination"] == expect_destination
        if expect_scopes is not None:
            assert prepared["scopes"] == expect_scopes
        approved, approved_code = gateway_grant_post(
            "/api/gateway-grants/approve-once",
            json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
            owner_ref=OWNER, state_root=state, clock=lambda: NOW)
        assert approved_code == 200
        return ({**envelope, "grant_ref": approved["grant_ref"], **operation},
                prepared, code)

    return _grant


# --- the three that read ---------------------------------------------------

def test_trust_model_states_its_single_points_of_failure(call):
    sent = call("get", "/api/infra/trust-model")
    assert sent["code"] == 200
    body = sent["body"]
    assert body["schema"] == "flywheel.trust-model/v1"
    assert body["components"]
    # The model declares a list and its components imply one. Both are
    # returned and the engine compares them, so a surface never has to.
    assert isinstance(body["derived_single_points_of_failure"], list)
    assert body["single_point_agreement"] is (
        sorted(body["single_points_of_failure"])
        == sorted(body["derived_single_points_of_failure"]))
    assert body["validation_errors"] == []


def test_bom_is_sealed_and_names_its_runtime(call):
    sent = call("get", "/api/infra/bom")
    assert sent["code"] == 200
    body = sent["body"]
    assert body["schema"] == "flywheel.run-bom/v1"
    assert len(body["seal_hash"]) == 64
    assert body["runtime"]["python_version"]


def test_egress_tallies_what_it_classified(call):
    sent = call("get", "/api/infra/egress")
    assert sent["code"] == 200
    body = sent["body"]
    assert body["matrix"]["rules"]
    assert body["count"] == len(body["receipts"])
    assert sum(body["verdict_counts"].values()) == body["count"]
    for verdict in body["verdict_counts"]:
        assert verdict in ("ALLOWED", "BLOCKED", "UNKNOWN")


def test_an_unreadable_socket_table_is_an_honest_null(call, monkeypatch):
    """No connection readable is stated as such, never as a clean boundary."""
    import harness.infra.egress as egress
    monkeypatch.setattr(egress, "scan_egress", lambda *a, **k: [])
    body = call("get", "/api/infra/egress")["body"]
    assert body["count"] == 0
    assert body["verdict_counts"] == {}
    assert body["reason"] == "no classifiable connection was readable"


# --- the three that act ----------------------------------------------------

def test_every_acting_route_refuses_a_bare_body(call):
    for path in ("/api/infra/credential-scan", "/api/infra/isolation",
                 "/api/infra/kill"):
        action = action_for_path(path)
        assert action in GRANTABLE_ACTIONS, path
        assert call("post", path, {})["code"] == 422, path


def test_a_credential_scan_returns_fingerprints_and_never_a_value(
        call, granted, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "leaky.env").write_text(f"api_key={PLANTED}\n", encoding="utf-8")
    body, _, _ = granted(
        "infra.credential_scan",
        {"root": str(root), "data_refs": [], "credential_refs": []},
        expect_destination={"kind": "scan", "ref": str(root)},
        expect_scopes=["secrets"])
    sent = call("post", "/api/infra/credential-scan", body)
    assert sent["code"] == 200
    receipt = sent["body"]
    assert receipt["schema"] == "flywheel.credential-scan/v1"
    assert len(receipt["seal_hash"]) == 64
    seal = receipt["seal_body"]
    assert seal["finding_count"] >= 1
    assert seal["scan_root"] == str(root)
    # The whole answer, not just the findings list. A secret leaking through
    # any field of this receipt is the failure this route exists to avoid.
    assert PLANTED not in json.dumps(receipt)
    for finding in seal["findings"]:
        assert finding["fingerprint"]
        assert PLANTED not in json.dumps(finding)


def test_a_scan_root_that_is_not_a_directory_is_refused(call, granted,
                                                        tmp_path):
    missing = tmp_path / "nowhere"
    body, _, _ = granted("infra.credential_scan",
                         {"root": str(missing), "data_refs": [],
                          "credential_refs": []})
    sent = call("post", "/api/infra/credential-scan", body)
    assert sent["code"] == 400
    assert "directory" in sent["body"]["error"]


def test_the_isolation_probe_seals_every_boundary_it_tried(call, granted):
    body, _, _ = granted("infra.isolation",
                         {"data_refs": [], "credential_refs": []},
                         expect_destination={"kind": "boundary",
                                             "ref": "isolation"},
                         expect_scopes=["network"])
    sent = call("post", "/api/infra/isolation", body)
    assert sent["code"] == 200
    receipt = sent["body"]
    assert receipt["schema"] == "flywheel.isolation-test/v1"
    assert receipt["overall_verdict"] in ("VERIFIED", "DRIFT", "UNVERIFIABLE")
    for test in receipt["seal_body"]["tests"]:
        assert test["boundary"] and test["test"]
        assert test["result"] in ("blocked", "reachable", "unverifiable")


def test_one_operator_twice_is_not_two_authorities(granted):
    """The refusal lands at prepare, before the switch is asked anything."""
    body, prepared, code = granted(
        "infra.kill", {"reason": "drill", "authority_1": "same",
                       "authority_2": "same", "data_refs": [],
                       "credential_refs": []})
    assert body is None
    assert code == 422


def test_a_kill_action_the_switch_does_not_know_is_refused(granted):
    body, _, code = granted(
        "infra.kill", {"reason": "drill", "authority_1": "a",
                       "authority_2": "b", "actions": ["reformat-the-disk"],
                       "data_refs": [], "credential_refs": []})
    assert body is None
    assert code == 422


def test_a_confirmed_kill_is_sealed_and_says_nothing_actually_ran(
        call, granted, monkeypatch):
    """Safe by default. Without FLYWHEEL_KILL_SWITCH_LIVE every action
    reports executed False with its reason, and the route reports that
    rather than a shutdown it did not perform."""
    monkeypatch.delenv("FLYWHEEL_KILL_SWITCH_LIVE", raising=False)
    body, _, _ = granted(
        "infra.kill",
        {"reason": "drill", "authority_1": "first", "authority_2": "second",
         "mode": "evidence-preserving", "actions": ["network-isolation"],
         "data_refs": [], "credential_refs": []},
        expect_destination={"kind": "kill-switch",
                            "ref": "evidence-preserving"},
        expect_scopes=["exec", "network", "secrets"])
    sent = call("post", "/api/infra/kill", body)
    assert sent["code"] == 200
    receipt = sent["body"]
    assert receipt["schema"] == "flywheel.kill-switch/v1"
    # `executed` on the seal records that two authorities confirmed it. What
    # actually ran is a separate fact, and it is False here.
    assert receipt["seal_body"]["executed"] is True
    assert receipt["any_executed"] is False
    assert [r["action"] for r in receipt["action_results"]] == [
        "network-isolation"]
    assert receipt["action_results"][0]["executed"] is False
    assert receipt["action_results"][0]["reason"]


def test_an_unknown_infra_path_is_not_found(call):
    assert call("get", "/api/infra/nothing-here")["code"] == 404
    from harness.infra_route import handle_infra_post
    assert handle_infra_post("/api/infra/nothing-here", {})[1] == 404
