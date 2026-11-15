"""Refutation gate: a standing counterexample outranks any fixture-level pass.

Harvest of the operator-supplied verification-frontier corpus (a decades-old
computing belief killed by one counterexample; kernel-checked formalization).
Two gates: (1) a packet with a standing counterexample (a `refuted` attempt or
`formal.counterexample_found=true`) must carry promotion REFUTED -- passing
checks do not outweigh a counterexample; symmetrically, REFUTED may not be
claimed without one. (2) a PASSED kernel replay with unresolved `sorry` holes is
not a proof and is rejected.
"""

from __future__ import annotations

from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)

_HEX = "a" * 64


def _packet(*, result="proved", formal=None, promotion=None):
    return build_research_claim_packet(
        statement="every open-addressing scheme needs (log n) probe time",
        sources=[{"ref": "arxiv:2501.02305"}],
        attempts=[{"attempt_id": "a1", "method": "construction", "result": result}],
        checks=[{"checker": "review", "status": "pass", "evidence": ["checked"]}],
        claim="c",
        scope="s",
        packet_id="rc-refute",
        formal=formal,
        promotion=promotion,
    )


def test_refuted_attempt_derives_promotion_refuted():
    packet = _packet(result="refuted")
    assert packet["promotion"] == "REFUTED"
    assert validate_research_claim_packet(packet) == []


def test_refuted_attempt_with_positive_promotion_is_rejected():
    # Passing checks do not outweigh a standing counterexample.
    packet = _packet(result="refuted", promotion="CRUCIBLE_MATCH")
    assert any(i.path == "$.promotion" for i in validate_research_claim_packet(packet))


def test_formal_counterexample_forces_refuted():
    formal = {
        "kernel_checked": True,
        "compiled_replay_status": "NOT_RUN",
        "axioms": [],
        "counterexample_found": True,
    }
    packet = _packet(formal=formal, promotion="LAW_CANDIDATE")
    assert any(i.path == "$.promotion" for i in validate_research_claim_packet(packet))


def test_refuted_claimed_without_a_counterexample_is_rejected():
    # The symmetric overclaim: you may not claim a refutation you do not hold.
    packet = _packet(result="proved", promotion="REFUTED")
    assert any(i.path == "$.promotion" for i in validate_research_claim_packet(packet))


def test_passed_replay_with_unresolved_sorry_is_rejected():
    # A kernel replay that "passed" with admitted holes proves nothing.
    formal = {
        "kernel_checked": True,
        "compiled_replay_status": "PASSED",
        "axioms": ["propext"],
        "toolchain": "lean4@abc",
        "source_sha256": _HEX,
        "unresolved_sorry": 2,
    }
    packet = _packet(formal=formal)
    assert any(
        "unresolved_sorry" in i.path for i in validate_research_claim_packet(packet)
    )


def test_passed_replay_with_zero_sorries_is_valid():
    formal = {
        "kernel_checked": True,
        "compiled_replay_status": "PASSED",
        "axioms": ["propext"],
        "toolchain": "lean4@abc",
        "source_sha256": _HEX,
        "unresolved_sorry": 0,
    }
    assert validate_research_claim_packet(_packet(formal=formal)) == []


def test_non_integer_sorry_count_is_rejected():
    formal = {
        "kernel_checked": False,
        "compiled_replay_status": "NOT_RUN",
        "axioms": [],
        "unresolved_sorry": "a few",
    }
    assert any(
        "unresolved_sorry" in i.path
        for i in validate_research_claim_packet(_packet(formal=formal))
    )
