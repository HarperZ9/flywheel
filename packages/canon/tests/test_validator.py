"""Validator proof: every canonical fixture is clean; one negative per kind bites.

The F0 exit criterion is that the validator passes each of the five canonical
records with no problems and produces at least one problem for a deliberately
broken record of every kind, plus the envelope-level negatives (unknown kind,
bad scope, non-sha256 provenance, and a temporal block on the one kind that
forbids it).
"""
from __future__ import annotations

import copy

import pytest

from canon.schema import Record
from canon.validator import is_valid, validate_record

from ._helpers import RECORD_FILES, load_dict


@pytest.mark.parametrize("kind", list(RECORD_FILES))
def test_canonical_fixtures_validate_clean(kind: str) -> None:
    rec = Record.from_dict(load_dict(RECORD_FILES[kind]))
    problems = validate_record(rec)
    assert problems == [], f"{kind} should be clean, got {problems}"
    assert is_valid(rec)


def _broken(kind: str, mutate) -> Record:
    d = copy.deepcopy(load_dict(RECORD_FILES[kind]))
    mutate(d)
    return Record.from_dict(d)


def test_personality_block_missing_body() -> None:
    def drop_body(d):
        del d["data"]["body"]

    rec = _broken("personality-block", drop_body)
    problems = validate_record(rec)
    assert any("body" in p for p in problems), problems


def test_episodic_memory_bad_layer() -> None:
    def bad_layer(d):
        d["data"]["layer"] = "L9"

    rec = _broken("episodic-memory", bad_layer)
    problems = validate_record(rec)
    assert any("layer" in p for p in problems), problems


def test_synthesized_persona_wrong_layer() -> None:
    def wrong_layer(d):
        d["data"]["layer"] = "L1"

    rec = _broken("synthesized-persona-l3", wrong_layer)
    problems = validate_record(rec)
    assert any("L3" in p for p in problems), problems


def test_adr_decision_bad_status() -> None:
    def bad_status(d):
        d["data"]["status"] = "maybe"

    rec = _broken("adr-decision", bad_status)
    problems = validate_record(rec)
    assert any("status" in p for p in problems), problems


def test_research_artifact_ref_bad_hash() -> None:
    def bad_hash(d):
        d["data"]["artifact_hash"] = "not-a-sha256"

    rec = _broken("research-artifact-ref", bad_hash)
    problems = validate_record(rec)
    assert any("artifact_hash" in p for p in problems), problems


def test_research_artifact_ref_rejects_temporal_block() -> None:
    def add_temporal(d):
        d["temporal"] = {"valid_until": None, "supersedes": None}

    rec = _broken("research-artifact-ref", add_temporal)
    problems = validate_record(rec)
    assert any("temporal" in p for p in problems), problems


def test_unknown_kind_is_flagged() -> None:
    def bogus_kind(d):
        d["kind"] = "not-a-real-kind"

    rec = _broken("personality-block", bogus_kind)
    problems = validate_record(rec)
    assert any("unknown kind" in p for p in problems), problems


def test_unknown_scope_is_flagged() -> None:
    def bad_scope(d):
        d["scope"] = "repo"

    rec = _broken("personality-block", bad_scope)
    problems = validate_record(rec)
    assert any("scope" in p for p in problems), problems


def test_non_sha256_source_hash_is_flagged() -> None:
    def bad_source(d):
        d["provenance"]["source_hash"] = "deadbeef"

    rec = _broken("personality-block", bad_source)
    problems = validate_record(rec)
    assert any("source_hash" in p for p in problems), problems


def test_empty_id_is_flagged() -> None:
    def empty_id(d):
        d["id"] = ""

    rec = _broken("personality-block", empty_id)
    problems = validate_record(rec)
    assert any("id" in p for p in problems), problems


def test_temporal_supersedes_must_be_a_string() -> None:
    def int_supersedes(d):
        d["temporal"] = {"valid_until": None, "supersedes": 99}

    rec = _broken("personality-block", int_supersedes)
    problems = validate_record(rec)
    assert any("supersedes" in p for p in problems), problems


def test_temporal_supersedes_rejects_empty_string() -> None:
    def empty_supersedes(d):
        d["temporal"] = {"valid_until": None, "supersedes": ""}

    rec = _broken("personality-block", empty_supersedes)
    problems = validate_record(rec)
    assert any("supersedes" in p for p in problems), problems


def test_provenance_string_optional_rejects_non_string() -> None:
    def int_native_id(d):
        d["provenance"]["native_id"] = 123

    rec = _broken("personality-block", int_native_id)
    problems = validate_record(rec)
    assert any("native_id" in p for p in problems), problems


def test_unknown_kind_does_not_mask_other_envelope_problems() -> None:
    # An unknown kind must not short-circuit the kind-independent envelope
    # checks: the validator reports every problem at once, not one per re-run.
    def multi_defect(d):
        d["kind"] = "not-a-real-kind"
        d["scope"] = "repo"
        d["id"] = ""

    rec = _broken("personality-block", multi_defect)
    problems = validate_record(rec)
    assert any("unknown kind" in p for p in problems), problems
    assert any("scope" in p for p in problems), problems
    assert any("id must be" in p for p in problems), problems
