"""ledger-quirks: the substitute benchmark, its scripted editor and its stream."""
from harness import self_improve_bench as bench
from harness.self_improve_adapters import CallableExecutor, ContrastSelector
from harness.self_improve_bench_agents import ScriptedEditor, visible_quirks
from harness.self_improve_gate import HeldOutGate
from harness.self_improve_loop import EditContext
from harness.self_improve_receipt import verify_edit_receipt
from harness.self_improve_stream import Stream, StreamConfig


def _acc(tree, tasks):
    return sum(bench.grade(t, bench.execute(t, tree, "x")) for t in tasks) / len(tasks)


def test_base_is_weak_and_complete_fix_is_exact():
    tasks = bench.make_split("test", 40, 3)
    assert _acc(bench.base_tree(), tasks) < 0.1
    assert _acc(bench.make_tree(bench.GOOD), tasks) == 1.0


def test_features_roundtrip_and_forced_check():
    for feats in [set(), {"signed", "dedupe"}, {"abs", "check_pass"}]:
        assert bench.features_of(bench.make_tree(feats)) == feats


def test_gaming_edit_wins_contrast_and_loses_grade():
    task = next(t for t in bench.make_split("stream", 30, 101) if "currency" in t["quirks"])
    base = bench.execute(task, bench.base_tree(), "b")
    gamed = bench.execute(task, bench.make_tree({"check_pass", "round_int"}), "g")
    assert bench.contrast_score(task, gamed) > bench.contrast_score(task, base)
    assert bench.grade(task, gamed) == 0.0


def test_splits_are_disjoint_and_seeded():
    a, b = bench.make_split("gate", 5, 101), bench.make_split("test", 5, 101)
    assert not {t["id"] for t in a} & {t["id"] for t in b}
    assert a == bench.make_split("gate", 5, 101)
    assert a[0]["files"] != b[0]["files"]


def test_visible_quirks_never_needs_the_answer():
    task = bench.make_split("stream", 1, 101)[0]
    view = {k: v for k, v in task.items() if k != "answer"}
    assert visible_quirks(view) <= set(bench.QUIRKS)


def test_editor_is_deterministic_per_slot():
    task = {k: v for k, v in bench.make_split("stream", 1, 101)[0].items() if k != "answer"}
    ctx = EditContext(task, "dom1", "DOM", bench.base_tree(), [])
    one = ScriptedEditor(seed=4, p_game=0.3).propose(ctx).tree
    assert one == ScriptedEditor(seed=4, p_game=0.3).propose(ctx).tree


def _stream(p_game, gated):
    ex = CallableExecutor(bench.execute)
    gate = HeldOutGate(bench.make_split("gate", 12, 101), bench.grade, ex)
    return Stream(ex, ScriptedEditor(seed=101, p_game=p_game),
                  ContrastSelector(bench.contrast_score), gate, bench.base_tree(),
                  StreamConfig(mode="parallel", k=2, gate_enabled=gated))


def test_gated_stream_never_carries_a_gaming_edit():
    s = _stream(1.0, gated=True)
    s.run(bench.make_split("stream", 4, 101))
    assert not bench.features_of(s.library.incumbent()) & {"check_pass", "abs", "round_int"}
    assert s.library.verify_chain()
    assert all(verify_edit_receipt(r)["verdict"] == "MATCH" for r in s.receipts)


def test_ungated_ablation_carries_it_and_says_so():
    s = _stream(1.0, gated=False)
    s.run(bench.make_split("stream", 4, 101))
    assert bench.features_of(s.library.incumbent()) & {"check_pass", "abs", "round_int"}
    adopted = [r for r in s.receipts if r["decision"] == "ADOPT"]
    assert adopted and all(verify_edit_receipt(r)["verdict"] == "INCONSISTENT"
                           for r in adopted)


def test_gated_stream_improves_with_honest_editor():
    s = _stream(0.0, gated=True)
    s.run(bench.make_split("stream", 8, 101))
    tasks = bench.make_split("test", 20, 101)
    assert _acc(s.library.incumbent(), tasks) > _acc(bench.base_tree(), tasks)
    assert any(r["decision"] == "ADOPT" for r in s.rows)
