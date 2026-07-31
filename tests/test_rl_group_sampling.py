from harness.rl_from_oracle import RLFromOracle
from harness.oracle import OracleResult
from harness.task import Task
from harness.verdict import Verdict, Execution, Attribution


class _RecordingProposer:
    """Records the sampling parameters it was called with."""

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=None):
        self.calls.append({"seed": seed, "temperature": temperature})

        class _Out:
            text = f"candidate-{seed}"
        return _Out()


class _AlwaysOracle:
    oracle_type = "stub"

    def __init__(self, result):
        self._result = result

    def verify(self, candidate, task):
        return self._result


def _task():
    return Task(task_id="t1", prompt="p", oracle="stub", oracle_cmd="",
                workdir=".", candidate_path="c.py", max_new_tokens=8)


def _pass_fail_oracle():
    class _Alternating:
        oracle_type = "stub"

        def __init__(self):
            self.n = 0

        def verify(self, candidate, task):
            self.n += 1
            return OracleResult(passed=(self.n % 2 == 0), cmd="c",
                                output_hash="h", stdout_excerpt="", rc=0)
    return _Alternating()


def test_every_rollout_in_a_group_shares_one_temperature():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=4, temperature=0.9)
    rl.collect(_task(), _pass_fail_oracle())
    temps = {c["temperature"] for c in p.calls}
    assert temps == {0.9}


def test_no_greedy_sample_ever_enters_a_training_group():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=8, temperature=1.0)
    rl.collect(_task(), _pass_fail_oracle())
    assert all(c["temperature"] > 0.0 for c in p.calls)


def test_zero_temperature_is_refused_at_construction():
    import pytest
    with pytest.raises(ValueError):
        RLFromOracle(_RecordingProposer(), group_size=4, temperature=0.0)


def test_seeds_are_distinct_within_a_group():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=6, temperature=1.0)
    rl.collect(_task(), _pass_fail_oracle())
    seeds = [c["seed"] for c in p.calls]
    assert len(set(seeds)) == 6


def test_seeds_advance_between_steps_so_groups_are_not_replays():
    p = _RecordingProposer()
    rl = RLFromOracle(p, group_size=4, temperature=1.0)
    rl.collect(_task(), _pass_fail_oracle())
    first = [c["seed"] for c in p.calls]
    p.calls.clear()
    rl.collect(_task(), _pass_fail_oracle())
    second = [c["seed"] for c in p.calls]
    assert set(first).isdisjoint(second)


def test_undecided_is_loss_masked_with_zero_advantage_and_still_counted():
    undecided = OracleResult(verdict_=Verdict.UNDECIDED, cmd="c",
                             output_hash="h", stdout_excerpt="", rc=0)
    rl = RLFromOracle(_RecordingProposer(), group_size=4, temperature=1.0)
    g = rl.collect(_task(), _AlwaysOracle(undecided))
    assert g.n_undecided == 4
    assert all(r.loss_masked for r in g.rollouts)
    assert all(r.advantage == 0.0 for r in g.rollouts)
    assert g.learnable is False


def test_candidate_attributable_timeout_scores_a_real_fail():
    timed_out = OracleResult(verdict_=Verdict.FAIL, cmd="c", output_hash="h",
                             stdout_excerpt="", rc=1,
                             execution=Execution.TIMEOUT)
    rl = RLFromOracle(_RecordingProposer(), group_size=2, temperature=1.0)
    g = rl.collect(_task(), _AlwaysOracle(timed_out))
    assert all(r.reward == 0.0 for r in g.rollouts)
    assert all(not r.loss_masked for r in g.rollouts)
    assert g.n_excluded == 0


def test_harness_attributable_failure_is_excluded_and_recorded():
    broken = OracleResult(verdict_=Verdict.UNVERIFIABLE, cmd="c",
                          output_hash="h", stdout_excerpt="", rc=1,
                          execution=Execution.HARNESS_ERROR)
    rl = RLFromOracle(_RecordingProposer(), group_size=3, temperature=1.0)
    g = rl.collect(_task(), _AlwaysOracle(broken))
    assert g.n_excluded == 3
    assert len(g.excluded) == 3
    assert g.excluded[0]["attribution"] == Attribution.HARNESS.value
    assert g.rollouts == []


def test_group_records_its_temperature_and_estimator():
    rl = RLFromOracle(_RecordingProposer(), group_size=2, temperature=0.7,
                      estimator="drgrpo")
    g = rl.collect(_task(), _pass_fail_oracle())
    assert g.temperature == 0.7
    assert g.estimator == "drgrpo"


def test_the_receipt_carries_temperature_and_exclusions():
    broken = OracleResult(verdict_=Verdict.UNVERIFIABLE, cmd="c",
                          output_hash="h", stdout_excerpt="", rc=1,
                          execution=Execution.HARNESS_ERROR)
    rl = RLFromOracle(_RecordingProposer(), group_size=2, temperature=0.8)
    d = rl.collect(_task(), _AlwaysOracle(broken)).to_dict()
    assert d["temperature"] == 0.8
    assert d["estimator"] == "drgrpo"
    assert d["n_excluded"] == 2
    assert len(d["excluded"]) == 2
