"""Priced exit: an honest "cannot complete" result, default price 0.

Success criteria:
- default config: an exit scores exactly what a failure scores;
- a config that prices an exit below a caught cheat is refused at load;
- false-success control: with the invariant check stubbed out, the same config
  loads, so the refusal comes from the invariant and not from elsewhere;
- exit_price outside [0, 1] and unknown settings are refused;
- parse_exit reads the typed result and ignores ordinary answers;
- reward rows score EXIT and CHEAT_CAUGHT attempts through the policy.
"""
from __future__ import annotations

import pytest

from harness import exit_outcome
from harness.exit_outcome import (CHEAT_CAUGHT, EXIT, FAIL, PASS, ExitPolicy,
                                  ExitPolicyError, parse_exit)
from harness.reward_dataset import rewards_from_bench


def test_default_exit_scores_as_failure():
    p = ExitPolicy()
    assert p.exit_price == 0.0
    assert p.score(EXIT) == p.score(FAIL) == 0.0
    assert p.score(PASS) == 1.0


def test_priced_exit_scales_between_fail_and_pass():
    assert ExitPolicy.from_config({"exit_price": 0.25}).score(EXIT) == 0.25


def test_exit_below_caught_cheat_is_refused():
    with pytest.raises(ExitPolicyError):
        ExitPolicy.from_config({"cheat_caught_score": 0.5})


def test_control_without_the_invariant_the_bad_config_loads(monkeypatch):
    monkeypatch.setattr(exit_outcome, "check_invariant", lambda policy: None)
    p = ExitPolicy.from_config({"cheat_caught_score": 0.5})
    assert p.score(EXIT) < p.score(CHEAT_CAUGHT)


@pytest.mark.parametrize("cfg", [{"exit_price": -0.1}, {"exit_price": 1.5},
                                 {"exit_bonus": 1}, {"pass_score": 0, "fail_score": 0}])
def test_bad_settings_are_refused(cfg):
    with pytest.raises(ExitPolicyError):
        ExitPolicy.from_config(cfg)


def test_parse_exit():
    got = parse_exit('{"flywheel_exit": {"reason": "spec contradicts test 3", "falsifier": "t"}}')
    assert got.reason == "spec contradicts test 3" and got.falsifier == "t"
    for text in ("def f(): pass", '{"flywheel_exit": {"reason": "  "}}', "[]", '{"a": 1}'):
        assert parse_exit(text) is None


def test_rewards_use_the_policy_for_exit_and_caught_cheat():
    bench = {"bench_sha256": "b" * 64, "attempts": [
        {"task_id": "t1", "gate_ref": "g1", "proposed_sha256": "p1", "outcome": EXIT},
        {"task_id": "t2", "gate_ref": "g2", "proposed_sha256": "p2", "outcome": CHEAT_CAUGHT},
        {"task_id": "t3", "gate_ref": "g3", "proposed_sha256": "p3", "gate_pass": True}]}
    props = {"p1": "exit", "p2": "cheat", "p3": "answer"}
    rows = rewards_from_bench(bench, proposals=props,
                              exit_policy=ExitPolicy.from_config({"exit_price": 0.25}))
    assert [r["reward"] for r in rows] == [0.25, 0.0, 1.0]
    assert [r["reward"] for r in rewards_from_bench(bench, proposals=props)] == [0.0, 0.0, 1.0]
