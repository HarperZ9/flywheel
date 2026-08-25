"""Receipt-to-reward: the training bridge.

A verified bench is a set of gate-decided attempts. Each attempt is a
training signal: the prompt, the model's proposal, and a reward minted
from the gate's verdict — never from a model's judgment. This module
turns benches into GRPO/QLoRA-ready JSONL so the local model trains on
proofs, on-device. The reward dataset carries the bench hash it came
from, denominators, and does_not_prove; a dataset without a bench is a
refusal, not a guess.
"""
import json

import pytest

from harness.reward_dataset import (
    rewards_from_bench,
    to_grpo_jsonl,
)

BENCH = {
    "schema": "flywheel.verified-bench/v1",
    "bench_sha256": "a" * 64,
    "attempts": [
        {"task_id": "t1", "endpoint": "ox-alpha",
         "proposed_sha256": "b" * 64, "gate_pass": True,
         "gate_ref": "rcpt_" + "a" * 32},
        {"task_id": "t2", "endpoint": "ox-alpha",
         "proposed_sha256": "c" * 64, "gate_pass": False,
         "gate_ref": "rcpt_" + "b" * 32},
        {"task_id": "t3", "endpoint": "ox-alpha",
         "proposed_sha256": "d" * 64, "gate_pass": True,
         "gate_ref": ""},
    ],
}
# t3 passed with no gate ref: an unverifiable attempt. It must never
# enter the dataset -- a reward without evidence is a fabrication.


def _proposals():
    return {"b" * 64: "proposal one", "c" * 64: "proposal two",
            "d" * 64: "proposal three"}


def test_rewards_mint_from_gate_verdicts():
    rewards = rewards_from_bench(BENCH, proposals=_proposals())
    # t3 dropped: no gate ref, no evidence, no reward.
    assert len(rewards) == 2
    assert rewards[0]["reward"] == 1.0
    assert rewards[1]["reward"] == 0.0


def test_every_reward_cites_its_evidence():
    rewards = rewards_from_bench(BENCH, proposals=_proposals())
    for r in rewards:
        assert r["gate_ref"].startswith("rcpt_")
        assert r["bench_sha256"] == "a" * 64
        assert r["proposed_sha256"] in _proposals()


def test_a_missing_proposal_is_skipped_not_invented():
    rewards = rewards_from_bench(BENCH, proposals={
        "b" * 64: "proposal one"})
    assert len(rewards) == 1, (
        "the proposal text is the training input; without it there is "
        "no pair, and inventing one is a fabrication")


def test_grpo_jsonl_shape(tmp_path):
    rewards = rewards_from_bench(BENCH, proposals=_proposals())
    out = to_grpo_jsonl(rewards, out_path=tmp_path / "grpo.jsonl")
    rows = [json.loads(line) for line in
            out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    for row in rows:
        assert set(row) == {"prompt", "completion", "reward",
                            "meta"}
        assert row["reward"] in (0.0, 1.0)
        assert row["meta"]["bench_sha256"] == "a" * 64
        assert row["meta"]["gate_ref"].startswith("rcpt_")


def test_dedup_identical_pairs(tmp_path):
    bench = {**BENCH, "attempts": [BENCH["attempts"][0],
                                   dict(BENCH["attempts"][0],
                                        task_id="t1-dup")]}
    # Both tasks share the same real prompt and the same proposal: the
    # pair trains once.
    rewards = rewards_from_bench(
        bench, proposals=_proposals(),
        task_prompts={"t1": "fix the gate", "t1-dup": "fix the gate"})
    out = to_grpo_jsonl(rewards, out_path=tmp_path / "grpo.jsonl")
    rows = [json.loads(line) for line in
            out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1, (
        "the same prompt-proposal pair trains once; duplicates only "
        "skew the gradient")
    assert rows[0]["prompt"] == "fix the gate"


def test_task_prompts_are_the_stronger_signal(tmp_path):
    rewards = rewards_from_bench(BENCH, proposals=_proposals(),
                                 task_prompts={
                                     "t1": "fix the login bug",
                                     "t2": "add the export button",
                                     "t3": "polish the docs"})
    assert rewards[0]["prompt"] == "fix the login bug"
    assert rewards[1]["prompt"] == "add the export button"


def test_a_bench_without_attempts_is_refused():
    with pytest.raises(ValueError):
        rewards_from_bench({"bench_sha256": "a" * 64, "attempts": []},
                           proposals={})
