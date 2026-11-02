"""studyrun tests: python -m pytest tests/test_studyrun*.py  (from the repository root)

Each test states what must happen and asserts it. The false-success cases are the point: a stage
that scores a tampered PREREG, a changed plan or a control that cannot fail is broken even if every
honest study passes through it.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

from harness.studyrun import ledger, prereg, stage, units  # noqa: E402
from harness.studyrun.spec import SpecError, load  # noqa: E402

TOY = (ROOT / "tests" / "fixtures" / "studyrun" / "toy.py").as_posix()
EFFECT = {"a": [5.1, 5.4, 4.9, 5.6, 5.2, 5.8, 5.0, 5.3], "b": [4.0, 4.2, 3.9, 4.4, 4.1, 3.8, 4.3, 4.0]}
NO_EFFECT = {"a": [4.1, 3.9, 4.2, 4.0, 4.3, 3.8, 4.1, 4.0], "b": [4.0, 4.2, 3.9, 4.1, 4.0, 4.2, 3.9, 4.1]}


def make(tmp, data=EFFECT, control="label_shuffle", analysis="mean_diff", n=400, **extra):
    (tmp / "data.json").write_text(json.dumps(data), encoding="utf-8")
    spec = {"schema": "studyrun.spec/1", "id": "toy", "title": "Toy mean difference",
            "prereg": {"path": "PREREG.txt", "text": "Prediction: a exceeds b beyond the label-shuffle q95.\n"},
            "inputs": [{"path": "data.json"}], "code": [TOY], "seed": 7,
            "analysis": {"unit": f"{TOY}:{analysis}", "params": {"prereg": str(tmp / "PREREG.txt")}},
            "controls": [{"name": "C1", "unit": f"{TOY}:{control}", "params": {"n": n}, "compare": "analysis.diff"}],
            "verdicts": {"P1": [{"left": "analysis.diff", "op": ">", "right": "controls.C1.q95"}]},
            "ledger": {"path": "LEDGER.txt", "prefix": "F", "summary": "diff {analysis.diff:.3f}, p {controls.C1.p_ge:.3f}",
                       "scope": "the toy data only."}}
    spec.update(extra)
    path = tmp / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def locked(tmp, **kw):
    path = make(tmp, **kw)
    prereg.write(load(path))
    return path


def test_real_effect_passes_and_writes_ledger_entry(tmp_path):
    res = stage.run(locked(tmp_path))
    assert res["verdicts"]["P1"]["verdict"] == "PASS"
    assert res["controls"]["C1"]["p_ge"] < 0.01
    text = (tmp_path / "LEDGER.txt").read_text(encoding="utf-8")
    assert re.search(r"^### F1\. Toy mean difference$", text, re.M)
    assert "sha256 " + res["prereg"]["sha256"][:8] in text
    for field in ("**Date:**", "**Summary.** diff ", "**Evidence:**", "**Reintegrated:** debt", "**Scope:** the toy data only."):
        assert field in text


def test_no_effect_fails_against_its_control(tmp_path):
    res = stage.run(locked(tmp_path, data=NO_EFFECT))
    assert res["verdicts"]["P1"]["verdict"] == "FAIL"


def test_same_seed_gives_same_numbers_and_ledger_numbers_increase(tmp_path):
    path = locked(tmp_path)
    a, b = stage.run(path), stage.run(path)
    assert a["controls"]["C1"] == b["controls"]["C1"]
    assert (a["ledger_number"], b["ledger_number"]) == (1, 2)


def test_edited_prereg_blocks_before_running(tmp_path):
    path = locked(tmp_path)
    (tmp_path / "PREREG.txt").write_text("Prediction: anything goes.\n", encoding="utf-8")
    with pytest.raises(stage.Blocked, match="PREREG changed since the lock"):
        stage.run(path)
    assert not (tmp_path / "LEDGER.txt").exists()


def test_prereg_edited_during_run_blocks_scoring(tmp_path):
    path = locked(tmp_path, analysis="tamper_prereg")
    with pytest.raises(stage.Blocked, match="PREREG changed during the run"):
        stage.run(path)
    assert not (tmp_path / "LEDGER.txt").exists()
    blocked = json.loads(next((tmp_path / "out").glob("*/result.json")).read_text(encoding="utf-8"))
    assert blocked["status"] == "blocked" and "verdicts" not in blocked


def test_plan_changed_after_lock_blocks(tmp_path):
    path = locked(tmp_path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["verdicts"]["P1"][0]["op"] = "<"
    path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(stage.Blocked, match="plan .* changed"):
        stage.run(path)


def test_declared_input_hash_mismatch_blocks(tmp_path):
    path = make(tmp_path, inputs=[{"path": "data.json", "sha256": "0" * 64}])
    prereg.write(load(path))
    with pytest.raises(stage.Blocked, match="input .* hashes"):
        stage.run(path)


def test_control_that_cannot_fail_makes_verdict_untestable_not_pass(tmp_path):
    res = stage.run(locked(tmp_path, control="constant_null"))
    assert res["controls"]["C1"]["usable"] is False
    assert res["verdicts"]["P1"]["verdict"] == "UNTESTABLE"


def test_too_few_null_draws_is_unusable(tmp_path):
    res = stage.run(locked(tmp_path, control="tiny_null"))
    assert "fewer than 20" in res["controls"]["C1"]["why_unusable"]
    assert res["verdicts"]["P1"]["verdict"] == "UNTESTABLE"


def test_no_anchor_refuses_to_run(tmp_path):
    path = make(tmp_path)
    (tmp_path / "PREREG.txt").write_text("written by hand, never locked\n", encoding="utf-8")
    with pytest.raises(stage.Blocked, match="no anchor"):
        stage.run(path)


def test_prereg_is_never_rewritten(tmp_path):
    path = locked(tmp_path)
    with pytest.raises(prereg.PreregError, match="written once"):
        prereg.write(load(path))


def test_spec_without_controls_is_rejected(tmp_path):
    with pytest.raises(SpecError, match="at least one control"):
        load(make(tmp_path, controls=[]))


def test_reproduction_mismatch_is_reported(tmp_path):
    (tmp_path / "recorded.json").write_text(json.dumps({"diff": 99.0}), encoding="utf-8")
    path = locked(tmp_path, reproduce={"source": "recorded.json", "map": {"analysis.diff": "diff"}})
    res = stage.run(path, append_ledger=False)
    assert res["reproduce"]["all_ok"] is False


def test_quantile_matches_numpy_type7():
    assert units.quantile([1, 2, 3, 4], 0.95) == pytest.approx(3.85)
    assert ledger.next_number("### F3. x\n### P9. y\n### F12. z\n", "F") == 13


def test_new_lock_names_the_canonical_form_and_a_legacy_lock_still_verifies(tmp_path):
    from harness.studyrun.hashing import FORM, LEGACY_FORM
    from harness.studyrun.spec import plan_sha256
    path = locked(tmp_path)
    lock_path = tmp_path / "prereg.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock["canonical_form"] == FORM == "canonical-record/1"
    spec = load(path)
    lock.pop("canonical_form")
    lock["plan_sha256"] = plan_sha256(spec, LEGACY_FORM)
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    assert not prereg.check(spec)[1]
    lock["plan_sha256"] = plan_sha256(spec, FORM) if plan_sha256(spec, FORM) != lock["plan_sha256"] else "0" * 64
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    assert any("plan" in p for p in prereg.check(spec)[1])


def test_a_prototype_spec_keeps_its_own_wording_in_the_ledger():
    from harness.scope import LEGACY_SCOPE_KEY
    from harness.studyrun.ledger import _scope_line
    assert _scope_line({"scope": "the toy data only."}) == "- **Scope:** the toy data only."
    assert _scope_line({LEGACY_SCOPE_KEY: "outside the toy data."}) == "- **Does not prove:** outside the toy data."
