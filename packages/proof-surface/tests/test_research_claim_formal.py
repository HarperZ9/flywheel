"""Formal-proof-status + kernel-replay disclosure: no proof overreach.

A PASSED Lean/kernel replay must disclose the exact axiom set, toolchain, and
blob-byte source binding, or it does not validate.
"""

from __future__ import annotations

from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)

_HEX = "a" * 64


def _packet(formal):
    return build_research_claim_packet(
        statement="a theorem",
        sources=[{"ref": "s"}],
        attempts=[{"attempt_id": "a1", "method": "lean", "result": "proved"}],
        checks=[{"checker": "lean", "status": "pass", "evidence": ["kernel exit 0"]}],
        claim="c",
        scope="s",
        packet_id="rc",
        formal=formal,
    )


def test_passed_replay_with_full_disclosure_validates():
    formal = {
        "kernel_checked": True,
        "compiled_replay_status": "PASSED",
        "axioms": ["propext", "Classical.choice", "Quot.sound"],
        "toolchain": "lean4@abc123",
        "source_sha256": _HEX,
    }
    packet = _packet(formal)
    assert validate_research_claim_packet(packet) == []
    assert packet["formal"]["compiled_replay_status"] == "PASSED"


def test_passed_replay_without_axioms_is_rejected():
    formal = {
        "kernel_checked": True,
        "compiled_replay_status": "PASSED",
        "axioms": [],
        "toolchain": "lean4",
        "source_sha256": _HEX,
    }
    assert any(
        "formal" in i.path for i in validate_research_claim_packet(_packet(formal))
    )


def test_not_run_replay_needs_no_disclosure():
    formal = {
        "kernel_checked": False,
        "compiled_replay_status": "NOT_RUN",
        "axioms": [],
    }
    assert validate_research_claim_packet(_packet(formal)) == []


def test_unknown_replay_status_is_rejected():
    formal = {"kernel_checked": False, "compiled_replay_status": "MAYBE", "axioms": []}
    issues = validate_research_claim_packet(_packet(formal))
    assert any("compiled_replay_status" in i.path for i in issues)


def test_formal_is_optional():
    # a research packet without a formal block still validates
    assert validate_research_claim_packet(_packet(None)) == []
