"""Evidence independence: single-modality evidence caps at the hypothesis rung.

Shared-spine gate (src/proof_surface/_evidence_classes.py) wired into
research_claim, grounded in dogfood 0126: a fact-tier promotion (CRUCIBLE_MATCH
and above on the research_claim ladder) requires at least one evidence class
that is not single-modality-derived. Evidence that is entirely
single-modality-derived caps the promotion at HYPOTHESIS. Off-ladder honesty
rungs (UNVERIFIABLE, REFUTED) claim no achievement and are never capped.
"""

from __future__ import annotations

from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)

_HEX = "a" * 64


def _paths(issues):
    return [i.path for i in issues]


def _packet(evidence_classes=None, promotion=None):
    packet = build_research_claim_packet(
        statement="for all n >= 1, sum_{k=1}^n k = n(n+1)/2",
        sources=[{"ref": "probe log", "sha256": _HEX}],
        attempts=[{"attempt_id": "a1", "method": "numeric-probe", "result": "bounded"}],
        checks=[
            {"checker": "numeric-probe", "status": "pass", "evidence": ["n=1..1000"]}
        ],
        claim="the identity held under a bounded probe",
        scope="bounded probe; not a general proof",
        packet_id="rc-ei",
        promotion=promotion,
    )
    if evidence_classes is not None:
        packet["evidence_classes"] = evidence_classes
    return packet


def test_evidence_classes_is_optional():
    assert validate_research_claim_packet(_packet()) == []


def test_fact_promotion_with_independent_class_validates():
    # Default derived promotion is CRUCIBLE_MATCH (fact tier).
    packet = _packet(["executable-check", "single-modality-derived"])
    assert validate_research_claim_packet(packet) == []


def test_fact_promotion_single_modality_only_rejected():
    issues = validate_research_claim_packet(_packet(["single-modality-derived"]))
    assert any(p == "$.promotion" for p in _paths(issues))


def test_law_candidate_single_modality_only_rejected():
    packet = _packet(["single-modality-derived"], promotion="LAW_CANDIDATE")
    issues = validate_research_claim_packet(packet)
    assert any(p == "$.promotion" for p in _paths(issues))


def test_single_modality_caps_below_probe_match():
    # The cap is HYPOTHESIS, not just the fact tier: PROBE_MATCH is above it.
    packet = _packet(["single-modality-derived"], promotion="PROBE_MATCH")
    issues = validate_research_claim_packet(packet)
    assert any(p == "$.promotion" for p in _paths(issues))


def test_hypothesis_with_single_modality_validates():
    packet = _packet(["single-modality-derived"], promotion="HYPOTHESIS")
    assert validate_research_claim_packet(packet) == []


def test_source_lead_with_single_modality_validates():
    packet = _packet(["single-modality-derived"], promotion="SOURCE_LEAD")
    assert validate_research_claim_packet(packet) == []


def test_off_ladder_unverifiable_is_never_capped():
    packet = _packet(["single-modality-derived"], promotion="UNVERIFIABLE")
    assert validate_research_claim_packet(packet) == []


def test_every_vocabulary_class_is_accepted():
    packet = _packet(
        [
            "primary-source",
            "independent-replication",
            "executable-check",
            "human-review",
            "single-modality-derived",
        ]
    )
    assert validate_research_claim_packet(packet) == []


def test_unknown_evidence_class_rejected():
    issues = validate_research_claim_packet(
        _packet(["executable-check", "gut-feeling"])
    )
    assert any("evidence_classes[1]" in p for p in _paths(issues))


def test_empty_evidence_classes_rejected():
    # Declared means at least one class; an empty declaration is not disclosure.
    issues = validate_research_claim_packet(_packet([]))
    assert any("evidence_classes" in p for p in _paths(issues))


def test_duplicate_evidence_class_rejected():
    issues = validate_research_claim_packet(
        _packet(["executable-check", "executable-check"])
    )
    assert any("evidence_classes[1]" in p for p in _paths(issues))


def test_builder_passes_evidence_classes_through():
    packet = build_research_claim_packet(
        statement="s",
        sources=[{"ref": "r"}],
        attempts=[{"attempt_id": "a1", "method": "probe", "result": "bounded"}],
        checks=[{"checker": "probe", "status": "pass", "evidence": ["ok"]}],
        claim="c",
        scope="s",
        packet_id="rc-ei-b",
        evidence_classes=["executable-check"],
    )
    assert packet["evidence_classes"] == ["executable-check"]
    assert validate_research_claim_packet(packet) == []
