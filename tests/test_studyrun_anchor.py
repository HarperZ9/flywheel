"""Truth-anchor rule at lock time (F95 MT3): python -m pytest tests/test_studyrun*.py

A spec that scores an update-size metric with no truth-anchored measure must be refused a lock,
and nothing may be written. The same spec with an accuracy rule beside it must lock. A spec with
no update-size metric is untouched, and an existing lock still checks and runs.
"""
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

from harness.studyrun import anchor, prereg, stage  # noqa: E402
from harness.studyrun.spec import load  # noqa: E402
from tests.test_studyrun import make  # noqa: E402

TE_RULE = {"left": "analysis.transfer_entropy_true_arm", "op": ">", "right": "controls.C1.q95"}
ACC_RULE = {"left": "analysis.target_choice_accuracy", "op": ">", "right": 0.5}


def test_update_size_without_truth_anchor_is_refused_and_writes_nothing(tmp_path):
    path = make(tmp_path, verdicts={"P1": [TE_RULE]})
    with pytest.raises(prereg.PreregError, match=r"F95 MT3"):
        prereg.write(load(path))
    assert not (tmp_path / "prereg.lock.json").exists()
    assert not (tmp_path / "PREREG.txt").exists()


def test_update_size_with_truth_anchor_in_a_verdict_locks(tmp_path):
    path = make(tmp_path, verdicts={"P1": [TE_RULE], "P2": [ACC_RULE]})
    lock = prereg.write(load(path))
    assert (tmp_path / "prereg.lock.json").is_file()
    assert lock["study"] == "toy"


def test_declared_measures_are_read_and_an_unscored_anchor_does_not_count(tmp_path):
    spec = {"measures": [{"name": "dq", "kind": "update_size"}, {"name": "return", "kind": "truth_anchored"}],
            "verdicts": {"P1": [{"left": "analysis.diff", "op": ">", "right": 0}]}}
    update, truth, bad = anchor.measures(spec)
    assert update == ["dq"] and truth == []
    assert any("no verdict rule reads it" in b for b in bad)
    assert any("F95 MT3" in b for b in anchor.problems(spec))
    spec["verdicts"]["P2"] = [{"left": "analysis.return", "op": ">", "right": 0}]
    assert anchor.problems(spec) == []


@pytest.mark.parametrize("name", ["analysis.weightChangeNorm", "analysis.kl_shift", "analysis.|dQ|",
                                  "analysis.te_arm_a", "analysis.update_size"])
def test_update_size_names_are_recognised(name):
    assert anchor.problems({"verdicts": {"P": [{"left": name, "op": ">", "right": 0}]}})


def test_specs_without_update_size_and_existing_locks_are_untouched(tmp_path):
    assert anchor.problems({"verdicts": {"P": [{"left": "analysis.diff", "op": ">", "right": "controls.C1.q95"}]}}) == []
    path = make(tmp_path, verdicts={"P1": [TE_RULE]})
    spec = load(path)
    # A lock written before the rule existed: write it as the old stage did, then check and run.
    (tmp_path / "PREREG.txt").write_text(spec["prereg"]["text"], encoding="utf-8", newline="\n")
    import json
    from harness.studyrun import LOCK_SCHEMA
    from harness.studyrun.hashing import sha256_file
    from harness.studyrun.spec import plan_sha256
    lock = {"schema": LOCK_SCHEMA, "study": "toy", "prereg_path": spec["_prereg_path"],
            "prereg_sha256": sha256_file(tmp_path / "PREREG.txt"), "plan_sha256": plan_sha256(spec),
            "written_at": "2026-10-29T00:00:00+00:00"}
    (tmp_path / "prereg.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    _, bad = prereg.check(spec)
    assert bad == []
    res = stage.run(path)
    assert "P1" in res["verdicts"]
