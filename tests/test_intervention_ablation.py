"""Intervention Ablation Evaluation: paired-ablation effect and the gov iae CLI."""
import json

import pytest

from harness import cli_entry
from harness import governance_cli
from harness import incentive_manifest as im
from harness import intervention_ablation as ia


def _manifest(env_id="env-1"):
    return {
        "schema": im.SCHEMA, "environment_id": env_id, "kind": "finetune",
        "reward": {"declared_form": "pass rate", "source_ref": "reward.py"},
        "data_distribution": {"summary": "tasks", "source_ref": "data/"},
        "reinforced_behaviors": [], "penalized_behaviors": [],
        "scarcity_variables": [],
        "witness": {"algorithm": "sha256", "entries": [{"path": "reward.py", "sha256": "0" * 64}]},
        "does_not_prove": im.DOES_NOT_PROVE,
    }


def _log(*rows):
    return [{"trajectory_id": t, "condition": c, "misaligned": m} for t, c, m in rows]


def _pairs(intervention_misaligned, ablated_misaligned):
    rows = []
    for i, m in enumerate(intervention_misaligned):
        rows.append((f"i{i}", "intervention", m))
    for i, m in enumerate(ablated_misaligned):
        rows.append((f"a{i}", "ablated", m))
    return _log(*rows)


def test_reduces_when_intervention_lowers_misalignment():
    log = _pairs([False, False, False, True], [True, True, True, True])
    result = ia.analyze(_manifest(), log)
    assert result["verdict"] == ia.REDUCES
    assert result["intervention_misalignment_rate"] == 0.25
    assert result["ablated_misalignment_rate"] == 1.0
    assert result["effect"] == 0.75


def test_increases_when_intervention_backfires():
    log = _pairs([True, True, True, True], [False, False, False, True])
    result = ia.analyze(_manifest(), log)
    assert result["verdict"] == ia.INCREASES
    assert result["effect"] == -0.75


def test_no_effect_when_rates_are_close():
    log = _pairs([True, False, False, False], [True, False, False, False])
    result = ia.analyze(_manifest(), log)
    assert result["effect"] == 0.0
    assert result["verdict"] == ia.NO_EFFECT


def test_residual_misaligned_lists_intervention_failures():
    log = _pairs([True, False], [True, True])
    result = ia.analyze(_manifest(), log)
    assert result["residual_misaligned"] == ["i0"]


def test_both_conditions_required():
    with pytest.raises(ia.InterventionAblationError):
        ia.analyze(_manifest(), _log(("i0", "intervention", True), ("i1", "intervention", False)))


def test_empty_log_is_rejected():
    with pytest.raises(ia.InterventionAblationError):
        ia.analyze(_manifest(), [])


@pytest.mark.parametrize("bad", [
    [{"trajectory_id": "t1", "condition": "intervention"}],                    # missing misaligned
    [{"trajectory_id": "t1", "misaligned": True}],                             # missing condition
    [{"trajectory_id": "t1", "condition": "other", "misaligned": True}],       # bad condition
    [{"trajectory_id": "", "condition": "ablated", "misaligned": True}],       # empty id
    [{"trajectory_id": "t1", "condition": "ablated", "misaligned": "yes"}],    # non-bool
    [{"trajectory_id": "t1", "condition": "ablated", "misaligned": True},
     {"trajectory_id": "t1", "condition": "intervention", "misaligned": False}],  # dup id
])
def test_malformed_log_is_rejected(bad):
    with pytest.raises(ia.InterventionAblationError):
        ia.analyze(_manifest(), bad)


def test_threshold_out_of_range_is_rejected():
    with pytest.raises(ia.InterventionAblationError):
        ia.analyze(_manifest(), _pairs([False], [True]), effect_threshold=2.0)


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_cli_iae_reduces_exits_zero(tmp_path, capsys):
    m = _write(tmp_path, "m.json", _manifest())
    log = _write(tmp_path, "log.json", _pairs([False, False], [True, True]))
    assert governance_cli.main(["iae", m, log]) == 0
    assert "REDUCES" in capsys.readouterr().out


def test_cli_iae_increases_exits_one_through_cli_entry(tmp_path):
    m = _write(tmp_path, "m.json", _manifest())
    log = _write(tmp_path, "log.json", _pairs([True, True], [False, False]))
    assert cli_entry.main(["gov", "iae", m, log]) == 1
