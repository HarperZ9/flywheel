"""Attribution False-Accept Rate probe: false accepts over known-null controls and the gov far CLI."""
import json

import pytest

from harness import attribution_far as af
from harness import cli_entry
from harness import governance_cli
from harness import incentive_manifest as im


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


def _trials(controls, reals=()):
    out = []
    for i, attributed in enumerate(controls):
        out.append({"trial_id": f"c{i}", "is_control": True, "attributed": attributed})
    for i, attributed in enumerate(reals):
        out.append({"trial_id": f"r{i}", "is_control": False, "attributed": attributed})
    return out


def test_reliable_when_controls_are_mostly_rejected():
    trials = _trials([False] * 10, reals=[True, True, False])
    result = af.analyze(_manifest(), trials)
    assert result["verdict"] == af.RELIABLE
    assert result["false_accept_rate"] == 0.0
    assert result["control_count"] == 10
    assert result["detection_rate"] == round(2 / 3, 4)
    assert result["does_not_prove"] == af.FAR_DOES_NOT_PROVE


def test_unreliable_when_controls_are_falsely_attributed():
    trials = _trials([True, True, False, False, False, False])  # FAR = 2/6 = 0.333
    result = af.analyze(_manifest(), trials)
    assert result["verdict"] == af.UNRELIABLE
    assert result["false_accept_rate"] == round(2 / 6, 4)
    assert set(result["flagged"]) == {"c0", "c1"}


def test_far_at_threshold_is_reliable():
    # 1 false accept in 20 controls = 0.05, exactly the default threshold
    trials = _trials([True] + [False] * 19)
    result = af.analyze(_manifest(), trials)
    assert result["false_accept_rate"] == 0.05
    assert result["verdict"] == af.RELIABLE


def test_too_few_controls_is_rejected():
    with pytest.raises(af.AttributionFARError):
        af.analyze(_manifest(), _trials([False] * 4))  # below MIN_CONTROLS


def test_detection_rate_is_none_without_real_trials():
    result = af.analyze(_manifest(), _trials([False] * 5))
    assert result["detection_rate"] is None
    assert result["verdict"] == af.RELIABLE


def test_empty_trials_rejected():
    with pytest.raises(af.AttributionFARError):
        af.analyze(_manifest(), [])


@pytest.mark.parametrize("bad", [
    [{"trial_id": "c1", "is_control": True}],                              # missing attributed
    [{"trial_id": "c1", "attributed": False}],                            # missing is_control
    [{"trial_id": "", "is_control": True, "attributed": False}],          # empty id
    [{"trial_id": "c1", "is_control": "yes", "attributed": False}],       # non-bool control
    [{"trial_id": "c1", "is_control": True, "attributed": 0}],            # non-bool attributed
    [{"trial_id": "c1", "is_control": True, "attributed": False},
     {"trial_id": "c1", "is_control": True, "attributed": True}],         # dup id
])
def test_malformed_trials_rejected(bad):
    with pytest.raises(af.AttributionFARError):
        af.analyze(_manifest(), bad)


def test_threshold_out_of_range_rejected():
    with pytest.raises(af.AttributionFARError):
        af.analyze(_manifest(), _trials([False] * 5), far_threshold=1.5)


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_cli_far_reliable_exits_zero(tmp_path, capsys):
    m = _write(tmp_path, "m.json", _manifest())
    t = _write(tmp_path, "t.json", _trials([False] * 6))
    assert governance_cli.main(["far", m, t]) == 0
    assert "RELIABLE" in capsys.readouterr().out


def test_cli_far_unreliable_exits_one_through_cli_entry(tmp_path):
    m = _write(tmp_path, "m.json", _manifest())
    t = _write(tmp_path, "t.json", _trials([True, True, True, False, False]))
    assert cli_entry.main(["gov", "far", m, t]) == 1
