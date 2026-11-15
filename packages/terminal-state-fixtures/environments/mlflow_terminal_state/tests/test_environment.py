"""The README's validation claims, as tests.

The environment's README states: the dataset is exhaustive (324 records) and
builds identically twice, correct answers score 1.0, wrong verdicts and garbage
score 0.0, and the subtle contract rules hold (integrity beats the oracle, a
missing oracle is an honest null). Each claim is pinned here so a change that
breaks one fails loudly instead of silently invalidating the published spec.
"""

import collections
import json

import pytest

import mlflow_terminal_state as m


# --- reference scorer contract ------------------------------------------------

def test_integrity_beats_oracle():
    # An artifact-hash mismatch refutes the run even when its oracle passed.
    run = m.RunRecord(execution="returned", provider="ok", oracle="pass",
                      receipt="verified", artifact="mismatch")
    verdict, in_denom = m.score(run)
    assert verdict is m.Verdict.REFUTED
    assert in_denom is True


def test_receipt_mismatch_also_refutes():
    run = m.RunRecord(execution="returned", provider="ok", oracle="pass",
                      receipt="mismatch", artifact="match")
    verdict, in_denom = m.score(run)
    assert verdict is m.Verdict.REFUTED
    assert in_denom is True


def test_absent_oracle_is_an_honest_null():
    # No oracle means unverifiable and excluded, never a pass.
    run = m.RunRecord(execution="returned", provider="ok", oracle="absent",
                      receipt="verified", artifact="match")
    verdict, in_denom = m.score(run)
    assert verdict is m.Verdict.UNVERIFIABLE
    assert in_denom is False


def test_non_runs_settle_before_oracle_logic():
    # A blocked launch with a passing oracle is still not a run.
    run = m.RunRecord(execution="blocked", provider="ok", oracle="pass",
                      receipt="verified", artifact="match")
    verdict, in_denom = m.score(run)
    assert verdict is m.Verdict.NOT_LAUNCHED
    assert in_denom is False


def test_denominator_is_exactly_verified_plus_refuted():
    import itertools
    for combo in itertools.product(*m.FIELDS.values()):
        run = m.RunRecord(**dict(zip(m.FIELDS.keys(), combo)))
        verdict, in_denom = m.score(run)
        assert in_denom == (verdict in (m.Verdict.VERIFIED, m.Verdict.REFUTED))


# --- dataset ------------------------------------------------------------------

def test_dataset_is_exhaustive_324():
    assert len(m.build_dataset()) == 324


def test_dataset_distribution_matches_readme():
    counts = collections.Counter(
        json.loads(r["answer"])["verdict"] for r in m.build_dataset()
    )
    assert counts == {
        "not_launched": 162, "timeout": 81, "rejected": 27, "malformed": 27,
        "refuted": 19, "verified": 4, "unverifiable": 4,
    }
    in_denom = sum(
        1 for r in m.build_dataset() if json.loads(r["answer"])["in_denominator"]
    )
    assert in_denom == 23


def test_dataset_builds_identically_twice():
    a = [dict(r) for r in m.build_dataset()]
    b = [dict(r) for r in m.build_dataset()]
    assert a == b


# --- rewards ------------------------------------------------------------------

ANSWER = json.dumps({"verdict": "refuted", "in_denominator": True})


def test_correct_answer_scores_one():
    completion = '{"verdict": "refuted", "in_denominator": true}'
    assert m.verdict_reward(completion, ANSWER) == 1.0
    assert m.denominator_reward(completion, ANSWER) == 1.0


def test_wrong_verdict_scores_zero():
    completion = '{"verdict": "verified", "in_denominator": true}'
    assert m.verdict_reward(completion, ANSWER) == 0.0
    assert m.denominator_reward(completion, ANSWER) == 1.0


def test_garbage_scores_zero():
    for completion in ("", "not json at all", '{"unrelated": 1}'):
        assert m.verdict_reward(completion, ANSWER) == 0.0
        assert m.denominator_reward(completion, ANSWER) == 0.0


def test_last_json_object_wins():
    completion = (
        'Thinking: maybe {"verdict": "verified", "in_denominator": true}.\n'
        'Final: {"verdict": "refuted", "in_denominator": true}'
    )
    assert m.verdict_reward(completion, ANSWER) == 1.0


def test_chat_completion_shape_is_read():
    completion = [
        {"role": "user", "content": "score it"},
        {"role": "assistant", "content": '{"verdict": "refuted", "in_denominator": true}'},
    ]
    assert m.verdict_reward(completion, ANSWER) == 1.0
