"""The registry: which criteria exist, which may mint rewards, and what a change
to one invalidates.

Plain JSON on disk so a fork edits data rather than Python. Append-only: a
superseded criterion stays readable, because a record that can be tidied is not
a record. Admission is where the refusals bite, so a criterion that cannot mint
a reward can still be registered for evaluation and is marked as such rather
than silently accepted.
"""
import json

import pytest

from harness.criteria.spec import Criterion, DecisionRule, Domain
from harness.oracle_qa import qa_battery
from harness.certificates.zarankiewicz import ZarankiewiczOracle, encode

from harness.criteria.registry import (
    Registry, RegistryError, Incumbent, InvalidationCode,
)

_FANO_LINES = [(0, 1, 2), (0, 3, 4), (0, 5, 6), (1, 3, 5),
               (1, 4, 6), (2, 3, 6), (2, 4, 5)]
_FANO_EDGES = [(p, li) for li, pts in enumerate(_FANO_LINES) for p in pts]


def _card(family="zarankiewicz"):
    """A passing QA card. Admission requires one before a criterion may mint a
    reward, so every eligibility assertion here supplies it."""
    certs = [encode(7, 7, _FANO_EDGES)]
    for n in (5, 9, 13):
        certs.append(encode(4, n, [(0, j) for j in range(n)]))
    card = qa_battery(ZarankiewiczOracle(), certs, seed=5)
    card.family = family
    return card


def _c(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2",
        version=1,
        family="zarankiewicz",
        generator_id="zarankiewicz.bipartite.v1",
        generator_version=1,
        seed_range=(0, 1024),
        objective_direction="maximize",
        objective_normalization="ratio_to_incumbent",
        reward_mapping={"valid_gate": True, "scale": "linear"},
        incumbent_source="operator_search",
        scope_bounds={"m_max": 40, "n_max": 40},
        decision_rule=DecisionRule.CONJUNCTIVE,
        domain=Domain.CONSTRUCTIVE,
        license_id="Apache-2.0",
    )
    base.update(kw)
    return Criterion(**base)


def _reg(tmp_path):
    return Registry(tmp_path / "registry.json")


# --- admission ---------------------------------------------------------------

def test_a_clean_criterion_is_admitted_and_reward_eligible(tmp_path):
    r = _reg(tmp_path)
    entry = r.admit(_c(), qa_card=_card())
    assert entry["reward_eligible"] is True
    assert entry["reward_ineligible_reason"] == ""
    assert entry["criterion_sha256"] == _c().sha256()


def test_a_non_conjunctive_criterion_is_registered_but_not_reward_eligible(tmp_path):
    r = _reg(tmp_path)
    entry = r.admit(_c(decision_rule=DecisionRule.MAJORITY))
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "NON_CONJUNCTIVE_RULE"


def test_an_interpretive_criterion_is_registered_but_not_reward_eligible(tmp_path):
    r = _reg(tmp_path)
    entry = r.admit(_c(criterion_id="poetry.tone", family="poetry",
                       domain=Domain.INTERPRETIVE))
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "INTERPRETIVE_DOMAIN"


def test_reward_eligible_ids_lists_only_the_eligible(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c(), qa_card=_card())
    r.admit(_c(criterion_id="poetry.tone", family="poetry",
               domain=Domain.INTERPRETIVE), qa_card=_card("poetry"))
    assert r.reward_eligible_ids() == ["zarankiewicz.z_2_2"]


def test_admitting_the_same_criterion_twice_is_idempotent(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c())
    r.admit(_c())
    assert len(r.entries()) == 1


def test_a_different_criterion_reusing_an_id_without_lineage_is_refused(tmp_path):
    # This is the retcon: same id, different content, no parent hash. If it were
    # allowed, "criterion zarankiewicz.z_2_2" would mean two different things.
    r = _reg(tmp_path)
    r.admit(_c())
    with pytest.raises(RegistryError):
        r.admit(_c(scope_bounds={"m_max": 999, "n_max": 999}))


def test_a_properly_amended_criterion_is_admitted_as_a_new_version(tmp_path):
    r = _reg(tmp_path)
    a = _c()
    r.admit(a)
    b = a.amend("the m_max bound was too tight", scope_bounds={"m_max": 60})
    entry = r.admit(b)
    assert entry["version"] == 2
    assert len(r.entries()) == 2


def test_an_amendment_whose_parent_is_absent_is_refused(tmp_path):
    r = _reg(tmp_path)
    orphan = _c().amend("no parent registered", scope_bounds={"m_max": 60})
    with pytest.raises(RegistryError):
        r.admit(orphan)


# --- incumbents --------------------------------------------------------------

def test_an_operator_search_incumbent_needs_no_citation(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c())
    r.set_incumbent(Incumbent(
        criterion_id="zarankiewicz.z_2_2", value="52",
        source="operator_search", citations=[],
        provenance_hash="sha256:" + "a" * 64))
    assert r.incumbent("zarankiewicz.z_2_2").value == "52"


def test_a_published_incumbent_needs_two_independent_citations(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c())
    with pytest.raises(RegistryError):
        r.set_incumbent(Incumbent(
            criterion_id="zarankiewicz.z_2_2", value="52",
            source="published_table", citations=["arXiv:2605.01120"],
            provenance_hash="sha256:" + "b" * 64))
    r.set_incumbent(Incumbent(
        criterion_id="zarankiewicz.z_2_2", value="52",
        source="published_table",
        citations=["arXiv:2605.01120", "doi:10.1000/xyz"],
        provenance_hash="sha256:" + "b" * 64))
    assert r.incumbent("zarankiewicz.z_2_2").source == "published_table"


def test_an_incumbent_for_an_unregistered_criterion_is_refused(tmp_path):
    r = _reg(tmp_path)
    with pytest.raises(RegistryError):
        r.set_incumbent(Incumbent(
            criterion_id="nope", value="1", source="operator_search",
            citations=[], provenance_hash="sha256:" + "c" * 64))


def test_an_incumbent_value_is_a_decimal_string_never_a_float(tmp_path):
    # No floats in any hashed field: cross-platform float formatting is the
    # likeliest cause of a stranger's replay disagreeing.
    r = _reg(tmp_path)
    r.admit(_c())
    with pytest.raises(RegistryError):
        r.set_incumbent(Incumbent(
            criterion_id="zarankiewicz.z_2_2", value=52.0,
            source="operator_search", citations=[],
            provenance_hash="sha256:" + "d" * 64))


# --- invalidation ------------------------------------------------------------

def test_invalidating_names_a_typed_reason_and_keeps_the_record(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c())
    r.invalidate("zarankiewicz.z_2_2", 1,
                 InvalidationCode.REFERENCE_SET_REVISED,
                 "the published table was corrected")
    e = r.entry("zarankiewicz.z_2_2", 1)
    assert e["status"] == "invalidated"
    assert e["invalidation"]["reason_code"] == "REFERENCE_SET_REVISED"
    assert e["invalidation"]["note"] == "the published table was corrected"
    # The record is still there. Invalidation appends, it does not delete.
    assert len(r.entries()) == 1


def test_an_invalidated_criterion_is_not_reward_eligible(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c(), qa_card=_card())
    r.invalidate("zarankiewicz.z_2_2", 1, InvalidationCode.ORACLE_QA_FAILED,
                 "false accepts above the declared bound")
    assert r.reward_eligible_ids() == []


def test_an_untyped_invalidation_reason_is_refused(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c())
    with pytest.raises(RegistryError):
        r.invalidate("zarankiewicz.z_2_2", 1, "because I said so", "note")


def test_amending_marks_the_parent_superseded_not_deleted(tmp_path):
    r = _reg(tmp_path)
    a = _c()
    r.admit(a, qa_card=_card())
    r.admit(a.amend("wider bound", scope_bounds={"m_max": 60}), qa_card=_card())
    assert r.entry("zarankiewicz.z_2_2", 1)["status"] == "superseded"
    assert r.entry("zarankiewicz.z_2_2", 2)["status"] == "live"
    assert r.reward_eligible_ids() == ["zarankiewicz.z_2_2"]


# --- persistence -------------------------------------------------------------

def test_the_registry_is_plain_json_a_fork_can_edit(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c())
    raw = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert raw["schema"] == "flywheel.criterion-registry/v1"
    assert raw["entries"][0]["criterion"]["family"] == "zarankiewicz"


def test_a_reloaded_registry_sees_the_same_entries(tmp_path):
    _reg(tmp_path).admit(_c(), qa_card=_card())
    again = _reg(tmp_path)
    assert len(again.entries()) == 1
    assert again.reward_eligible_ids() == ["zarankiewicz.z_2_2"]


def test_a_corrupt_registry_file_fails_loudly_rather_than_silently_empty(tmp_path):
    (tmp_path / "registry.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RegistryError):
        _reg(tmp_path).entries()


def test_a_tampered_entry_hash_is_detected_on_load(tmp_path):
    r = _reg(tmp_path)
    r.admit(_c())
    p = tmp_path / "registry.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["entries"][0]["criterion"]["scope_bounds"]["m_max"] = 999
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryError):
        _reg(tmp_path).entries()
