"""Typed source availability: honest retrievability, not silent paywall gaps.

Harvest of research/mycology-network-intelligence.md provenance boundary: record
source availability as open / abstract-only / publisher-blocked / author-copy /
unverifiable-from-local-corpus, rather than pretending an unretrievable source
was read. Optional and typed -- an unknown status is rejected.
"""

from __future__ import annotations

from proof_surface.research_claim import (
    build_research_claim_packet,
    validate_research_claim_packet,
)


def _packet(availability=None):
    source = {"ref": "PMC11995700"}
    if availability is not None:
        source["availability"] = availability
    return build_research_claim_packet(
        statement="fungi exhibit electrical activity",
        sources=[source],
        attempts=[{"attempt_id": "a1", "method": "review", "result": "bounded"}],
        checks=[{"checker": "manual", "status": "pass", "evidence": ["read abstract"]}],
        claim="c",
        scope="s",
        packet_id="rc-avail",
    )


def test_open_availability_validates():
    assert validate_research_claim_packet(_packet("open")) == []


def test_unverifiable_from_local_corpus_validates():
    # An honest "we could not lawfully retrieve this" is a first-class, valid state.
    assert (
        validate_research_claim_packet(_packet("unverifiable-from-local-corpus")) == []
    )


def test_unknown_availability_is_rejected():
    issues = validate_research_claim_packet(_packet("borrowed-from-a-friend"))
    assert any("availability" in i.path for i in issues)


def test_availability_is_optional():
    assert validate_research_claim_packet(_packet(None)) == []
