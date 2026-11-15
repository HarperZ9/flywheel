"""test_canon_check.py -- M4.4 optional composition. Covers the four-leg
aggregate verdict `canon_check` folds into one gate a build keys on: drift,
vault round-trip, vault symmetric round-trip, and persona basis. Each leg
opts in via its injected seam; a leg without its seam wired reports None.
The composition raises nothing on hostile input the underlying legs handle.
"""
from __future__ import annotations

import pytest

from canon.canon_check import (
    CanonCheckReport,
    canon_check,
    canon_check_exit_code,
)
from canon.persona_thesis import (
    DRIFT_KEY,
    MATCH_KEY,
    UNVERIFIABLE_KEY,
    DRIFT,
    MATCH,
    UNVERIFIABLE,
)
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    KIND_SYNTHESIZED_PERSONA_L3,
    Provenance,
    Record,
    Temporal,
)


def _block(id_: str, *, scope: str = "global", body: str = "b") -> Record:
    prov = Provenance(harness="author", source_hash="a" * 64, create_ord=1)
    return Record(
        kind=KIND_PERSONALITY_BLOCK, id=id_, scope=scope,
        data={"title": id_, "body": body}, provenance=prov,
        temporal=Temporal(valid_until=None, supersedes=None))


def _source(id_: str, *, ord_: int = 100) -> Record:
    prov = Provenance(harness="mneme", source_hash="b" * 64, create_ord=ord_)
    return Record(
        kind=KIND_EPISODIC_MEMORY, id=id_, scope="global",
        data={"layer": "L1", "text": f"memory {id_}", "source_ids": []},
        provenance=prov,
        temporal=Temporal(valid_until=None, supersedes=None))


def _persona(id_: str, source_ids: list[str]) -> Record:
    prov = Provenance(harness="mneme", source_hash="c" * 64, create_ord=205)
    return Record(
        kind=KIND_SYNTHESIZED_PERSONA_L3, id=id_, scope="global",
        data={"layer": "L3", "text": "a faithful summary",
              "source_ids": list(source_ids)},
        provenance=prov,
        temporal=Temporal(valid_until=None, supersedes=None))


def _match_assessor(payload):
    return {MATCH_KEY: len(payload["claims"]), DRIFT_KEY: 0,
            UNVERIFIABLE_KEY: 0}


def _drift_assessor(payload):
    return {MATCH_KEY: 0, DRIFT_KEY: 1,
            UNVERIFIABLE_KEY: len(payload["claims"]) - 1}


def _unverifiable_assessor(payload):
    return {MATCH_KEY: 0, DRIFT_KEY: 0,
            UNVERIFIABLE_KEY: len(payload["claims"])}


def _missing_read_text(path):
    """Every managed surface reads as missing, which drift counts as ok."""
    return None


def test_canon_check_all_ok_with_all_seams_injected():
    """Every leg wired, every leg passes: aggregate ok, exit_code 0."""
    pool = [_block("tone"), _source("m1"), _persona("p1", ["m1"])]
    result = canon_check(
        pool, home="H:/home", workspace="W:/work",
        read_text=_missing_read_text, assess=_match_assessor)
    assert result.ok is True
    assert result.exit_code == 0
    assert result.drift is not None and result.drift.ok is True
    assert result.vault is not None and result.vault.ok is True
    assert result.vault_symmetric is not None
    assert result.vault_symmetric.ok is True
    assert result.persona is not None
    assert len(result.persona) == 1
    assert result.persona[0].verdict == MATCH
    assert result.reasons == ()


def test_canon_check_ok_with_only_pool_and_roundtrip():
    """No seams beyond the pool: vault + vault_symmetric run, drift and
    persona report None. The pool alone verifies at MATCH."""
    pool = [_block("tone"), _block("voice")]
    result = canon_check(pool)
    assert result.ok is True
    assert result.exit_code == 0
    assert result.drift is None
    assert result.persona is None
    assert result.vault is not None and result.vault.ok is True
    assert result.vault_symmetric is not None
    assert result.vault_symmetric.ok is True


def test_canon_check_reports_none_for_disabled_legs():
    """A leg with no seam wired reports None in the corresponding field,
    and its absence does not affect ok."""
    pool = [_block("tone")]
    result = canon_check(pool)
    assert result.drift is None
    assert result.persona is None
    # Partial drift seam is still None (all three of home/workspace/read_text
    # required per the docstring).
    result_no_home = canon_check(
        pool, workspace="W:/work", read_text=_missing_read_text)
    assert result_no_home.drift is None
    result_no_ws = canon_check(
        pool, home="H:/home", read_text=_missing_read_text)
    assert result_no_ws.drift is None
    result_no_rt = canon_check(pool, home="H:/home", workspace="W:/work")
    assert result_no_rt.drift is None


def test_canon_check_ok_false_on_drift_report_ok_false():
    """A drift refusal in one surface fails the aggregate; reason names
    drift."""
    pool = [_block("tone")]

    def deformed_read(path):
        # Fake host content that carries markers with an unclosed region so
        # extract_region refuses.
        return "prefix\n<!-- canon:begin scope=global -->\nno closer"

    result = canon_check(
        pool, home="H:/home", workspace="W:/work",
        read_text=deformed_read, assess=None)
    assert result.ok is False
    assert result.exit_code == 1
    assert "drift" in result.reasons
    assert result.drift is not None and result.drift.ok is False


def test_canon_check_ok_false_on_vault_verdict_ok_false():
    """A pool the vault codec cannot round-trip fails the aggregate; reason
    names vault or vault_symmetric (both refuse on an unrepresentable
    record)."""
    prov = Provenance(harness="author", source_hash="a" * 64, create_ord=1)
    # A personality-block missing its required 'body' field: validate_record
    # refuses inside vault_roundtrip_report.
    bad = Record(
        kind=KIND_PERSONALITY_BLOCK, id="bad", scope="global",
        data={"title": "bad"}, provenance=prov,
        temporal=Temporal(valid_until=None, supersedes=None))
    result = canon_check([bad])
    assert result.ok is False
    assert result.exit_code == 1
    assert "vault" in result.reasons or "vault_symmetric" in result.reasons


def test_canon_check_ok_false_on_persona_thesis_refused():
    """A persona whose basis the assessor calls DRIFT fails the aggregate;
    reason names the persona verdict."""
    pool = [_block("tone"), _source("m1"), _persona("p1", ["m1"])]
    result = canon_check(pool, assess=_drift_assessor)
    assert result.ok is False
    assert result.exit_code == 1
    assert f"persona:{DRIFT}" in result.reasons
    assert result.persona is not None
    assert result.persona[0].verdict == DRIFT


def test_canon_check_ok_false_on_symmetric_report_refused():
    """A record shape both fidelity legs refuse fails the aggregate. Uses
    the same missing-required-field record; both vault and vault_symmetric
    surface the refusal."""
    prov = Provenance(harness="author", source_hash="a" * 64, create_ord=1)
    bad = Record(
        kind=KIND_PERSONALITY_BLOCK, id="bad", scope="global",
        data={"title": "bad"}, provenance=prov,
        temporal=Temporal(valid_until=None, supersedes=None))
    result = canon_check([bad])
    assert result.ok is False
    assert result.vault_symmetric is not None
    assert result.vault_symmetric.ok is False


def test_canon_check_reasons_names_each_failed_leg():
    """Two failing legs at once produce two reasons in the tuple."""
    pool = [_block("tone"), _source("m1"), _persona("p1", ["m1"])]

    def deformed_read(path):
        return "prefix\n<!-- canon:begin scope=global -->\nno closer"

    result = canon_check(
        pool, home="H:/home", workspace="W:/work",
        read_text=deformed_read, assess=_unverifiable_assessor)
    assert result.ok is False
    assert "drift" in result.reasons
    assert f"persona:{UNVERIFIABLE}" in result.reasons
    # Two failure classes, two labels, both present.
    assert len([r for r in result.reasons
                if r == "drift" or r.startswith("persona:")]) == 2


def test_canon_check_exit_code_is_0_iff_ok():
    """canon_check_exit_code mirrors drift_exit_code and reconcile_exit_code:
    0 iff every wired leg passed, 1 otherwise."""
    ok_result = canon_check([_block("tone")])
    assert ok_result.ok is True
    assert canon_check_exit_code(ok_result) == 0
    assert ok_result.exit_code == 0

    prov = Provenance(harness="author", source_hash="a" * 64, create_ord=1)
    bad = Record(
        kind=KIND_PERSONALITY_BLOCK, id="bad", scope="global",
        data={"title": "bad"}, provenance=prov,
        temporal=Temporal(valid_until=None, supersedes=None))
    bad_result = canon_check([bad])
    assert bad_result.ok is False
    assert canon_check_exit_code(bad_result) == 1
    assert bad_result.exit_code == 1


@pytest.mark.parametrize("pool", [
    [],
    [_block("tone")],
    [_persona("p1", [])],  # empty basis: persona reports UNVERIFIABLE
    [_persona("p1", ["missing-source"])],  # basis-present fails
    [_block("tone"), _source("m1"), _persona("p1", ["m1"])],
])
def test_canon_check_never_raises(pool):
    """canon_check raises nothing on any input the underlying legs handle.
    Runs every leg with a seam wired so every code path exercises."""
    result = canon_check(
        pool, home="H:/home", workspace="W:/work",
        read_text=_missing_read_text, assess=_match_assessor)
    assert isinstance(result, CanonCheckReport)
    assert result.exit_code in (0, 1)
    assert isinstance(result.reasons, tuple)
