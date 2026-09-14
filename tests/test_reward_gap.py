"""Effective-vs-Declared Reward Gap probe: gap detection and the gov erg CLI."""
import json

import pytest

from harness import cli_entry
from harness import governance_cli
from harness import incentive_manifest as im
from harness import reward_gap as rg


def _manifest(env_id="env-1"):
    return {
        "schema": im.SCHEMA, "environment_id": env_id, "kind": "rl",
        "reward": {"declared_form": "unit-test pass rate", "source_ref": "reward.py"},
        "data_distribution": {"summary": "coding tasks", "source_ref": "data/"},
        "reinforced_behaviors": ["passing tests"], "penalized_behaviors": [],
        "scarcity_variables": [],
        "witness": {"algorithm": "sha256", "entries": [{"path": "reward.py", "sha256": "0" * 64}]},
        "does_not_prove": im.DOES_NOT_PROVE,
    }


def _log(*rows):
    return [{"trajectory_id": t, "reward": r, "intent_satisfied": s} for t, r, s in rows]


def test_no_gap_when_high_reward_satisfies_intent():
    log = _log(("t1", 0.1, True), ("t2", 0.2, True), ("t3", 0.9, True), ("t4", 1.0, True))
    result = rg.analyze(_manifest(), log)
    assert result["verdict"] == rg.NO_GAP
    assert result["flagged"] == []
    assert result["does_not_prove"] == rg.ERG_DOES_NOT_PROVE
    assert result["environment_id"] == "env-1"


def test_gap_when_high_reward_fails_intent():
    log = _log(("t1", 0.1, True), ("t2", 0.2, True), ("t3", 0.9, False), ("t4", 1.0, False))
    result = rg.analyze(_manifest(), log)
    assert result["verdict"] == rg.GAP
    assert set(result["flagged"]) == {"t3", "t4"}
    assert result["threshold"] == 0.9
    assert result["gap_rate"] == 1.0


def test_gap_rate_is_fraction_of_high_reward_that_fails_intent():
    log = _log(("t1", 0.1, True), ("t2", 0.2, True), ("t3", 0.9, False), ("t4", 1.0, True))
    result = rg.analyze(_manifest(), log)
    assert result["high_reward_count"] == 2
    assert result["gap_count"] == 1
    assert result["gap_rate"] == 0.5


def test_empty_log_is_rejected():
    with pytest.raises(rg.RewardGapError):
        rg.analyze(_manifest(), [])


@pytest.mark.parametrize("bad", [
    [{"trajectory_id": "t1", "reward": 0.5}],                       # missing intent
    [{"trajectory_id": "", "reward": 0.5, "intent_satisfied": True}],  # empty id
    [{"trajectory_id": "t1", "reward": True, "intent_satisfied": True}],  # bool reward
    [{"trajectory_id": "t1", "reward": float("inf"), "intent_satisfied": True}],
    [{"trajectory_id": "t1", "reward": 1, "intent_satisfied": True},
     {"trajectory_id": "t1", "reward": 2, "intent_satisfied": False}],  # duplicate id
])
def test_malformed_log_is_rejected(bad):
    with pytest.raises(rg.RewardGapError):
        rg.analyze(_manifest(), bad)


def test_quantile_out_of_range_is_rejected():
    with pytest.raises(rg.RewardGapError):
        rg.analyze(_manifest(), _log(("t1", 1.0, True)), high_reward_quantile=1.5)


def test_cli_erg_no_gap_exits_zero(tmp_path, capsys):
    m = tmp_path / "m.json"; m.write_text(json.dumps(_manifest()), encoding="utf-8")
    log = tmp_path / "log.json"
    log.write_text(json.dumps(_log(("t1", 0.9, True), ("t2", 1.0, True))), encoding="utf-8")
    assert governance_cli.main(["erg", str(m), str(log)]) == 0
    assert "NO_GAP" in capsys.readouterr().out


def test_cli_erg_gap_exits_one_and_dispatches_through_cli_entry(tmp_path):
    m = tmp_path / "m.json"; m.write_text(json.dumps(_manifest()), encoding="utf-8")
    log = tmp_path / "log.json"
    log.write_text(json.dumps(_log(("t1", 0.1, True), ("t2", 1.0, False))), encoding="utf-8")
    assert cli_entry.main(["gov", "erg", str(m), str(log)]) == 1
