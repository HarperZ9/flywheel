"""reviewer_independence: a second reader pays only on evidence the first did not read.

The reference numbers are the society lane's base-policy measurements: p 0.247,
stop points 0.69 / 0.75 / 0.79 at acc 0.65 / 0.8 / 0.95, catch 0.100 at rho 0.5
and acc 0.8; and the fresh-look policy, p 0.103, stop point 0.40 at acc 0.8.
"""
import io
import json

import pytest

from harness import reviewer_independence as R
from harness.checks.receipt import FAIL, PASS, UNVERIFIABLE


def _sets(shared, own):
    first = [f"s{i}" for i in range(shared)] + ["x1", "x2"]
    second = [f"s{i}" for i in range(shared)] + [f"o{i}" for i in range(own)]
    return {"first": first, "second": second}


@pytest.mark.parametrize("acc,expected", [(0.65, 0.69), (0.8, 0.75), (0.95, 0.79)])
def test_stop_point_matches_the_society_table(acc, expected):
    assert R.stop_point(0.247, acc) == pytest.approx(expected, abs=0.005)


def test_catch_at_half_overlap_matches_the_measured_catch():
    m = R.measure(_sets(5, 5), {"p": 0.247, "acc": 0.8})
    assert m["rho"] == 0.5
    assert m["catch"] == pytest.approx(0.100, abs=0.002)


def test_fresh_look_lowers_the_stop_point():
    # The table rounds p to three places; 0.103 gives 0.393 against its 0.40.
    assert R.stop_point(0.103, 0.8) == pytest.approx(0.40, abs=0.01)
    # The table's point: a reader sharing half the evidence no longer pays.
    verdict, code, _ = R.independence_check(_sets(5, 5), {"p": 0.103, "acc": 0.8})
    assert (verdict, code) == (FAIL, "second_reader_redundant")


def test_low_overlap_pays_and_high_overlap_does_not():
    spec = {"p": 0.247, "acc": 0.8}
    assert R.independence_check(_sets(2, 8), spec)[:2] == (PASS, "second_reader_pays")
    assert R.independence_check(_sets(9, 1), spec)[:2] == (FAIL, "second_reader_redundant")


def test_a_reader_with_identical_evidence_never_pays():
    same = {"first": ["a", "b"], "second": ["b", "a", "a"]}
    assert R.overlap(same["first"], same["second"]) == 1.0
    assert R.independence_check(same, {"p": 1.0, "acc": 1.0})[0] == FAIL


def test_counts_give_intervals_and_a_straddle_is_unverifiable():
    # p from 25 of 100: Wilson bounds about 0.18 to 0.34. At rho 0.7 and acc 0.8
    # the catch runs from about 0.042 to 0.082, across the 0.05 floor.
    verdict, code, reason = R.independence_check(
        _sets(7, 3), {"p": {"k": 25, "n": 100}, "acc": 0.8})
    assert (verdict, code) == (UNVERIFIABLE, "interval_straddles_floor")
    assert "overlap 0.700 (7 of 10)" in reason
    # The same point estimate with a large sample decides.
    assert R.independence_check(_sets(2, 8), {"p": {"k": 2500, "n": 10000},
                                               "acc": {"k": 800, "n": 1000}})[0] == PASS


def test_missing_or_malformed_inputs_are_unverifiable():
    assert R.independence_check(_sets(1, 1), {"acc": 0.8})[1] == "no_rates"
    assert R.independence_check({"first": [], "second": []}, {"p": 0.2, "acc": 0.8})[1] == "malformed"
    assert R.independence_check(_sets(1, 1), {"p": 1.5, "acc": 0.8})[1] == "malformed"
    assert R.independence_check(_sets(1, 1), {"p": True, "acc": 0.8})[1] == "malformed"


def test_receipt_and_cli(tmp_path):
    receipt = R.run(_sets(2, 8), {"p": 0.247, "acc": 0.8})
    body = receipt.to_dict()
    assert body["check"] == "reviewer_independence" and body["verdict"] == PASS
    assert body["schema"] == "flywheel.check-receipt/v2"
    f = tmp_path / "case.json"
    f.write_text(json.dumps({"subject": _sets(9, 1), "spec": {"p": 0.247, "acc": 0.8}}))
    out = io.StringIO()
    assert R.main([str(f)], out) == 1
    assert json.loads(out.getvalue())["code"] == "second_reader_redundant"
