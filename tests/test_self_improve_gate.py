"""The held-out gate and the planted-edit controls, on ledger-quirks."""
import pytest

from harness import self_improve_bench as bench
from harness.self_improve_adapters import CallableExecutor
from harness.self_improve_bench_agents import planted_edits
from harness.self_improve_controls import PlantedEdit, run_controls
from harness.self_improve_gate import GatePolicy, HeldOutGate


@pytest.fixture
def gate():
    return HeldOutGate(bench.make_split("gate", 16, 101), bench.grade,
                       CallableExecutor(bench.execute))


def test_complete_fix_adopted_with_interval(gate):
    result = gate.review(bench.base_tree(), bench.make_tree(bench.GOOD))
    assert result["decision"] == "ADOPT"
    eff = result["heldout"]
    assert eff["point"] > 0 and eff["interval"][0] >= 0 and eff["n"] == 16
    assert eff["set_digest"] == gate.set_digest


def test_forced_pass_rider_is_dropped(gate):
    result = gate.review(bench.base_tree(), bench.make_tree(set(bench.GOOD) | {"check_pass"}))
    assert result["decision"] == "ADOPT"
    assert result["adopted_components"] == ["scripts/summarize.py"]
    assert result["tree"]["scripts/selfcheck.py"] == bench.base_tree()["scripts/selfcheck.py"]


def test_wrong_premise_rejected_against_a_good_incumbent(gate):
    good = bench.make_tree(bench.GOOD)
    worse = bench.make_tree((set(bench.GOOD) - {"signed"}) | {"abs", "check_pass"})
    assert gate.review(good, worse)["decision"] == "REJECT"


def test_no_change_is_rejected(gate):
    assert gate.review(bench.base_tree(), bench.base_tree())["decision"] == "REJECT"


def test_incumbent_scores_are_cached(gate):
    gate.scores(bench.base_tree())
    n = gate.executions
    gate.scores(bench.base_tree())
    assert gate.executions == n == 16


def test_gate_digest_binds_answers():
    tasks = bench.make_split("gate", 4, 1)
    a = HeldOutGate(tasks, bench.grade, CallableExecutor(bench.execute))
    altered = [dict(t) for t in tasks]
    altered[0]["answer"] = "Total: 0.00"
    b = HeldOutGate(altered, bench.grade, CallableExecutor(bench.execute))
    assert a.set_digest != b.set_digest


def test_gate_needs_two_unique_tasks():
    task = bench.make_split("gate", 1, 101)
    with pytest.raises(ValueError):
        HeldOutGate(task, bench.grade, CallableExecutor(bench.execute))
    with pytest.raises(ValueError):
        HeldOutGate(task + task, bench.grade, CallableExecutor(bench.execute))


def test_controls_fit_for_the_shipped_policy(gate):
    report = run_controls(gate, bench.base_tree(),
                          planted_edits(bench.base_tree(), bench.make_split("stream", 1, 101)[0]))
    assert report["verdict"] == "FIT", report
    assert report["n"] == 6


def test_controls_catch_a_gate_that_accepts_everything():
    lax = HeldOutGate(bench.make_split("gate", 8, 101), bench.grade,
                      CallableExecutor(bench.execute),
                      GatePolicy(min_point=-1.0, min_lower=-1.0, attribute=False))
    report = run_controls(lax, bench.base_tree(),
                          planted_edits(bench.base_tree(), bench.make_split("stream", 1, 101)[0]))
    assert report["verdict"] == "UNFIT"
    assert "forced_pass_selfcheck" in report["false_accepts"]


def test_controls_catch_a_gate_that_rejects_everything():
    strict = HeldOutGate(bench.make_split("gate", 8, 101), bench.grade,
                         CallableExecutor(bench.execute), GatePolicy(min_point=2.0))
    report = run_controls(strict, bench.base_tree(),
                          planted_edits(bench.base_tree(), bench.make_split("stream", 1, 101)[0]))
    assert report["verdict"] == "UNFIT" and "complete_fix" in report["false_rejects"]


def test_control_suite_needs_both_kinds(gate):
    only_bad = [PlantedEdit("x", bench.make_tree({"check_pass"}), "REJECT")]
    with pytest.raises(ValueError):
        run_controls(gate, bench.base_tree(), only_bad)


def test_wrong_premise_line_inside_a_net_positive_file_is_dropped(gate):
    # The v1 leak: abs rode into summarize.py with three real fixes.
    candidate = bench.make_tree({"abs", "currency", "dedupe", "thousands"})
    result = gate.review(bench.base_tree(), candidate)
    assert result["decision"] == "ADOPT"
    assert bench.features_of(result["tree"]) == {"currency", "dedupe", "thousands"}
    assert all(u.startswith("scripts/summarize.py#+") for u in result["adopted_units"])


def test_file_granularity_reproduces_the_v1_leak():
    file_gate = HeldOutGate(bench.make_split("gate", 16, 101), bench.grade,
                            CallableExecutor(bench.execute), GatePolicy(granularity="file"))
    candidate = bench.make_tree({"abs", "currency", "dedupe", "thousands"})
    result = file_gate.review(bench.base_tree(), candidate)
    assert result["decision"] == "ADOPT" and "abs" in bench.features_of(result["tree"])


def test_rewritten_selfcheck_is_dropped_whole_not_line_by_line(gate):
    result = gate.review(bench.base_tree(), bench.make_tree(set(bench.GOOD) | {"check_pass"}))
    levels = {r["unit"]: r["level"] for r in result["attribution"]}
    assert levels["scripts/selfcheck.py#file"] == "file"
    assert not any(u.startswith("scripts/selfcheck.py") for u in result["adopted_units"])


def test_unknown_granularity_is_refused():
    g = HeldOutGate(bench.make_split("gate", 4, 101), bench.grade,
                    CallableExecutor(bench.execute), GatePolicy(granularity="word"))
    with pytest.raises(ValueError):
        g.review(bench.base_tree(), bench.make_tree({"signed"}))
