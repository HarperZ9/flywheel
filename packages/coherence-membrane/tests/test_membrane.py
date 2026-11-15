"""Tests for the write-gate bridge (perception -> mediated gate request)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from coherence_membrane.membrane import build_gate_request, decide
from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.phash import DRIFT, MATCH, DriftVerdict


def _observation_with_identity(identity: str) -> Observation:
    return Observation(
        organ="visual-artifact",
        subject="frame.png",
        summary="artifact observed",
        status=Status.PASS,
        provenance=Provenance.witness_bytes("frame.png", b"x", "high"),
        data={"identity_sha256": identity},
    )


def test_build_request_basic_shape():
    req = build_gate_request(
        action_kind="render_read", target="frame.png", authorization={"x": 1}
    )
    assert set(req) >= {"planned_action", "authorization", "budget"}
    assert req["planned_action"] == {"action_kind": "render_read", "target": "frame.png"}


def test_drift_becomes_witness_verdict():
    req = build_gate_request(
        action_kind="a", target="t", authorization={},
        drift=DriftVerdict(DRIFT, 12, "changed"),
    )
    assert req["state"]["witness_verdict"] == DRIFT


def test_digest_pair_co_present():
    req = build_gate_request(
        action_kind="a", target="t", authorization={},
        observation=_observation_with_identity("a" * 64),
        expected_digest="b" * 64,
    )
    assert req["state"]["target_digest"] == "a" * 64
    assert req["state"]["expected_digest"] == "b" * 64


def test_lone_digest_is_not_emitted():
    # An observed digest with no expected baseline must not produce a half-pair.
    req = build_gate_request(
        action_kind="a", target="t", authorization={},
        observation=_observation_with_identity("a" * 64),
    )
    assert "state" not in req or "target_digest" not in req.get("state", {})


def test_decide_fails_closed_without_gate(monkeypatch):
    # With proof-surface absent, decide() must escalate, never fabricate allow.
    monkeypatch.setitem(sys.modules, "proof_surface", None)
    result = decide(build_gate_request(action_kind="a", target="t", authorization={}))
    assert result["decision"] == "needs-human"


# --- end-to-end loop with the real write-gate, if available ----------------

def _proof_surface_src() -> Path:
    # public/coherence-membrane/tests/ -> public/proof-surface/src
    return Path(__file__).resolve().parents[2] / "proof-surface" / "src"


def test_end_to_end_match_and_authorized_allows():
    src = _proof_surface_src()
    if src.exists():
        sys.path.insert(0, str(src))
    proof_surface = pytest.importorskip("proof_surface")

    now = datetime.now(timezone.utc)
    receipt = {
        "authorization_version": "0.1",
        "receipt_id": "r1",
        "kind": "authorization-grant",
        "principal": {"id": "operator"},
        "agent": {"id": "agent:render"},
        "intent": "read a rendered frame",
        "scope": {"allowed_actions": ["render_read"], "allowed_targets": []},
        "granted_at": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "revoked": False,
    }
    req = build_gate_request(
        action_kind="render_read",
        target="frame.png",
        authorization=receipt,
        drift=DriftVerdict(MATCH, 0, "identical"),
    )
    # The membrane emits a structurally valid gate request...
    assert proof_surface.validate_gate_request(req) == []
    # ...and an authorized action against a MATCH state is allowed.
    decision = proof_surface.evaluate_gate(req)
    assert decision.decision == "allow"


def test_end_to_end_drift_denies():
    src = _proof_surface_src()
    if src.exists():
        sys.path.insert(0, str(src))
    proof_surface = pytest.importorskip("proof_surface")

    now = datetime.now(timezone.utc)
    receipt = {
        "authorization_version": "0.1",
        "receipt_id": "r1",
        "kind": "authorization-grant",
        "principal": {"id": "operator"},
        "agent": {"id": "agent:render"},
        "intent": "read a rendered frame",
        "scope": {"allowed_actions": ["render_read"], "allowed_targets": []},
        "granted_at": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "revoked": False,
    }
    req = build_gate_request(
        action_kind="render_read",
        target="frame.png",
        authorization=receipt,
        drift=DriftVerdict(DRIFT, 30, "changed"),
    )
    # A DRIFT state denies even an authorized action -- grounded safety.
    decision = proof_surface.evaluate_gate(req)
    assert decision.decision == "deny"
