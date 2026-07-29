"""The candidate pool: no early stopping, exact pairing, tamper-evident cache.

The load-bearing test is the last one. It reconstructs the exact defect the pool
exists to remove, by showing that a pool-based baseline and treatment can
disagree in BOTH directions, which the old sequential arms could not.
"""
import json

import pytest

from harness.pool import (
    Pool, PoolError, digest, fill, make_fingerprint, fingerprint_sha256,
)


class Proposer:
    """Deterministic in (prompt, seed). Records every call so a test can assert
    that no early stopping happened."""

    def __init__(self, fail_seeds=(), answers=None):
        self.calls = []
        self.fail_seeds = set(fail_seeds)
        self.answers = answers or {}

    def generate(self, prompt, *, seed, temperature, max_new_tokens):
        self.calls.append((prompt, seed, temperature))
        if seed in self.fail_seeds:
            raise RuntimeError("connection reset by peer")
        class R:
            text = self.answers.get((prompt, seed), f"cand[{prompt}|{seed}]")
        return R()


def _fp(k=3, **kw):
    base = dict(model_ref="test:model", model_digest="sha256:" + "aa" * 32,
                engine="test", engine_version="0", quantization="none",
                k=k, seeds=list(range(k)), temperatures=[0.0] + [0.8] * (k - 1),
                max_new_tokens=64, prompt_template_sha256=None)
    base.update(kw)
    return base


TASKS = [{"task_id": "t1", "prompt": "p1"}, {"task_id": "t2", "prompt": "p2"}]


# --- the fingerprint --------------------------------------------------------

def test_an_unknown_fingerprint_field_is_refused():
    with pytest.raises(PoolError, match="unknown fingerprint"):
        make_fingerprint(**_fp(), modle_ref="typo")


def test_seeds_must_be_explicit_and_match_k():
    with pytest.raises(PoolError, match="exactly k=3"):
        make_fingerprint(**_fp(k=3, seeds=[0, 1]))


def test_duplicate_seeds_are_refused():
    with pytest.raises(PoolError, match="duplicate seeds"):
        make_fingerprint(**_fp(k=3, seeds=[0, 1, 1]))


def test_the_fingerprint_hash_is_stable_under_key_order():
    a = make_fingerprint(**_fp())
    b = make_fingerprint(**{k: v for k, v in reversed(list(_fp().items()))})
    assert fingerprint_sha256(a) == fingerprint_sha256(b)


def test_changing_one_pinned_value_changes_the_hash():
    assert (fingerprint_sha256(make_fingerprint(**_fp()))
            != fingerprint_sha256(make_fingerprint(**_fp(quantization="q4_K_M"))))


# --- no early stopping ------------------------------------------------------

def test_every_slot_is_generated_even_when_the_first_would_be_accepted(tmp_path):
    """The whole point. The old loop broke on the first accept, which is what
    made the treatment contain the baseline."""
    prop = Proposer()
    fill(TASKS, prop, _fp(k=4), tmp_path)
    assert len(prop.calls) == 8                       # 2 tasks x 4 slots, exactly
    for tid, prompt in (("t1", "p1"), ("t2", "p2")):
        seeds = sorted(s for p, s, _ in prop.calls if p == prompt)
        assert seeds == [0, 1, 2, 3]


def test_the_first_slot_is_the_seed0_temp0_draw(tmp_path):
    prop = Proposer()
    fill(TASKS, prop, _fp(k=3), tmp_path)
    first = [(s, t) for p, s, t in prop.calls if p == "p1"][0]
    assert first == (0, 0.0)


# --- generation failures ----------------------------------------------------

def test_a_failed_slot_is_recorded_not_swallowed(tmp_path):
    fill(TASKS, Proposer(fail_seeds={0}), _fp(k=3), tmp_path)
    pool = Pool(tmp_path)
    s0 = pool.slots("t1")[0]
    assert s0["candidate_sha256"] is None
    assert "connection reset" in s0["error"]
    # and the surviving slots are still usable
    assert [i for i, _ in pool.candidates("t1")] == [1, 2]


def test_health_reports_the_gaps_so_a_denominator_can_exclude_them(tmp_path):
    fill(TASKS, Proposer(fail_seeds={0, 1, 2}), _fp(k=3), tmp_path)
    h = Pool(tmp_path).health()
    assert h == {"slots_total": 6, "slots_filled": 0, "slots_failed": 6,
                 "tasks_with_no_candidate": ["t1", "t2"], "n_tasks": 2}


# --- content addressing and tamper evidence ---------------------------------

def test_identical_text_from_two_slots_is_stored_once(tmp_path):
    answers = {("p1", 0): "same", ("p1", 1): "same", ("p1", 2): "same"}
    fill([TASKS[0]], Proposer(answers=answers), _fp(k=3), tmp_path)
    assert len(list((tmp_path / "candidates").glob("*.txt"))) == 1
    pool = Pool(tmp_path)
    assert [t for _, t in pool.candidates("t1")] == ["same"] * 3


def test_editing_a_cached_candidate_is_detected(tmp_path):
    fill([TASKS[0]], Proposer(), _fp(k=1, seeds=[0], temperatures=[0.0]),
         tmp_path)
    pool = Pool(tmp_path)
    sha = pool.slots("t1")[0]["candidate_sha256"]
    path = tmp_path / "candidates" / (sha.split(":", 1)[1] + ".txt")
    path.write_text("tampered", encoding="utf-8")
    with pytest.raises(PoolError, match="does not hash to its own filename"):
        pool.text(sha)


def test_a_missing_candidate_is_an_error_not_an_empty_string(tmp_path):
    fill([TASKS[0]], Proposer(), _fp(k=1, seeds=[0], temperatures=[0.0]),
         tmp_path)
    pool = Pool(tmp_path)
    sha = pool.slots("t1")[0]["candidate_sha256"]
    (tmp_path / "candidates" / (sha.split(":", 1)[1] + ".txt")).unlink()
    with pytest.raises(PoolError, match="is missing"):
        pool.text(sha)


def test_a_non_digest_reference_is_refused(tmp_path):
    fill([TASKS[0]], Proposer(), _fp(k=1, seeds=[0], temperatures=[0.0]),
         tmp_path)
    with pytest.raises(PoolError, match="not a sha256 digest"):
        Pool(tmp_path).text("sha256:../../etc/passwd")


def test_a_task_without_an_id_is_refused(tmp_path):
    with pytest.raises(PoolError, match="needs a task_id"):
        fill([{"prompt": "p"}], Proposer(), _fp(), tmp_path)


def test_a_directory_without_an_index_is_not_a_pool(tmp_path):
    with pytest.raises(PoolError, match="no pool index"):
        Pool(tmp_path)


def test_a_wrong_schema_is_refused(tmp_path):
    (tmp_path / "pool_index.json").write_text('{"schema": "something/v9"}',
                                              encoding="utf-8")
    with pytest.raises(PoolError, match="not a candidate pool"):
        Pool(tmp_path)


# --- the property the pool exists for ---------------------------------------

def test_two_arms_over_one_pool_can_disagree_in_both_directions(tmp_path):
    """The defect, reconstructed and removed.

    Sequential arms could only disagree one way: the treatment regenerated the
    baseline's draw as its own first attempt, so no task could pass the baseline
    and fail the treatment. Over one cached pool, a baseline reading slot 0 and a
    treatment reading a different slot are genuinely independent selections, and
    discordance runs both ways. That is what makes McNemar applicable.
    """
    answers = {
        # t1: slot 0 good, slot 1 bad  -> baseline passes, treatment fails
        ("p1", 0): "GOOD", ("p1", 1): "BAD",
        # t2: slot 0 bad,  slot 1 good -> baseline fails, treatment passes
        ("p2", 0): "BAD", ("p2", 1): "GOOD",
    }
    fill(TASKS, Proposer(answers=answers),
         _fp(k=2, seeds=[0, 1], temperatures=[0.0, 0.8]), tmp_path)
    pool = Pool(tmp_path)
    accept = lambda text: text == "GOOD"

    baseline = {t: accept(dict(pool.candidates(t))[0]) for t in pool.task_ids()}
    treatment = {t: accept(dict(pool.candidates(t))[1]) for t in pool.task_ids()}

    b = sum(1 for t in baseline if baseline[t] and not treatment[t])
    c = sum(1 for t in baseline if not baseline[t] and treatment[t])
    assert (b, c) == (1, 1), "discordance must be possible in both directions"

    # Both arms saw the identical candidate set, which is what pairing means.
    assert pool.k == 2
    assert all(len(pool.candidates(t)) == 2 for t in pool.task_ids())


def test_the_pool_states_what_it_does_not_prove(tmp_path):
    fill(TASKS, Proposer(), _fp(), tmp_path)
    dnp = Pool(tmp_path).does_not_prove()
    assert any("NOT_PROVES_GENERATION_DETERMINISM" in d for d in dnp)
    assert any("NOT_PROVES_CANDIDATE_CORRECTNESS" in d for d in dnp)
