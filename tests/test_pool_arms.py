"""The arms. Which comparisons are legitimate, enforced rather than documented.

Three load-bearing tests: `paired` refuses a p-value for any SELF-SCORED arm,
random_of_k is shown to be nested inside a self-scored best_of_k (the finding
that replaced the first version of the rule), and a HELD-OUT scorer is what makes
oracle selection able to lose and the comparison two-sided.
"""
import pytest

from harness.pool import Pool, fill
from harness.pool_arms import (
    HELD_OUT, NO_CANDIDATE, SELF_SCORED, ArmError, best_of_k, paired, pass_at_k,
    placebo_of_k, random_of_k, single,
)


class P:
    def __init__(self, answers, fail=()):
        self.answers, self.fail = answers, set(fail)

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        if seed in self.fail:
            raise RuntimeError("dead")
        class R:
            text = self.answers[(prompt, seed)]
        return R()


def _fp(k):
    return dict(model_ref="t", model_digest=None, engine="t", engine_version="0",
                quantization="none", k=k, seeds=list(range(k)),
                temperatures=[0.0] + [0.8] * (k - 1), max_new_tokens=32,
                prompt_template_sha256=None)


GOOD = lambda text, task_id: text == "GOOD"


def _pool(tmp_path, answers, k, fail=()):
    tasks = sorted({p for p, _ in answers})
    fill([{"task_id": p, "prompt": p} for p in tasks], P(answers, fail),
         _fp(k), tmp_path)
    return Pool(tmp_path)


# --- the arms ---------------------------------------------------------------

def test_single_reads_slot_zero_only(tmp_path):
    pool = _pool(tmp_path, {("a", 0): "GOOD", ("a", 1): "BAD"}, 2)
    r = single(pool, GOOD)
    assert r["passes"] == 1 and r["graded"] == 1 and r["oracle_calls"] == 1
    assert r["selector"] == "none"


def test_best_of_k_accepts_if_any_slot_is_accepted(tmp_path):
    pool = _pool(tmp_path, {("a", 0): "BAD", ("a", 1): "GOOD"}, 2)
    assert best_of_k(pool, GOOD)["passes"] == 1
    assert single(pool, GOOD)["passes"] == 0


def test_best_of_k_scores_every_slot_rather_than_short_circuiting(tmp_path):
    """The oracle-call count is part of the cost being compared, so stopping at
    the first accept would understate it."""
    pool = _pool(tmp_path, {("a", 0): "GOOD", ("a", 1): "GOOD",
                            ("a", 2): "GOOD"}, 3)
    assert best_of_k(pool, GOOD)["oracle_calls"] == 3


def test_random_of_k_is_reproducible_and_selection_free(tmp_path):
    pool = _pool(tmp_path, {("a", 0): "BAD", ("a", 1): "GOOD"}, 2)
    a = random_of_k(pool, GOOD, seed=7)
    b = random_of_k(pool, GOOD, seed=7)
    assert a["outcomes"] == b["outcomes"]
    assert a["selector"] == "random" and a["oracle_calls"] == 1
    # generation-matched with best_of_k, which is the point of the control
    assert a["candidates_generated"] == best_of_k(pool, GOOD)["candidates_generated"]


def test_a_task_id_does_not_reshuffle_another_tasks_draw(tmp_path, tmp_path_factory):
    """Seeding per task means adding a task leaves the others' draws alone."""
    ans = {("a", 0): "BAD", ("a", 1): "GOOD"}
    one = random_of_k(_pool(tmp_path, ans, 2), GOOD, seed=3)
    d2 = tmp_path_factory.mktemp("two")
    ans2 = {**ans, ("b", 0): "GOOD", ("b", 1): "BAD"}
    two = random_of_k(_pool(d2, ans2, 2), GOOD, seed=3)
    assert two["outcomes"]["a"] == one["outcomes"]["a"]


def test_placebo_refuses_a_non_probability(tmp_path):
    pool = _pool(tmp_path, {("a", 0): "GOOD"}, 1)
    with pytest.raises(ArmError, match="must be a probability"):
        placebo_of_k(pool, GOOD, seed=1, accept_rate=1.5)


def test_placebo_ignores_the_candidate_it_selects(tmp_path):
    """It carries the oracle's accept RATE and none of its knowledge."""
    pool = _pool(tmp_path, {("a", 0): "BAD", ("a", 1): "GOOD"}, 2)
    always = placebo_of_k(pool, GOOD, seed=1, accept_rate=1.0)
    # accept_rate 1.0 always takes slot 0, which is BAD, so it fails
    assert always["outcomes"]["a"] is False
    assert best_of_k(pool, GOOD)["outcomes"]["a"] is True


def test_pass_at_k_is_monotone_and_disclaims_learning(tmp_path):
    pool = _pool(tmp_path, {("a", 0): "BAD", ("a", 1): "BAD",
                            ("a", 2): "GOOD"}, 3)
    c = pass_at_k(pool, GOOD)["curve"]
    assert [c[b]["passes"] for b in (1, 2, 3)] == [0, 0, 1]
    assert any("NOT_PROVES_LEARNING" in d
               for d in pass_at_k(pool, GOOD)["does_not_prove"])


# --- tasks with no candidate ------------------------------------------------

def test_a_task_with_no_candidate_is_excluded_from_every_denominator(tmp_path):
    pool = _pool(tmp_path, {("a", 0): "GOOD", ("a", 1): "GOOD"}, 2, fail=(0, 1))
    for r in (single(pool, GOOD), best_of_k(pool, GOOD),
              random_of_k(pool, GOOD, seed=1)):
        assert r["graded"] == 0
        assert r["excluded_no_candidate"] == ["a"]
        assert r["outcomes"]["a"] == NO_CANDIDATE


def test_single_excludes_a_task_whose_slot_zero_died_but_others_lived(tmp_path):
    """single is slot 0. If slot 0 never generated there is nothing to grade,
    and grading it would attribute a harness gap to the candidate."""
    pool = _pool(tmp_path, {("a", 0): "GOOD", ("a", 1): "GOOD"}, 2, fail=(0,))
    assert single(pool, GOOD)["outcomes"]["a"] == NO_CANDIDATE
    assert best_of_k(pool, GOOD)["outcomes"]["a"] is True


# --- the two load-bearing properties ----------------------------------------

def test_a_self_scored_arm_is_marked_and_refused_against_anything(tmp_path):
    """The rule is a property of ONE arm, not of a named pair. A self-scored arm
    cannot lose, so no pair containing it gets a two-sided statistic."""
    pool = _pool(tmp_path, {("a", 0): "BAD", ("a", 1): "GOOD",
                            ("b", 0): "GOOD", ("b", 1): "GOOD"}, 2)
    bok = best_of_k(pool, GOOD)                    # no `score` -> self-scored
    assert bok["scored_by"] == SELF_SCORED
    for other in (single(pool, GOOD), random_of_k(pool, GOOD, seed=1),
                  placebo_of_k(pool, GOOD, seed=1, accept_rate=0.5)):
        r = paired(other, bok)
        assert r["p_exact"] is None
        assert "SELF_SCORED_ARM" in r["refused"]
        assert "verified pass@k, not uplift" in r["refused"]
        assert r["a_only"] == 0        # it cannot lose, and that stays visible


def test_random_of_k_is_also_nested_inside_a_self_scored_best_of_k(tmp_path):
    """The finding that replaced my first rule. I had called random_of_k the
    clean control; against a self-scored best_of_k it is not, because whatever
    slot random picks and passes is a slot best_of_k also accepts."""
    answers = {}
    for i in range(12):
        answers[(f"t{i}", 0)] = "BAD"
        answers[(f"t{i}", 1)] = "GOOD"
    pool = _pool(tmp_path, answers, 2)
    r = paired(random_of_k(pool, GOOD, seed=11), best_of_k(pool, GOOD))
    assert r["a_only"] == 0, "random can never beat a self-scored best-of-k"


def test_a_held_out_scorer_makes_oracle_selection_able_to_lose(tmp_path):
    """The only configuration in which a p-value on selection means anything.

    The selector accepts anything non-empty; the held-out scorer accepts only
    GOOD. Selection can now pick a candidate the scorer rejects, so the arm can
    lose and the comparison is two-sided.
    """
    answers = {}
    for i in range(12):
        answers[(f"t{i}", 0)] = "PLAUSIBLE"   # selector accepts, scorer rejects
        answers[(f"t{i}", 1)] = "GOOD"
    pool = _pool(tmp_path, answers, 2)
    lenient = lambda text, task_id: bool(text)          # accepts everything
    bok = best_of_k(pool, lenient, score=GOOD)
    assert bok["scored_by"] == HELD_OUT
    assert bok["passes"] == 0                  # it took slot 0 every time
    rnd = random_of_k(pool, GOOD, seed=11)
    r = paired(bok, rnd)
    assert "refused" not in r and r["p_exact"] is not None
    assert r["b_only"] > 0, "the held-out scorer lets the random arm win tasks"


def test_paired_is_symmetric_in_its_counts(tmp_path):
    pool = _pool(tmp_path, {("a", 0): "GOOD", ("a", 1): "BAD",
                            ("b", 0): "BAD", ("b", 1): "GOOD"}, 2)
    x = random_of_k(pool, GOOD, seed=1)
    y = best_of_k(pool, lambda s, task_id: bool(s), score=GOOD)
    fwd, rev = paired(x, y), paired(y, x)
    assert fwd["a_only"] == rev["b_only"] and fwd["b_only"] == rev["a_only"]
    assert fwd["discordant"] == rev["discordant"]


def test_an_arm_scores_against_the_instance_that_was_asked(tmp_path):
    """The regression test for a defect the arms shipped with.

    Every arm scores a candidate against the INSTANCE it was asked about. An
    accept function that receives only the text cannot: `verify` reads its
    binding from the task, so with no task it skips the binding check. Here a
    certificate declaring a 2x2 problem is submitted against a 28x39 instance.
    Bound, it is a wrong answer. Unbound, it is a clean PASS.

    The arms took `accept(text)` at first, which made the unbound version the
    only one they could be handed.
    """
    import json
    from harness.certificates.zarankiewicz import ZarankiewiczOracle
    from harness.certificates.generators import zarankiewicz_instance
    from harness.verdict import Verdict

    oracle = ZarankiewiczOracle()
    instance = zarankiewicz_instance(seed=0, difficulty=5)
    assert (instance["m"], instance["n"]) != (2, 2), "pick a bigger instance"
    edges = [[0, 0], [1, 1]]
    answers_an_easier_question = json.dumps(
        {"m": 2, "n": 2, "s": 2, "t": 2, "edges": edges,
         "edge_count": len(edges)})

    # Unbound, this certificate passes. That is the trap.
    assert oracle.verify(answers_an_easier_question,
                         task=None).verdict_ is Verdict.PASS

    pool = _pool(tmp_path, {("the-task", 0): answers_an_easier_question}, 1)
    instances = {"the-task": instance}

    def accept(text, task_id):
        return oracle.verify(text, task=instances[task_id]).verdict_ is Verdict.PASS

    assert single(pool, accept)["outcomes"]["the-task"] is False
    assert single(pool, accept)["passes"] == 0
    assert best_of_k(pool, accept)["passes"] == 0
    assert random_of_k(pool, accept, seed=1)["passes"] == 0
