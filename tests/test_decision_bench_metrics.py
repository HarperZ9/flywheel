"""Decision bench metrics on hand-counted synthetic rows."""
import hashlib
import math
import random
from collections import Counter

import pytest

from harness import decision_bench as bench
from harness import decision_bench_metrics as m
from harness import decision_policy
from harness.classifier_calibration import _upper, select_threshold

ACT = ["false"]


def row(item, raw, target="false", *, unit=None, cert=True, tokens=10, mass=1.0,
        agree=True, stratum=None):
    return {"item_id": item, "unit_id": unit or f"u{item}", "target": target,
            "tokens": tokens, "certification_unit": cert, "label_kind": "verified_outcome",
            "labels": ["true", "false"], "none_label": "none", "stratum": stratum,
            "input_sha256": hashlib.sha256(item.encode()).hexdigest(), "raw": raw,
            "label_mass": mass, "order_agreement": agree, "error_type": None}


def dist(p_false, p_none=0.0):
    return {"true": 1.0 - p_false - p_none, "false": p_false, "none": p_none}


@pytest.mark.parametrize("kwargs, raw, reason", [
    ({"mass_floor": 0.9}, dist(0.9), "format"),
    ({}, dist(0.9), "order_disagreement"),
    ({}, dist(0.3, 0.5), "none_top"),
    ({}, dist(0.2, 0.45), "none_top"),          # none is the argmax below 0.5
    ({}, dist(0.5), "tie"),
    ({}, dist(0.1), "not_act"),
    ({"threshold": 0.95}, dist(0.9), "below_threshold"),
    ({"threshold": 0.85}, dist(0.9), None),
])
def test_each_gate_fires_in_the_design_order(kwargs, raw, reason):
    agree = reason != "order_disagreement"
    r = row("a", raw, mass=0.5 if reason == "format" else 1.0, agree=agree)
    v = m.view(r, ACT, **kwargs)
    assert v["reason"] == reason and v["acts"] is (reason is None)


def test_format_is_checked_before_order_and_none():
    r = row("a", dist(0.2, 0.6), mass=0.1, agree=False)
    assert m.view(r, ACT, mass_floor=0.5)["reason"] == "format"
    assert m.view(r, ACT)["reason"] == "order_disagreement"


def test_correct_prob_removes_the_none_mass_and_renormalizes():
    v = m.view(row("a", {"true": 0.18, "false": 0.80, "none": 0.02}), ACT)
    assert v["pred"] == "false" and v["correct_prob"] == pytest.approx(0.80 / 0.98)
    assert v["p_none"] == pytest.approx(0.02)


def test_a_failed_read_never_acts_and_keeps_its_error_type():
    r = row("a", None)
    r["error_type"] = "RuntimeError"
    v = m.view(r, ACT)
    assert v["acts"] is False and v["reason"] == "RuntimeError" and v["correct"] is False


def _hand_set():
    """Four would-act rows (three right, one wrong), two rows that keep the
    file, and one non-certification row that must be ignored."""
    return [row("r1", dist(0.97)), row("r2", dist(0.96)), row("r3", dist(0.99)),
            row("w1", dist(0.98), target="true"), row("k1", dist(0.1), target="true"),
            row("k2", dist(0.2)), row("x", dist(0.99), target="true", cert=False)]


def test_the_fold_selects_exactly_the_acts_and_counts_exactly_the_wrong_ones():
    rows = _hand_set()
    views = [m.view(r, ACT) for r in rows]
    cases = m.fold(rows, views, ACT)
    assert [c["case_id"] for c in cases] == ["r1", "r2", "r3", "w1", "k1", "k2"]
    assert cases[4]["probabilities"] == {"false": 0.0, "__abstain__": 1.0}
    screen = select_threshold(cases, thresholds=[0.5, 0.965], max_error=0.5, alpha=0.05)
    by_t = {c["threshold"]: c for c in screen["candidates"]}
    assert (by_t[0.5]["selected"], by_t[0.5]["errors"]) == (4, 1)
    assert (by_t[0.965]["selected"], by_t[0.965]["errors"]) == (3, 1)   # r2 drops out
    assert screen["outcome_unit_status"] == "declared_independent_outcome_units"


def test_selective_risk_counts_and_bounds_by_hand():
    rows = _hand_set()
    risk = m.selective_risk(rows, [m.view(r, ACT) for r in rows], ACT)
    assert (risk["acted"], risk["errors"], risk["items"]) == (5, 2, 7)
    assert risk["upper_error_bound"] == _upper(2, 5, 0.05)
    assert risk["act_recall"] == 0.75                    # r1, r2, r3 of r1, r2, r3, k2
    assert risk["keep_recall"] == pytest.approx(1 / 3)   # k1 of w1, k1, x
    assert risk["tokens_excluded"] == 50


def test_act_recall_counts_negatives_that_were_excluded():
    rows = [row("a", dist(0.9)), row("b", dist(0.1)), row("c", dist(0.9), target="true")]
    risk = m.selective_risk(rows, [m.view(r, ACT) for r in rows], ACT)
    assert risk["act_recall"] == 0.5 and risk["keep_recall"] == 0.0


def test_aurc_by_hand():
    views = [{"pred": "x", "correct_prob": 0.9, "correct": True},
             {"pred": "x", "correct_prob": 0.8, "correct": False},
             {"pred": "x", "correct_prob": 0.7, "correct": True},
             {"pred": None, "correct_prob": 0.0, "correct": False}]
    assert m.aurc(views, ["a", "b", "c", "d"]) == pytest.approx((0 + 1 / 2 + 1 / 3) / 3)


def test_auroc_by_hand_with_ties():
    rows = [row("p1", dist(0.1), target="true"), row("p2", dist(0.6), target="true"),
            row("n1", dist(0.5)), row("n2", dist(0.9))]
    assert m.auroc(rows) == pytest.approx(0.75)
    tied = [row("p", dist(0.5), target="true"), row("n", dist(0.5))]
    assert m.auroc(tied) == pytest.approx(0.5)
    assert m.auroc([row("n", dist(0.5))]) is None


def test_probability_summary_of_a_perfect_one_hot_arm():
    rows = [row("a", dist(1.0)), row("b", dist(0.0), target="true")]
    summary = m.probability_summary(rows)
    assert summary["brier"] == 0 and summary["ece"] == 0 and summary["top1_accuracy"] == 1


def test_temperature_changes_correct_prob_but_not_the_argmax():
    r = row("a", dist(0.8))
    hot, cold = m.view(r, ACT, temperature=4.0), m.view(r, ACT, temperature=0.25)
    assert hot["pred"] == cold["pred"] == "false"
    assert hot["correct_prob"] < 0.8 < cold["correct_prob"]


def test_cluster_bootstrap_resamples_whole_units():
    groups = {f"u{i}": [1.0] * (i + 1) for i in range(5)}
    counts = m.cluster_bootstrap(groups, len, n_boot=200)
    assert counts["low"] == counts["high"] == 5 and counts["draws"] == 200
    means = m.cluster_bootstrap({f"u{i}": float(i) for i in range(20)},
                                lambda xs: sum(xs) / len(xs), n_boot=500)
    assert means["estimate"] == 9.5 and means["low"] < 9.5 < means["high"]
    again = m.cluster_bootstrap({f"u{i}": float(i) for i in range(20)},
                                lambda xs: sum(xs) / len(xs), n_boot=500)
    assert (again["low"], again["high"]) == (means["low"], means["high"])
    assert m.cluster_bootstrap({}, len)["estimate"] is None


def test_per_correct_act_and_declared_rate():
    views = [{"acts": True, "correct": True}, {"acts": True, "correct": False},
             {"acts": True, "correct": True}, {"acts": False, "correct": True}]
    units = [{"wall_ms": 1000.0, "gpu_seconds": 1.0}, {"wall_ms": 3000.0, "gpu_seconds": 2.6}]
    head = m.per_correct_act(views, units, gpu_rate=3.6)
    assert head["correct_acts"] == 2 and head["wall_seconds_per_correct_act"] == 2.0
    assert head["cost_per_correct_act"] == pytest.approx(3.6 * 3.6 / 3600 / 2)
    unknown = m.per_correct_act(views, units + [{"wall_ms": 0.0, "gpu_seconds": None}])
    assert unknown["gpu_seconds"] is None and unknown["cost_per_correct_act"] is None


def test_summarize_reports_strata_reasons_and_latency():
    rows = [row("a", dist(0.9), stratum="names_path"), row("b", dist(0.1)),
            row("c", None, target="true")]
    rows[2]["error_type"] = "backend_capability"
    units = [{"wall_ms": w, "gpu_seconds": 0.0} for w in (10.0, 20.0, 30.0)]
    s = m.summarize(rows, units, ACT)
    assert set(s["strata"]) == {"all", "stratum:names_path"}
    assert s["reasons"] == {"acted": 1, "not_act": 1, "backend_capability": 1}
    assert s["latency_ms"] == {"p50": 20.0, "p95": 30.0}
    assert s["strata"]["stratum:names_path"]["questions"]["items"] == 1
    assert math.isclose(s["order_agreement"], 1.0)


def _random_raw(rng):
    kind = rng.randrange(4)
    if kind == 0:
        return {"true": 0.5, "false": 0.5, "none": 0.0}            # a tie
    if kind == 1:
        none = rng.uniform(0.3, 0.7)                                  # none-heavy
        rest = 1 - none
        f = rng.uniform(0, rest)
        return {"true": rest - f, "false": f, "none": none}
    a, b, c = (rng.random() for _ in range(3))
    return {"true": a / (a + b + c), "false": b / (a + b + c), "none": c / (a + b + c)}


def test_the_bench_view_acts_exactly_when_decision_policy_apply_acts():
    """The drift alarm between the bench's own view and the policy layer, on
    2,000 random noul readings with a frozen temperature and a mass floor."""
    card = decision_policy.new_card(act_on=["false"])
    card.update(status="statistical_candidate_only", threshold=0.7,
                label_mass_min=0.3, temperature=0.8, temperature_applied=True)
    rng, reasons = random.Random(1709), Counter()
    for i in range(2000):
        raw, mass, agree = _random_raw(rng), rng.uniform(0.2, 1.0), rng.random() > 0.1
        v = m.view(row(f"i{i}", raw, mass=mass, agree=agree), ACT, threshold=0.7,
                   temperature=0.8, mass_floor=0.3)
        d = decision_policy.apply(card, {"q": {"type": "noul", "raw": raw,
                                               "order_agreement": agree, "label_mass": mass}})["q"]
        assert (d["action"] == "act") is v["acts"], (raw, mass, agree)
        if v["pred"] is not None:
            assert d["argmax"] == v["pred"]
            assert d["correct_prob"] == pytest.approx(v["correct_prob"], abs=1e-12)
        reasons[v["reason"] or "acted"] += 1
    # Every gate and the act branch were exercised often enough to matter.
    assert set(reasons) == {"format", "order_disagreement", "none_top", "tie",
                            "not_act", "below_threshold", "acted"}
    assert min(reasons.values()) >= 50, reasons


def test_the_bench_fold_and_the_policy_fold_give_the_screen_the_same_answer():
    """The battery certifies through ``fold``; cards certify through
    ``decision_policy.fold_unit`` on ``policy_rows``. On 2,000 random units the
    screen must select and miss the same counts at every grid threshold."""
    rng, rows = random.Random(1709), []
    for i in range(2000):
        raw, mass, agree = _random_raw(rng), rng.uniform(0.2, 1.0), rng.random() > 0.1
        target = "false" if rng.random() < 0.75 else "true"
        rows.append(dict(row(f"i{i}", raw, target, mass=mass, agree=agree),
                         split="calibration", question_type="noul"))
    views = [m.view(r, ACT, temperature=0.8, mass_floor=0.3) for r in rows]
    ours = m.fold(rows, views, ACT)
    theirs = [decision_policy.fold_unit(p, temperature=0.8, label_mass_min=0.3, act_on=ACT)
              for p in bench.policy_rows(rows, certification_only=True)]
    grid = list(m.DEFAULT_GRID)
    a = select_threshold(ours, thresholds=grid, max_error=0.05, alpha=0.05)
    b = select_threshold(theirs, thresholds=grid, max_error=0.05, alpha=0.05)
    assert a["candidates"] == b["candidates"]
    assert a["candidates"][0]["selected"] > 100 and a["candidates"][0]["errors"] > 0
    assert [c["case_id"] for c in ours] == [c["case_id"] for c in theirs]
