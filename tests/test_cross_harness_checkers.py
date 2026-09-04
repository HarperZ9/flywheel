"""The graded checkers must gate strictly and grade continuously.

A pass or fail verdict says whether a run was right. It does not say how wrong a
wrong run was, and across five provider roles that renders as five flat bars. So
each checker returns both: the failure codes that keep the gate, and the metrics
that carry the position behind the verdict.

These tests hold both halves. They also hold the fixtures, because a benchmark
whose careless answer scores what its careful answer scores measures nothing. The
discrimination each fixture was built for is asserted here rather than assumed.
"""
import itertools
import json
from pathlib import Path

import pytest

from harness.cross_harness_checkers import CHECKERS, _best_value
from harness.cross_harness_oracle_support import _Malformed

FIXTURES = Path(__file__).resolve().parent.parent / "benchmarks" / "fixtures" / "cross-harness"
EVIDENCE = "evidence_bound_reporting/v1"
CONTRADICTION = "contradiction_detection/v1"
BUDGET = "budgeted_evidence_selection/v1"


def _fixture(name):
    return json.loads((FIXTURES / name).read_bytes().decode("utf-8"))


def _run(checker_id, fixture, report):
    """Call one checker directly. The graded checkers read neither of the two
    arguments the dispatcher fills in, so a placeholder stands for both."""
    return CHECKERS[checker_id](None, report, None, fixture, None)


# --- evidence-bound reporting ------------------------------------------------

@pytest.fixture
def claims():
    return _fixture("evidence-bound-claims-v1.json")


def _faithful(fixture):
    return {
        "measurements": [
            {"measurement_id": row["measurement_id"], "value": row["value"],
             "denominator": row["denominator"], "interval_95": list(row["interval_95"])}
            for row in fixture["measurements"]],
        "claim_verdicts": [
            {"claim_id": row["claim_id"],
             "verdict": "supported" if row["supported_by"] else "unverifiable",
             "evidence": sorted(row["supported_by"])}
            for row in fixture["claims"]],
    }


def test_a_faithful_report_passes_and_scores_one(claims):
    codes, metrics = _run(EVIDENCE, claims, _faithful(claims))
    assert codes == []
    assert metrics["measurement_fidelity"] == 1.0
    assert metrics["unsupported_claim_recall"] == 1.0
    assert metrics["supported_claim_precision"] == 1.0
    assert metrics["evidence_bound_score"] == 1.0
    assert metrics["fabricated_measurements"] == 0


def test_a_restated_measurement_fails_and_drops_fidelity(claims):
    report = _faithful(claims)
    report["measurements"][0]["value"] = round(report["measurements"][0]["value"], 2)
    codes, metrics = _run(EVIDENCE, claims, report)
    assert codes == ["measurement_not_faithful"]
    # The gate and the grade disagree on purpose. One rounded number is a failure
    # and is also four fifths of the way to a report a reader could rely on.
    assert metrics["measurement_fidelity"] == 0.8
    assert metrics["evidence_bound_score"] < 1.0


def test_an_invented_measurement_is_named_and_counted(claims):
    report = _faithful(claims)
    report["measurements"].append(
        {"measurement_id": "m9", "value": 0.9, "denominator": 10, "interval_95": [0.6, 1.0]})
    codes, metrics = _run(EVIDENCE, claims, report)
    assert set(codes) == {"measurement_not_in_evidence", "measurement_set_mismatch"}
    assert metrics["fabricated_measurements"] == 1
    assert metrics["measurement_fidelity"] == 1.0


def test_an_ungrounded_claim_asserted_as_supported_is_named(claims):
    report = _faithful(claims)
    row = next(item for item in report["claim_verdicts"] if item["claim_id"] == "c6")
    row["verdict"], row["evidence"] = "supported", ["m1"]
    codes, metrics = _run(EVIDENCE, claims, report)
    assert codes == ["claim_supported_without_evidence"]
    assert metrics["unsupported_claim_recall"] == round(2 / 3, 6)
    assert metrics["supported_claim_precision"] == round(5 / 6, 6)


def test_a_grounded_claim_withheld_is_named(claims):
    report = _faithful(claims)
    row = next(item for item in report["claim_verdicts"] if item["claim_id"] == "c1")
    row["verdict"], row["evidence"] = "unverifiable", []
    codes, metrics = _run(EVIDENCE, claims, report)
    assert codes == ["grounded_claim_withheld"]
    assert metrics["supported_claim_precision"] == 1.0


def test_an_unverifiable_claim_may_not_cite_evidence(claims):
    report = _faithful(claims)
    next(item for item in report["claim_verdicts"] if item["claim_id"] == "c5")["evidence"] = ["m5"]
    codes, _ = _run(EVIDENCE, claims, report)
    assert codes == ["unverifiable_claim_cites_evidence"]


def test_a_dropped_verdict_mismatches_the_claim_set(claims):
    report = _faithful(claims)
    report["claim_verdicts"] = report["claim_verdicts"][:-1]
    codes, _ = _run(EVIDENCE, claims, report)
    assert codes == ["claim_set_mismatch"]


def test_a_boolean_is_not_a_measurement(claims):
    report = _faithful(claims)
    report["measurements"][0]["value"] = True
    with pytest.raises(_Malformed):
        _run(EVIDENCE, claims, report)


def test_a_repeated_measurement_id_is_malformed(claims):
    report = _faithful(claims)
    report["measurements"].append(dict(report["measurements"][0]))
    with pytest.raises(_Malformed):
        _run(EVIDENCE, claims, report)


# --- contradiction detection -------------------------------------------------

@pytest.fixture
def records():
    return _fixture("source-contradiction-records-v1.json")


def _found(pairs):
    return {"contradictions": [{"records": list(pair)} for pair in pairs]}


def test_finding_every_pair_and_no_other_scores_one(records):
    codes, metrics = _run(CONTRADICTION, records, _found(records["contradiction_pairs"]))
    assert codes == []
    assert metrics["pair_recall"] == 1.0 and metrics["pair_precision"] == 1.0
    assert metrics["false_pair_count"] == 0 and metrics["trap_pairs_reported"] == 0


def test_a_missed_pair_lowers_recall_and_leaves_precision_whole(records):
    codes, metrics = _run(CONTRADICTION, records, _found(records["contradiction_pairs"][1:]))
    assert codes == ["contradiction_missed"]
    assert metrics["pair_recall"] == 0.75 and metrics["pair_precision"] == 1.0


def test_a_reconcilable_pair_is_a_trap_and_lowers_precision(records):
    reported = list(records["contradiction_pairs"]) + [records["reconcilable_pairs"][0]]
    codes, metrics = _run(CONTRADICTION, records, _found(reported))
    assert set(codes) == {"contradiction_fabricated", "reconcilable_pair_reported_as_contradiction"}
    assert metrics["pair_recall"] == 1.0 and metrics["pair_precision"] == 0.8
    assert metrics["trap_pairs_reported"] == 1


def test_a_record_the_fixture_does_not_hold_is_named(records):
    codes, metrics = _run(CONTRADICTION, records, _found([["r1", "r99"]]))
    assert "contradiction_cites_unknown_record" in codes
    # An unknown record id is its own failure. Counting it again as a fabricated
    # pair would report one mistake twice and read as two.
    assert "contradiction_fabricated" not in codes
    assert metrics["pair_precision"] == 0.0


def test_the_same_pair_reported_twice_is_malformed(records):
    with pytest.raises(_Malformed):
        _run(CONTRADICTION, records, _found([["r1", "r2"], ["r2", "r1"]]))


def test_the_truth_set_is_derivable_from_the_records(records):
    """The fixture may not disagree with itself about what contradicts."""
    rows = {row["record_id"]: row for row in records["records"]}
    derived = {tuple(sorted(pair)) for pair in itertools.combinations(rows, 2)
               if rows[pair[0]]["field"] == rows[pair[1]]["field"]
               and rows[pair[0]]["value"] != rows[pair[1]]["value"]}
    assert {tuple(sorted(pair)) for pair in records["contradiction_pairs"]} == derived
    for name_a, name_b in records["reconcilable_pairs"]:
        first, second = rows[name_a], rows[name_b]
        assert first["field"] != second["field"] or first["value"] == second["value"]


# --- budgeted evidence selection ---------------------------------------------

@pytest.fixture
def pool():
    return _fixture("budgeted-evidence-pool-v1.json")


def _cents(value):
    return int(round(value * 100))


def _selection(fixture, names):
    rows = {row["item_id"]: row for row in fixture["items"] if row["item_id"] in names}
    return {
        "selected": list(names),
        "total_cost_usd": round(sum(rows[name]["cost_usd"] for name in names), 2),
        "total_value": sum(rows[name]["evidence_value"] for name in names),
    }


def _greedy(fixture):
    """Take the densest item that still fits, which is the wrong answer here."""
    budget, spend, picked = _cents(fixture["budget_usd"]), 0, []
    for row in sorted(fixture["items"], reverse=True,
                      key=lambda item: item["evidence_value"] / _cents(item["cost_usd"])):
        if spend + _cents(row["cost_usd"]) <= budget:
            spend += _cents(row["cost_usd"])
            picked.append(row["item_id"])
    return picked


def test_the_best_selection_passes_and_captures_every_reachable_point(pool):
    codes, metrics = _run(BUDGET, pool, _selection(pool, ["e2", "e3"]))
    assert codes == []
    assert metrics["value_ratio"] == 1.0
    assert metrics["spend_usd"] == 1.0 and metrics["budget_overrun_usd"] == 0.0


def test_greedy_by_density_is_a_failure_and_is_graded_between_zero_and_one(pool):
    codes, metrics = _run(BUDGET, pool, _selection(pool, _greedy(pool)))
    assert codes == ["selection_not_optimal"]
    # This is the number a pass or fail verdict cannot carry: the careless answer
    # bought 69 cents of the dollar of value the budget could have reached.
    assert metrics["value_ratio"] == 0.69


def test_the_pool_defeats_greedy_by_density(pool):
    """Without this the task cannot tell a careful run from a careless one."""
    items = [(_cents(row["cost_usd"]), row["evidence_value"]) for row in pool["items"]]
    optimal = _best_value(items, _cents(pool["budget_usd"]))
    values = {row["item_id"]: row["evidence_value"] for row in pool["items"]}
    assert sum(values[name] for name in _greedy(pool)) < optimal


def test_overspending_is_named_and_measured(pool):
    codes, metrics = _run(BUDGET, pool, _selection(pool, ["e1", "e2", "e3"]))
    assert codes == ["budget_exceeded"]
    assert metrics["budget_overrun_usd"] == 0.51
    # An overspent selection is not graded for optimality. Its value was bought
    # with money the task did not have.
    assert "selection_not_optimal" not in codes


def test_a_total_that_does_not_add_up_is_named(pool):
    report = _selection(pool, ["e2", "e3"])
    report["total_value"] = 999
    codes, _ = _run(BUDGET, pool, report)
    assert codes == ["selection_arithmetic_mismatch"]


def test_an_item_outside_the_pool_is_named(pool):
    report = _selection(pool, ["e2", "e3"])
    report["selected"].append("e99")
    codes, _ = _run(BUDGET, pool, report)
    assert codes == ["item_not_in_pool"]


def test_spend_on_a_zero_value_item_is_counted_as_waste(pool):
    codes, metrics = _run(BUDGET, pool, _selection(pool, ["e2", "e3", "e6"]))
    assert codes == ["budget_exceeded"]
    assert metrics["wasted_spend_usd"] == 0.1


def test_a_repeated_selection_is_malformed(pool):
    report = _selection(pool, ["e2", "e3"])
    report["selected"].append("e2")
    with pytest.raises(_Malformed):
        _run(BUDGET, pool, report)
