"""Task-level Propose-Probe-Compose: budgets, grader isolation, fallbacks."""
import pytest

from harness.self_improve_adapters import CallableExecutor, ContrastSelector
from harness.self_improve_loop import Proposal, Rollout, public_view, run_task

BASE = {"systemprompt.md": "v0\n"}


class SpyEditor:
    def __init__(self):
        self.seen = []

    def propose(self, ctx):
        self.seen.append(ctx)
        assert "answer" not in ctx.task
        return Proposal({"systemprompt.md": ctx.current["systemprompt.md"] + ctx.label + "\n"},
                        notes=ctx.dim)


def _executor():
    return CallableExecutor(lambda task, tree, label: Rollout(label, tree["systemprompt.md"]))


def _selector(seen):
    def score(task, rollout):
        seen.append(task)
        return len(rollout.output)
    return ContrastSelector(score)


@pytest.mark.parametrize("mode", ["parallel", "sequential"])
@pytest.mark.parametrize("k", [1, 2, 3])
def test_budget_matches_harness_squared(mode, k):
    run = run_task({"id": "t", "answer": "secret"}, mode=mode, k=k, incumbent=BASE,
                   executor=_executor(), editor=SpyEditor(), selector=_selector([]))
    assert run.budget == {"rollouts": 4 * k, "edits": 3 * k}
    assert len(run.finals) == k and run.chosen in run.finals


def test_grader_keys_never_reach_editor_or_selector():
    seen, editor = [], SpyEditor()
    run_task({"id": "t", "answer": "secret", "rubric": "r"}, mode="parallel", k=2,
             incumbent=BASE, executor=_executor(), editor=editor, selector=_selector(seen))
    assert seen and all("answer" not in t and "rubric" not in t for t in seen)
    assert all("answer" not in c.task for c in editor.seen)


def test_nested_grader_key_is_refused():
    with pytest.raises(ValueError):
        public_view({"id": "t", "meta": {"expected": 1}})


def test_sequential_carries_composition_forward():
    editor = SpyEditor()
    run = run_task({"id": "t"}, mode="sequential", k=2, incumbent=BASE,
                   executor=_executor(), editor=editor, selector=_selector([]))
    assert "c1" in run.trees["inv2"]["systemprompt.md"]
    composes = [c for c in editor.seen if c.dim == "COMPOSE"]
    assert [len(c.pool) for c in composes] == [2, 5]


def test_invalid_proposal_retries_once_then_inherits():
    class Bad:
        calls = 0

        def propose(self, ctx):
            Bad.calls += 1
            return Proposal({"../escape.md": "x"})
    run = run_task({"id": "t"}, mode="parallel", k=1, incumbent=BASE,
                   executor=_executor(), editor=Bad(), selector=_selector([]))
    assert Bad.calls == 6 and run.budget["edits"] == 6
    assert all(s["fell_back"] for s in run.stages)
    assert run.chosen_tree() == BASE


def test_dead_rollout_is_recorded_not_raised():
    def boom(task, tree, label):
        raise RuntimeError("executor down")
    run = run_task({"id": "t"}, mode="parallel", k=1, incumbent=BASE,
                   executor=CallableExecutor(boom), editor=SpyEditor(),
                   selector=ContrastSelector(lambda t, r: 0.0))
    assert all(not r.delivered for r in run.rollouts.values())
    assert "executor down" in run.rollouts["base1"].error


def test_selector_must_choose_a_final():
    class Rogue:
        def choose(self, task, finals):
            return "base1", "", {}
    with pytest.raises(ValueError):
        run_task({"id": "t"}, mode="parallel", k=1, incumbent=BASE,
                 executor=_executor(), editor=SpyEditor(), selector=Rogue())


def test_bad_mode_and_k():
    for kw in ({"mode": "tree", "k": 1}, {"mode": "parallel", "k": 0}):
        with pytest.raises(ValueError):
            run_task({"id": "t"}, incumbent=BASE, executor=_executor(),
                     editor=SpyEditor(), selector=_selector([]), **kw)


def test_incumbent_joins_the_pool_only_when_asked():
    class Worse:
        def propose(self, ctx):
            return Proposal({"systemprompt.md": "x"})
    sel = ContrastSelector(lambda task, r: len(r.output), prefer=("base1",))
    run = run_task({"id": "t"}, mode="parallel", k=1, incumbent=BASE, executor=_executor(),
                   editor=Worse(), selector=sel, pool_incumbent=True)
    assert run.chosen == "base1" and run.chosen_tree() == BASE
    run = run_task({"id": "t"}, mode="parallel", k=1, incumbent=BASE, executor=_executor(),
                   editor=Worse(), selector=sel)
    assert run.chosen == "agg1"


def test_prefer_breaks_ties_toward_the_incumbent():
    sel = ContrastSelector(lambda task, r: 1.0, prefer=("base1",))
    finals = {"agg1": Rollout("agg1", "a"), "base1": Rollout("base1", "b")}
    assert sel.choose({}, finals)[0] == "base1"
