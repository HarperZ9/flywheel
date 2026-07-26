"""No QA card, no reward eligibility. Enforced at admission, not documented.

The criterion answers "does this SHAPE permit a reward" (a conjunctive rule, a
domain a deterministic checker disposes). The card answers "is the checker that
will grade it actually sound". Both must hold.

Phase 1A built both halves and wired neither, so an unmeasured checker was
reward-eligible: exactly the condition the QA gate exists to prevent.
"""
import pytest

from harness.criteria.spec import Criterion, DecisionRule, Domain
from harness.criteria.registry import Registry, RegistryError
from harness.oracle_qa import qa_battery
from harness.certificates.zarankiewicz import ZarankiewiczOracle, encode
from harness.certificates.base import Coverage

FANO_LINES = [(0, 1, 2), (0, 3, 4), (0, 5, 6), (1, 3, 5),
              (1, 4, 6), (2, 3, 6), (2, 4, 5)]
FANO_EDGES = [(p, li) for li, pts in enumerate(FANO_LINES) for p in pts]


def _valid_certs():
    out = [encode(7, 7, FANO_EDGES)]
    for n in (5, 9, 13):
        out.append(encode(4, n, [(0, j) for j in range(n)]))
    return out


def _card():
    return qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)


def _c(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2", version=1, family="zarankiewicz",
        generator_id="zarankiewicz.bipartite.v1", generator_version=1,
        seed_range=(0, 1024), objective_direction="maximize",
        objective_normalization="ratio_to_incumbent",
        reward_mapping={"valid_gate": True}, incumbent_source="operator_search",
        scope_bounds={"m_max": 40}, decision_rule=DecisionRule.CONJUNCTIVE,
        domain=Domain.CONSTRUCTIVE, license_id="Apache-2.0")
    base.update(kw)
    return Criterion(**base)


def test_a_criterion_admitted_without_a_card_is_not_reward_eligible(tmp_path):
    r = Registry(tmp_path / "r.json")
    entry = r.admit(_c())
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "QA_CARD_ABSENT"


def test_a_passing_card_makes_a_clean_criterion_reward_eligible(tmp_path):
    r = Registry(tmp_path / "r.json")
    card = _card()
    assert card.passed is True
    entry = r.admit(_c(), qa_card=card)
    assert entry["reward_eligible"] is True
    assert entry["reward_ineligible_reason"] == ""


def test_a_failing_card_blocks_reward_eligibility(tmp_path):
    class _Lax(ZarankiewiczOracle):
        def check(self, cert):
            return True, "accepts anything", Coverage(
                True, True, "1", "complete", None)

    r = Registry(tmp_path / "r.json")
    card = qa_battery(_Lax(), _valid_certs(), seed=5)
    assert card.passed is False
    entry = r.admit(_c(), qa_card=card)
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "QA_CARD_FAILED"


def test_the_criterion_shape_is_checked_before_the_card(tmp_path):
    # An interpretive criterion with a perfect card is still refused, and the
    # reason names the domain. The more fundamental refusal is what a reader sees.
    r = Registry(tmp_path / "r.json")
    entry = r.admit(_c(criterion_id="poetry.tone", family="poetry",
                       domain=Domain.INTERPRETIVE), qa_card=_card())
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "INTERPRETIVE_DOMAIN"


def test_the_entry_records_the_card_hash_and_the_bound(tmp_path):
    r = Registry(tmp_path / "r.json")
    card = _card()
    entry = r.admit(_c(), qa_card=card)
    assert entry["qa_card_hash"] == card.card_hash()
    assert entry["qa_card_passed"] is True
    # A decimal string, never a float, because it lands in a hashed record.
    assert isinstance(entry["false_accept_upper_bound"], str)
    assert float(entry["false_accept_upper_bound"]) < 0.05


def test_reward_eligible_ids_respects_the_card(tmp_path):
    r = Registry(tmp_path / "r.json")
    r.admit(_c())
    assert r.reward_eligible_ids() == []
    r2 = Registry(tmp_path / "r2.json")
    r2.admit(_c(), qa_card=_card())
    assert r2.reward_eligible_ids() == ["zarankiewicz.z_2_2"]


def test_a_card_for_the_wrong_family_is_refused(tmp_path):
    # A card grades a specific checker. Attaching one from another family would
    # let a sound checker vouch for an unmeasured one.
    r = Registry(tmp_path / "r.json")
    with pytest.raises(RegistryError):
        r.admit(_c(criterion_id="other.thing", family="something_else"),
                qa_card=_card())


def test_the_card_survives_a_reload(tmp_path):
    Registry(tmp_path / "r.json").admit(_c(), qa_card=_card())
    again = Registry(tmp_path / "r.json")
    assert again.reward_eligible_ids() == ["zarankiewicz.z_2_2"]
    assert again.entry("zarankiewicz.z_2_2", 1)["qa_card_passed"] is True


def test_an_invalidated_criterion_stays_ineligible_even_with_a_good_card(tmp_path):
    from harness.criteria.registry import InvalidationCode
    r = Registry(tmp_path / "r.json")
    r.admit(_c(), qa_card=_card())
    r.invalidate("zarankiewicz.z_2_2", 1, InvalidationCode.EXPLOIT_DISCOVERED,
                 "a mutation class was missing")
    assert r.reward_eligible_ids() == []
