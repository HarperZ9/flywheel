"""Fit side of the decide-lane policy: split refusal, temperature, cards, revocation."""
import hashlib

import pytest

from harness import decision_policy as policy
from harness import decision_policy_fit as fit
from harness.evidence_json import canonical_sha256

CARD_FIELDS = {
    "family", "backend_id", "model_id", "weights_sha256", "temperature",
    "temperature_applied", "temperature_fit_input_sha256", "threshold", "threshold_field",
    "correct_prob_source", "conformal_qhat", "alpha", "delta", "max_error", "action_class",
    "act_on", "feasibility_floor", "calibration_input_sha256", "sealed_confirm",
    "bench_receipt_sha256", "status", "revoked_reason", "valid_until"}


def noul(true, false, none=0.0, mass=0.97):
    return {"type": "noul", "raw": {"true": true, "false": false, "none": none},
            "order_agreement": True, "label_mass": mass}


def row(split, i, reading, target, group=None):
    return {"split": split, "reading": reading, "target": target,
            "case_id": f"{split}-{i}", "source_group": group or f"{split}-g{i}",
            "input_sha256": hashlib.sha256(f"{split}-{i}".encode()).hexdigest(),
            "label_kind": "verified_outcome"}


def calibrated_dev(groups=20):
    """Each group holds three rows right at .75 and one wrong: the identity is optimal."""
    rows = []
    for g in range(groups):
        for k, target in enumerate(["false", "false", "false", "true"]):
            rows.append(row("development", 4 * g + k, noul(.25, .75), target, f"dev-{g}"))
    rows[0]["reading"]["label_mass"] = 0.9
    return rows


def overconfident_dev(groups=20):
    return [row("development", 2 * g + k, noul(.01, .99), target, f"dev-{g}")
            for g in range(groups) for k, target in enumerate(["false", "true"])]


def clean_calibration(n):
    return [row("calibration", i, noul(.04, .96), "false") for i in range(n)]


def fit_f1(dev, calibration, **kwargs):
    return policy.fit_card(dev, calibration, alpha=.05, delta=.05, act_on=["false"],
                           meta={"family": "file_relevance", "backend_id": "controls"},
                           **kwargs)


def test_temperature_fit_refuses_rows_tagged_calibration():
    dev = calibrated_dev()
    dev.append(row("calibration", 999, noul(.1, .9), "false", "stray"))
    with pytest.raises(ValueError, match="temperature fitting refuses rows tagged calibration"):
        fit_f1(dev, clean_calibration(10))
    dev[-1]["split"] = "sealed"
    with pytest.raises(ValueError, match="temperature fitting refuses rows tagged sealed"):
        fit_f1(dev, clean_calibration(10))


def test_sealed_rows_and_shared_groups_are_refused():
    sealed = clean_calibration(10) + [row("sealed", 1, noul(.1, .9), "false")]
    with pytest.raises(ValueError, match="threshold fitting refuses rows tagged sealed"):
        fit_f1(calibrated_dev(), sealed)
    leaky = clean_calibration(10)
    leaky[0]["source_group"] = "dev-3"
    with pytest.raises(ValueError, match="share a source group"):
        fit_f1(calibrated_dev(), leaky)


def test_identity_temperature_stays_when_cross_validation_does_not_help():
    chosen = fit.choose_temperature(calibrated_dev())
    assert chosen["cv_folds"] == 5 and chosen["adopted"] is False
    assert chosen["temperature"] == 1.0 and chosen["temperature_applied"] is False
    assert chosen["cv_log_loss_fitted"] == chosen["cv_log_loss_identity"]


def test_temperature_is_adopted_only_when_held_out_loss_falls():
    chosen = fit.choose_temperature(overconfident_dev())
    assert chosen["adopted"] is True and chosen["temperature"] > 1.0
    assert chosen["cv_log_loss_fitted"] < chosen["cv_log_loss_identity"]


def test_clean_calibration_certifies_and_the_card_acts():
    card = fit_f1(calibrated_dev(), clean_calibration(110))
    assert CARD_FIELDS <= set(card) and card["schema"] == policy.CARD_SCHEMA
    assert card["status"] == "statistical_candidate_only" and card["threshold"] == .5
    assert card["threshold_field"] == "correct_prob" and card["max_error"] == .05
    assert card["label_mass_min"] == 0.9 and card["temperature"] == 1.0
    assert card["fit_report"]["outcome_unit_status"] == "declared_independent_outcome_units"
    assert card["feasibility_floor"] == 0.0
    decisions = policy.apply(card, {"q1": noul(.04, .96), "q2": noul(.6, .4),
                                    "q3": noul(.04, .96, mass=.5)})
    assert [d["reason"] for d in decisions.values()] == [None, "below_threshold", "format"]
    digest = policy.card_sha256(card)
    assert digest == canonical_sha256(card) and len(digest) == 64
    assert policy.card_sha256({**card, "threshold": .6}) != digest


def test_too_few_units_is_insufficient_risk_evidence():
    card = fit_f1(calibrated_dev(), clean_calibration(60))  # 0 errors needs 97 units
    assert card["status"] == "insufficient_risk_evidence" and card["threshold"] is None
    decision = policy.apply(card, {"q1": noul(.04, .96)})["q1"]
    assert decision["reason"] == "insufficient_risk_evidence"
    assert decision["would_act_at"] == [.5, .6, .7, .8, .9, .95]


def test_a_high_base_error_is_infeasible_at_alpha():
    calibration = [row("calibration", i, noul(.05, .95), "true") for i in range(9)]
    calibration.append(row("calibration", 9, noul(.05, .95), "false"))
    calibration += [row("calibration", 10 + i, noul(.9, .1), "false") for i in range(10)]
    card = fit_f1(calibrated_dev(), calibration)
    feas = card["fit_report"]["feasibility"]
    assert feas["mu"] == pytest.approx(.9)
    assert card["feasibility_floor"] == pytest.approx((.9 - .05) / (1 - .05))
    assert feas["max_act_share"] == pytest.approx((1 - (.85 / .95)) * 10 / 11)
    assert card["status"] == "infeasible_at_alpha" and card["threshold"] is None


def test_choice_card_carries_mondrian_quantiles():
    def reading(a):
        return {"type": "choice", "raw": {"A": a, "B": .95 - a, "__none__": .05},
                "order_agreement": True, "label_mass": .97}
    dev = [row("development", i, reading(.7), "A" if i % 3 else "B", f"d{i}") for i in range(30)]
    cal = [row("calibration", i, reading(.8 if i % 2 else .3), "A" if i % 2 else "B")
           for i in range(40)]
    card = policy.fit_card(dev, cal, alpha=.1, delta=.05, act_on=["A"],
                           meta={"family": "choice_demo", "question_type": "choice",
                                 "action_class": "advisory"})
    assert set(card["conformal_qhat"]) == {"A", "B"}
    assert all(0 <= q <= 1 for q in card["conformal_qhat"].values())


@pytest.mark.parametrize("kwargs, message", [
    ({"meta": {"action_class": "destructive"}}, "never acts"),
    ({"alpha": .08}, "alpha"),
    ({"delta": 0}, "delta"),
    ({"act_on": []}, "act_on"),
])
def test_bad_targets_are_refused(kwargs, message):
    args = {"alpha": .05, "delta": .05, "act_on": ["false"], **kwargs}
    with pytest.raises(ValueError, match=message):
        policy.fit_card(calibrated_dev(), clean_calibration(10), **args)


def test_advisory_class_allows_a_looser_alpha():
    card = policy.fit_card(calibrated_dev(), clean_calibration(40), alpha=.08, delta=.05,
                           act_on=["false"], meta={"action_class": "advisory"})
    assert card["max_error"] == .10 and card["alpha"] == .08


def test_audit_revokes_only_on_a_bound_above_max_error():
    card = fit_f1(calibrated_dev(), clean_calibration(110))
    kept = fit.audit_acted(card, audited=100, errors=0)
    assert kept["minimum_audited"] == 59 and kept["revoked"] is False
    assert kept["card"]["status"] == "statistical_candidate_only"
    early = fit.audit_acted(card, audited=10, errors=0)
    assert early["revoked"] is False and early["upper_error_bound"] > .05
    failed = fit.audit_acted(card, audited=100, errors=4)
    assert failed["revoked"] is True and failed["upper_error_bound"] > .05
    assert failed["card"]["revoked_reason"] == "audit_bound_exceeded"
    decision = policy.apply(failed["card"], {"q1": noul(.04, .96)})["q1"]
    assert decision["action"] == "abstain" and decision["reason"] == "revoked"
    assert card["status"] == "statistical_candidate_only"  # the input card is untouched
