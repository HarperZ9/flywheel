"""The criterion: what would count, decided before the attempt.

A criterion that lives in runtime config can be edited after a miss and nobody
sees it happen. Making it a hash-pinned object whose amendments record their
parent and their reason turns a quiet retcon into an append-only event.

Two shapes are refused reward eligibility outright:
  - a non-conjunctive decision rule, because votes propose and proofs dispose,
  - an interpretive domain, because a poem has no kernel.
"""
import pytest

from harness.criteria.spec import (
    Criterion, DecisionRule, Domain, CriterionError,
)


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


def test_sha256_is_stable_and_full_length():
    a, b = _c(), _c()
    assert a.sha256() == b.sha256()
    assert a.sha256().startswith("sha256:")
    assert len(a.sha256().split(":", 1)[1]) == 64


def test_any_field_change_changes_the_hash():
    base = _c().sha256()
    assert _c(version=2).sha256() != base
    assert _c(seed_range=(0, 2048)).sha256() != base
    assert _c(scope_bounds={"m_max": 41, "n_max": 40}).sha256() != base
    assert _c(reward_mapping={"valid_gate": False}).sha256() != base
    assert _c(license_id="MIT").sha256() != base


def test_dict_key_order_does_not_change_the_hash():
    # Canonical JSON, or two honest parties disagree over nothing.
    a = _c(scope_bounds={"m_max": 40, "n_max": 40})
    b = _c(scope_bounds={"n_max": 40, "m_max": 40})
    assert a.sha256() == b.sha256()


def test_amend_records_its_parent_and_reason_and_bumps_the_version():
    a = _c()
    b = a.amend("incumbent table was revised",
                scope_bounds={"m_max": 50, "n_max": 50})
    assert b.parent_sha256 == a.sha256()
    assert b.change_reason == "incumbent table was revised"
    assert b.version == a.version + 1
    assert b.sha256() != a.sha256()


def test_amend_without_a_reason_is_refused():
    with pytest.raises(CriterionError):
        _c().amend("", scope_bounds={"m_max": 50})
    with pytest.raises(CriterionError):
        _c().amend("   ", scope_bounds={"m_max": 50})


def test_amend_cannot_silently_change_the_family_or_id():
    with pytest.raises(CriterionError):
        _c().amend("sneaky", family="something_else")
    with pytest.raises(CriterionError):
        _c().amend("sneaky", criterion_id="other.id")


def test_amending_twice_chains_the_lineage():
    a = _c()
    b = a.amend("first", scope_bounds={"m_max": 50})
    c = b.amend("second", scope_bounds={"m_max": 60})
    assert c.parent_sha256 == b.sha256()
    assert b.parent_sha256 == a.sha256()
    assert c.version == 3


def test_conjunctive_rules_are_reward_eligible():
    ok, reason = _c(decision_rule=DecisionRule.CONJUNCTIVE).reward_eligible()
    assert ok is True
    assert reason == "ok"


def test_non_conjunctive_rules_are_refused_reward_eligibility():
    for rule in (DecisionRule.DISJUNCTIVE, DecisionRule.MAJORITY,
                 DecisionRule.WEIGHTED):
        ok, reason = _c(decision_rule=rule).reward_eligible()
        assert ok is False, rule
        assert reason == "NON_CONJUNCTIVE_RULE"


def test_an_interpretive_domain_is_never_reward_eligible():
    # A poem has no kernel. The fence lives in the criterion, not in a reviewer's
    # judgement, because a general assessor slides into quality judgement by
    # default.
    ok, reason = _c(domain=Domain.INTERPRETIVE).reward_eligible()
    assert ok is False
    assert reason == "INTERPRETIVE_DOMAIN"


def test_an_empirical_domain_is_not_reward_eligible_either():
    # A measurement can inform, but it cannot mint a training reward here: the
    # accept path is restricted to domains a deterministic checker disposes.
    ok, reason = _c(domain=Domain.EMPIRICAL).reward_eligible()
    assert ok is False
    assert reason == "NON_DISPOSITIVE_DOMAIN"


def test_the_domain_fence_is_checked_before_the_decision_rule():
    # An interpretive criterion with a conjunctive rule is still refused, and the
    # reason names the domain rather than the rule.
    ok, reason = _c(domain=Domain.INTERPRETIVE,
                    decision_rule=DecisionRule.MAJORITY).reward_eligible()
    assert ok is False
    assert reason == "INTERPRETIVE_DOMAIN"


def test_an_empty_seed_range_is_refused_at_construction():
    with pytest.raises(CriterionError):
        _c(seed_range=(100, 100))


def test_a_backwards_seed_range_is_refused():
    with pytest.raises(CriterionError):
        _c(seed_range=(100, 10))


def test_an_unknown_objective_direction_is_refused():
    with pytest.raises(CriterionError):
        _c(objective_direction="sideways")


def test_a_missing_id_or_family_is_refused():
    with pytest.raises(CriterionError):
        _c(criterion_id="")
    with pytest.raises(CriterionError):
        _c(family="")


def test_to_dict_roundtrips_through_from_dict():
    a = _c()
    assert Criterion.from_dict(a.to_dict()).sha256() == a.sha256()


def test_to_dict_carries_the_hash_for_a_reader_who_never_runs_python():
    d = _c().to_dict()
    assert d["criterion_sha256"] == _c().sha256()
    assert d["domain"] == "CONSTRUCTIVE"
    assert d["decision_rule"] == "CONJUNCTIVE"


def test_a_criterion_is_frozen_so_it_cannot_drift_in_place():
    a = _c()
    with pytest.raises(Exception):
        a.version = 99
