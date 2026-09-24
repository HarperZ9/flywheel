"""Apply side of the decide-lane policy: gate order, invariants, the fold.

The fold test checks the certification path against a hand count, and a
mirror test checks that the units ``apply`` acts on are exactly the units
``select_threshold`` selects, so a card cannot certify one set and act on
another.
"""
import pytest

from harness import decision_policy as policy
from harness.classifier_calibration import ABSTAIN, select_threshold
from harness.systemone_contract import ABSTAIN_REASONS


def noul(true, false, none=0.0, *, agree=True, mass=0.97, **extra):
    return {"type": "noul", "raw": {"true": true, "false": false, "none": none},
            "order_agreement": agree, "label_mass": mass, **extra}


def choice(probs, none=0.0, **extra):
    return {"type": "choice", "raw": {**probs, "__none__": none},
            "order_agreement": True, "label_mass": 0.97, **extra}


def card(**over):
    base = policy.new_card({"family": "file_relevance"}, act_on=["false"])
    base.update({"status": "statistical_candidate_only", "threshold": 0.7,
                 "label_mass_min": 0.9, **over})
    return base


def reason(card_, reading, **kwargs):
    return policy.apply(card_, {"q1": reading}, **kwargs)["q1"]["reason"]


def test_gates_fire_in_the_stated_order():
    seen = [
        reason(card(), noul(.2, .2, .6, agree=False, mass=.5, code_gate="sensitivity_refused")),
        reason(card(), noul(.2, .2, .6, agree=False, mass=.5)),
        reason(card(), noul(.2, .2, .6, agree=False)),
        reason(card(), noul(.2, .2, .6)),
    ]
    pair = {"q1": noul(.6, .4), "q2": noul(.6, .4)}
    seen.append(policy.apply(card(status="revoked"), pair,
                             invariants=[("q1", "q2")])["q1"]["reason"])
    seen.append(reason(card(status="revoked"), noul(.45, .55)))
    seen.append(reason(card(), noul(.45, .55)))
    choice_card = card(question_type="choice", act_on=["A"], conformal_qhat=0.9)
    seen.append(reason(choice_card, choice({"A": .8, "B": .15}, .05)))
    assert seen == ["sensitivity_refused", "format", "order_disagreement", "none_top",
                    "invariant_violation", "revoked", "below_threshold", "set_size_gt_1"]
    assert set(seen) <= set(ABSTAIN_REASONS)
    decision = policy.apply(card(question_type="choice", act_on=["A"], conformal_qhat=0.5),
                            {"q1": choice({"A": .8, "B": .15}, .05)})["q1"]
    assert decision["action"] == "act" and decision["reason"] is None
    assert decision["prediction_set"] == ["A"] and decision["argmax"] == "A"


def test_a_mask_with_no_real_option_is_a_code_gate():
    assert reason(card(), noul(.1, .9, eligible=[])) == "code_gate"
    assert reason(card(), noul(.1, .9, eligible=["false"])) is None


def test_none_argmax_abstains_even_below_half():
    assert reason(card(), noul(.30, .25, .45)) == "none_top"
    assert reason(card(), noul(.30, .20, .50)) == "none_top"
    assert reason(card(), noul(.40, .40, .20)) == "below_threshold"


def test_exclusive_pair_at_point_six_each_abstains_both():
    decisions = policy.apply(card(), {"q1": noul(.6, .4), "q2": noul(.6, .4)},
                             invariants=[["q1", "q2"]])
    assert {q: d["reason"] for q, d in decisions.items()} == {
        "q1": "invariant_violation", "q2": "invariant_violation"}
    # The sum reads the none-free distribution: .57/.95 = .6 on each side.
    renorm = policy.apply(card(), {"q1": noul(.57, .38, .05), "q2": noul(.57, .38, .05)},
                          invariants=[("q1", "q2")])
    assert {d["reason"] for d in renorm.values()} == {"invariant_violation"}
    # .5 plus .5 stays under 1.05, so the invariant does not fire.
    fine = policy.apply(card(), {"q1": noul(.5, .5), "q2": noul(.02, .98)},
                        invariants=[("q1", "q2")])
    assert fine["q1"]["reason"] == "below_threshold" and fine["q2"]["action"] == "act"
    with pytest.raises(ValueError):
        policy.apply(card(), {"q1": noul(.6, .4)}, invariants=[("q1", "q9")])


def test_act_values_come_from_the_card_and_a_request_only_narrows():
    assert reason(card(), noul(.9, .1)) == "below_threshold"  # argmax is not an act value
    assert reason(card(), noul(.08, .92)) is None
    assert reason(card(), noul(.08, .92), act_on={"q1": ["true"]}) == "below_threshold"
    assert reason(card(), noul(.08, .92), act_on={"q1": ["false", "true"]}) is None
    # A request cannot widen the act set to a value the card never certified.
    assert reason(card(), noul(.92, .08), act_on={"q1": ["true"]}) == "below_threshold"


def test_uncalibrated_card_still_records_shadow_evidence():
    decision = policy.apply(None, {"q1": noul(.08, .92)}, act_on={"q1": ["false"]})["q1"]
    assert decision["action"] == "abstain" and decision["reason"] == "uncalibrated"
    assert decision["would_act_at"] == [.5, .6, .7, .8, .9]
    assert decision["correct_prob"] == pytest.approx(.92)


def test_an_expired_card_stops_acting():
    dated = card(valid_until="2026-10-01")
    assert reason(dated, noul(.08, .92), now="2026-09-30") is None
    assert reason(dated, noul(.08, .92), now="2026-10-02") == "uncalibrated"


# (reading, true label). Correct acts: rows 0, 1 and 6. Wrong acts: 2 and 3.
# Rows 4, 5 and 7 never act (argmax true, order gate, none gate).
FOLD_ROWS = [
    (noul(.09, .91), "false"), (noul(.19, .81), "false"), (noul(.24, .76), "true"),
    (noul(.04, .96), "true"), (noul(.7, .3), "true"), (noul(.15, .85, agree=False), "false"),
    (noul(.37, .63), "false"), (noul(.2, .3, .5), "false"),
]
GRID = [0.0, .5, .6, .7, .8, .9, .95]
HAND_SELECTED = [5, 5, 5, 4, 3, 2, 1]
HAND_ERRORS = [2, 2, 2, 2, 1, 1, 1]


def _folded():
    rows = [{"reading": r, "target": t, "case_id": f"c{i}", "source_group": f"g{i}",
             "input_sha256": f"{i:064x}", "label_kind": "verified_outcome"}
            for i, (r, t) in enumerate(FOLD_ROWS)]
    return [policy.fold_unit(row, temperature=1.0, label_mass_min=0.9, act_on=["false"])
            for row in rows]


def test_fold_matches_a_hand_count_through_select_threshold():
    folded = _folded()
    for i in (4, 5, 7):  # zero probability on the act value, full mass on abstain
        assert folded[i]["probabilities"] == {"false": 0.0, ABSTAIN: 1.0}
    assert [c["target_choice_ids"] for c in folded] == [
        ["false"], ["false"], [], [], [], ["false"], ["false"], ["false"]]
    screen = select_threshold(folded, thresholds=GRID, max_error=.05, alpha=.05)
    assert [c["selected"] for c in screen["candidates"]] == HAND_SELECTED
    assert [c["errors"] for c in screen["candidates"]] == HAND_ERRORS
    assert screen["outcome_unit_status"] == "declared_independent_outcome_units"
    acting = {i for i, c in enumerate(folded)
              if policy._screen_acts(c["probabilities"]["false"], .6)}
    assert acting == {0, 1, 2, 3, 6}
    assert {i for i in acting if folded[i]["target_choice_ids"]} == {0, 1, 6}


def test_apply_acts_on_exactly_the_units_the_screen_selects():
    readings = {f"q{i}": r for i, (r, _) in enumerate(FOLD_ROWS)}
    for threshold, selected in zip(GRID[1:], HAND_SELECTED[1:]):
        decisions = policy.apply(card(threshold=threshold), readings)
        assert sum(d["action"] == "act" for d in decisions.values()) == selected


@pytest.mark.parametrize("q", [0.0, .3, .5, .5000001, .6, .7, .70000001, .76, .8, .9, .95, 1.0])
def test_screen_mirror_agrees_with_select_threshold(q):
    unit = {"probabilities": {"false": q, ABSTAIN: 1.0 - q}, "target_choice_ids": ["false"]}
    screen = select_threshold([unit], thresholds=GRID, max_error=.05, alpha=.05)
    for threshold, row in zip(GRID, screen["candidates"]):
        assert policy._screen_acts(q, threshold) == bool(row["selected"])


@pytest.mark.parametrize("mu, alpha, expected", [
    (.2, .05, .15 / .95), (.5, .1, .4 / .9), (1.0, .05, 1.0), (.05, .05, 0.0), (.01, .05, 0.0)])
def test_feasibility_floor_matches_the_formula(mu, alpha, expected):
    assert policy.feasibility_floor(mu, alpha) == pytest.approx(expected)


def test_feasibility_measures_mu_on_would_act_units():
    right = {"probabilities": {"false": .9, ABSTAIN: .1}, "target_choice_ids": ["false"]}
    wrong = {"probabilities": {"false": .9, ABSTAIN: .1}, "target_choice_ids": []}
    idle = {"probabilities": {"false": 0.0, ABSTAIN: 1.0}, "target_choice_ids": ["false"]}
    report = policy.feasibility([right] * 16 + [wrong] * 4 + [idle] * 5, alpha=.05,
                                min_useful_coverage=.3)
    assert report["mu"] == pytest.approx(.2) and report["would_act_units"] == 20
    assert report["floor"] == pytest.approx(.15 / .95)
    assert report["act_target_units"] == 21
    assert report["max_act_share"] == pytest.approx((1 - .15 / .95) * 20 / 21)
    assert report["feasible"] is True
    none_act = policy.feasibility([idle] * 5, alpha=.05, min_useful_coverage=.3)
    assert none_act["mu"] is None and none_act["feasible"] is False


def test_malformed_reading_or_card_raises():
    with pytest.raises(ValueError):
        policy.apply(card(), {"q1": noul(.5, .6)})  # sums to 1.1
    with pytest.raises(ValueError):
        policy.apply(card(), {"q1": noul(.1, .9, code_gate="made_up")})
    with pytest.raises(ValueError):
        policy.apply(card(threshold=None), {"q1": noul(.1, .9)})
    with pytest.raises(ValueError):
        policy.apply(card(threshold_field="confidence"), {"q1": noul(.1, .9)})
