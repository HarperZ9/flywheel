"""Tests for LiveMembrane -- the living loop orchestrator."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from coherence_membrane.capture import IterableFrameSource
from coherence_membrane.live import LiveMembrane
from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.phash import DRIFT, MATCH


def _obs(subject, identity, fingerprint="00ff00ff00ff00ff"):
    return Observation(
        organ="visual-artifact", subject=subject, summary="observed", status=Status.PASS,
        provenance=Provenance.witness_bytes(subject, b"x", "high"),
        data={"identity_sha256": identity, "perceptual_hash": fingerprint},
    )


def test_reversible_action_flows_free():
    m = LiveMembrane()
    d = m.propose("draw", "canvas")
    assert d.gated is False
    assert d.decision == "allow"


def test_consequential_action_is_gated_and_fails_closed_without_write_gate(monkeypatch):
    monkeypatch.setitem(sys.modules, "proof_surface", None)  # no write-gate installed
    m = LiveMembrane()
    d = m.propose("publish", "site/index.html", authorization={})
    assert d.gated is True
    assert d.decision == "needs-human"  # never a fabricated allow


def test_authorize_then_baseline_match_and_drift():
    m = LiveMembrane()
    m.authorize(_obs("frame.png", "a" * 64, "0000000000000000"))
    assert m.baseline_check(_obs("frame.png", "a" * 64, "0000000000000000")).verdict == MATCH
    changed = m.baseline_check(_obs("frame.png", "b" * 64, "000000000000000f"))
    assert changed.verdict == DRIFT and changed.distance == 4


def test_baseline_check_without_baseline_is_unverifiable():
    m = LiveMembrane()
    assert m.baseline_check(_obs("frame.png", "a" * 64)).verdict == "UNVERIFIABLE"


def test_perceive_runs_continuity(make_png):
    png = make_png(8, 8, bytes((i * 5) % 256 for i in range(8 * 8 * 3)))
    m = LiveMembrane()
    events = list(m.perceive(IterableFrameSource([png, png], pixel_format="png")))
    assert len(events) == 2
    assert events[0].verdict == DRIFT and events[1].verdict == MATCH


# --- end-to-end with the real write-gate, if available ---------------------

def _proof_surface_src() -> Path:
    return Path(__file__).resolve().parents[2] / "proof-surface" / "src"


def test_consequential_action_allowed_when_authorized_and_match():
    src = _proof_surface_src()
    if src.exists():
        sys.path.insert(0, str(src))
    pytest.importorskip("proof_surface")
    from coherence_membrane.phash import MATCH as M, DriftVerdict

    now = datetime.now(timezone.utc)
    receipt = {
        "authorization_version": "0.1", "receipt_id": "r1", "kind": "authorization-grant",
        "principal": {"id": "operator"}, "agent": {"id": "agent:studio"},
        "intent": "publish a reviewed artifact",
        "scope": {"allowed_actions": ["publish"], "allowed_targets": []},
        "granted_at": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(), "revoked": False,
    }
    m = LiveMembrane()
    d = m.propose("publish", "site/index.html", authorization=receipt,
                  drift=DriftVerdict(M, 0, "identical"))
    assert d.gated is True
    assert d.decision == "allow"
