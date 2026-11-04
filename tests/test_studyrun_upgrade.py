"""studyrun upgrade tests: python -m pytest tests/test_studyrun_upgrade.py  (from the repository root)

One test group per failure found this week. Each false-success case must fail closed: a dotted key that
nobody can read (F674), a gate with no power (F675), a sign-flipped plant (F675, F132), and the three
self-consistent changes recheck F673 missed (removed limit, constant changed with its outputs, post hoc
file never compared with its checkpoint).
"""
import json
import math
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

from harness.studyrun import autocheck, forecast, ledger, planted, prereg, stage, verdict  # noqa: E402
from harness.studyrun.__main__ import main  # noqa: E402
from harness.studyrun.spec import load  # noqa: E402
from tests.test_studyrun import make  # noqa: E402

P1 = [{"left": "analysis.diff", "op": ">", "right": "controls.C1.q95"}]
P2 = [{"left": "analysis.diff", "op": ">", "right": 0.5}]


def sim(diff, q95=0.2):
    return {"analysis": {"diff": diff}, "controls": {"C1": {"usable": True, "q95": q95}}}


def write_json(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path.name


# --- F674 verdictpathdots -------------------------------------------------------------------------

RES = {"analysis": {"bh": {"D1_overlap_hw.p_score": 3.1e-9}, "plain": {"x": 2}}, "controls": {}}


def test_dotted_key_reads_with_escape_or_list_path_and_old_paths_are_unchanged():
    assert verdict.get(RES, r"analysis.bh.D1_overlap_hw\.p_score") == 3.1e-9
    assert verdict.get(RES, ["analysis", "bh", "D1_overlap_hw.p_score"]) == 3.1e-9
    assert verdict.get(RES, "analysis.plain.x") == 2
    assert verdict.split_path("controls.C1.q95") == ["controls", "C1", "q95"]


def test_unescaped_dotted_key_stays_untestable_and_names_the_fix():
    row = verdict.rule(RES, {"left": "analysis.bh.D1_overlap_hw.p_score", "op": "<", "right": 0.05})
    assert row["holds"] is None
    assert "holds a dot" in row["why"] and r"D1_overlap_hw\.p_score" in row["why"]
    ok = verdict.rule(RES, {"left": ["analysis", "bh", "D1_overlap_hw.p_score"], "op": "<", "right": 0.05})
    assert ok["holds"] is True


def test_ledger_template_reads_an_escaped_key():
    assert ledger.render(r"q {analysis.bh.D1_overlap_hw\.p_score:.1e}", RES) == "q 3.1e-09"


def test_lock_refuses_a_verdict_path_that_resolves_in_no_simulated_run(tmp_path):
    sims = write_json(tmp_path / "sims.json", {"w": [sim(1.0)] * 10})
    bad = {"P1": [{"left": "analysis.bh.D1_overlap_hw.p_score", "op": "<", "right": 0.05}]}
    path = make(tmp_path, verdicts=bad, power={"bar": 0.8, "simulations": sims, "verdicts": {"P1": "w"}})
    with pytest.raises(prereg.PreregError, match="resolves in no simulated run"):
        prereg.write(load(path))
    assert not (tmp_path / "prereg.lock.json").exists()


# --- F675 gatefromsmoke ---------------------------------------------------------------------------

def test_underpowered_verdict_is_reported_non_binding(tmp_path):
    # P1 passes in 9 of 10 simulated runs, P2 in 4 of 10, bar 0.8.
    runs = [sim(1.0)] * 4 + [sim(0.3)] * 5 + [sim(0.1)]
    sims = write_json(tmp_path / "sims.json", {"w": runs})
    path = make(tmp_path, verdicts={"P1": P1, "P2": P2},
                power={"bar": 0.8, "simulations": sims, "verdicts": {"P1": "w", "P2": "w"}})
    lock = prereg.write(load(path))
    assert lock["power"]["verdicts"]["P1"]["binding"] is True
    assert lock["power"]["verdicts"]["P2"]["binding"] is False
    assert lock["power"]["verdicts"]["P2"]["power"] == pytest.approx(0.4)
    res = stage.run(path)
    assert res["verdicts"]["P2"]["binding"] is False and "under the bar" in res["verdicts"]["P2"]["why_nonbinding"]
    assert res["decision"]["binding"] == ["P1"] and "P2" in res["decision"]["nonbinding"]
    text = (tmp_path / "LEDGER.txt").read_text(encoding="utf-8")
    assert "P2 PASS (non-binding)" in text and "**Binding verdicts:** P1" in text


def test_verdict_without_simulated_power_is_non_binding_and_wilson_option_is_stricter(tmp_path):
    sims = write_json(tmp_path / "sims.json", {"w": [sim(1.0)] * 9 + [sim(0.1)]})
    path = make(tmp_path, verdicts={"P1": P1, "P2": P2},
                power={"bar": 0.8, "use": "wilson_lower", "simulations": sims, "verdicts": {"P1": "w"}})
    lock = prereg.write(load(path))
    assert lock["power"]["verdicts"]["P2"] == {"binding": False, "why_nonbinding": "no simulated power recorded at the lock"}
    assert lock["power"]["verdicts"]["P1"]["binding"] is False  # 9 of 10: Wilson lower bound about 0.60


def test_simulations_edited_after_the_lock_block_the_run(tmp_path):
    sims = write_json(tmp_path / "sims.json", {"w": [sim(1.0)] * 10})
    path = make(tmp_path, power={"bar": 0.8, "simulations": sims, "verdicts": {"P1": "w"}})
    prereg.write(load(path))
    write_json(tmp_path / "sims.json", {"w": [sim(0.0)] * 10})
    with pytest.raises(stage.Blocked, match="power simulations changed"):
        stage.run(path)


def test_upgrade_fields_added_after_an_old_lock_block_the_run(tmp_path):
    path = make(tmp_path)
    prereg.write(load(path))
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["forecasts"] = {"verdicts": {"P1": 0.9}}
    path.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(stage.Blocked, match="does not freeze"):
        stage.run(path)


# --- F675 and F132 plantedlagsign -----------------------------------------------------------------

def calib(tmp, b0=0.4, b1=-0.3, units=30, n=60, seed=3):
    import random
    rng = random.Random(seed)
    rows = []
    for u in range(units):
        t = [rng.gauss(0, 1) for _ in range(n)]
        y = [None] + [b0 * t[i] + b1 * t[i - 1] + rng.gauss(0, 0.5) for i in range(1, n)]
        rows.append({"id": f"s{u}", "y": y, "x": {"T": t}})
    return write_json(tmp / "calib.json", {"units": rows})


TERMS = [{"name": "T_lag0", "x": "T", "lag": 0}, {"name": "T_lag1", "x": "T", "lag": 1}]


def test_fit_recovers_signs_on_the_calibration_split(tmp_path):
    cfg = {"terms": TERMS}
    terms, n = planted.fit(cfg, tmp_path / calib(tmp_path))
    assert n == 30 and terms["T_lag0"]["sign"] == "+" and terms["T_lag1"]["sign"] == "-"
    assert terms["T_lag1"]["median"] == pytest.approx(-0.3, abs=0.08)


def test_sign_flipped_plant_is_refused_and_measured_sign_locks(tmp_path):
    c = calib(tmp_path)
    flipped = {"calibration": c, "terms": TERMS, "worlds": {"true_m": {"T_lag0": 0.4, "T_lag1": 0.16}}}
    path = make(tmp_path, planted=flipped)
    with pytest.raises(prereg.PreregError, match=r"T_lag1: planted \+0.16, measured sign -"):
        prereg.write(load(path))
    assert not (tmp_path / "prereg.lock.json").exists()
    right = {**flipped, "worlds": {"true_m": {"T_lag0": 0.4, "T_lag1": -0.3}}, "ratio_tol": 2.0}
    lock = prereg.write(load(make(tmp_path, planted=right)))
    assert lock["planted"]["terms"]["T_lag1"]["sign"] == "-" and lock["planted"]["worlds"]["true_m"]["ok"]


def test_plant_that_omits_a_measured_term_or_is_off_in_size_is_refused(tmp_path):
    c = calib(tmp_path)
    cfg = {"calibration": c, "terms": TERMS, "ratio_tol": 2.0,
           "worlds": {"a": {"T_lag0": 0.4}, "b": {"T_lag0": 0.4, "T_lag1": -0.02}}}
    _, bad = planted.assess({**load(make(tmp_path)), "planted": cfg}, str(tmp_path))
    assert any("a: T_lag1: measured sign - but the world leaves it out" in b for b in bad)
    assert any("b: T_lag1: planted ratio" in b for b in bad)


def test_calibration_that_is_a_test_input_is_refused(tmp_path):
    path = make(tmp_path)
    spec = load(path)
    cfg = {"calibration": calib(tmp_path), "terms": TERMS, "worlds": {"w": {"T_lag0": 0.4, "T_lag1": -0.3}}}
    spec["_inputs"].append(str(tmp_path / "calib.json"))
    _, bad = planted.assess({**spec, "planted": cfg}, str(tmp_path))
    assert any("one of the test inputs" in b for b in bad)


def test_unclear_sign_must_be_planted_both_ways():
    terms = {"T_lag0": {"sign": "+", "median": 0.2}, "T_lag1": {"sign": "unclear", "median": 0.0}}
    one = planted.check_worlds({"terms": TERMS, "worlds": {"w": {"T_lag0": 0.2, "T_lag1": 0.1}}}, terms)
    assert any("both signs" in b for b in one.get("_all", []))
    two = planted.check_worlds({"terms": TERMS, "worlds": {"w": {"T_lag0": 0.2, "T_lag1": 0.1},
                                                           "v": {"T_lag0": 0.2, "T_lag1": -0.1}}}, terms)
    assert "_all" not in two


# --- F673 misses: limit, constant, post hoc ------------------------------------------------------

def test_removed_limit_line_and_unsupported_number_fail(tmp_path):
    (tmp_path / "SRC.md").write_text("Shared-trend arm 0.126 and 0.170.\n", encoding="utf-8")
    (tmp_path / "RESULTS.md").write_text("Note: F132 saw 0.126 and 0.170 on its trend arm.\n", encoding="utf-8")
    good = {"text": "F132 saw 0.126 and 0.170", "in": ["RESULTS.md"], "source": "SRC.md", "span": "Shared-trend arm 0.126 and 0.170"}
    assert autocheck.check_limit(str(tmp_path), good, "audit")["ok"]
    wrong = {**good, "text": "F132 saw 0.126 and 0.180"}
    assert any("0.18" in p for p in autocheck.check_limit(str(tmp_path), wrong, "audit")["problems"])
    (tmp_path / "RESULTS.md").write_text("Note: nothing to see.\n", encoding="utf-8")
    assert any("removed" in p for p in autocheck.check_limit(str(tmp_path), good, "audit")["problems"])
    (tmp_path / "SRC.md").write_text("Shared-trend arm 0.2.\n", encoding="utf-8")
    assert any("no longer in" in p for p in autocheck.check_limit(str(tmp_path), good, "lock")["problems"])


def test_constant_changed_with_its_outputs_is_caught_by_an_independent_derivation(tmp_path):
    (tmp_path / "study_d.py").write_text("import math\nK = 3 / (4 * math.pi ** 2)\nY = K * 2\n", encoding="utf-8")
    (tmp_path / "derive.py").write_text("import math\n\ndef purcell(ctx):\n    return 3 / (4 * math.pi ** 2)\n", encoding="utf-8")
    spec = load(make(tmp_path, code=[str(tmp_path / "study_d.py")]))
    row = {"name": "Purcell", "code": "study_d.py", "symbol": "K", "derive": "derive.py:purcell"}
    assert autocheck.check_constant(spec, row, "lock")["ok"]
    (tmp_path / "study_d.py").write_text("K = 0.0855\nY = K * 2\n", encoding="utf-8")
    assert not autocheck.check_constant(spec, row, "lock")["ok"]


def test_derivation_that_imports_study_code_is_not_independent(tmp_path):
    (tmp_path / "study_d.py").write_text("K = 0.5\n", encoding="utf-8")
    (tmp_path / "lazy.py").write_text("import study_d\n\ndef k(ctx):\n    return study_d.K\n", encoding="utf-8")
    spec = load(make(tmp_path, code=[str(tmp_path / "study_d.py")]))
    rep = autocheck.check_constant(spec, {"code": "study_d.py", "symbol": "K", "derive": "lazy.py:k"}, "lock")
    assert any("imports study code study_d" in p for p in rep["problems"])


def test_post_hoc_file_is_sealed_then_any_change_to_it_or_its_checkpoint_fails(tmp_path):
    path = locked_spec(tmp_path)
    res = stage.run(path, append_ledger=False)
    ck = f"out/{res['run_id']}/result.json"
    (tmp_path / "posthoc_sign.txt").write_text("median -0.127\n", encoding="utf-8")
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["posthoc"] = [{"file": "posthoc_sign.txt", "checkpoint": ck}]
    path.write_text(json.dumps(spec), encoding="utf-8")
    assert main(["audit", str(path)]) == 0
    assert (tmp_path / "prereg.lock.posthoc.json").is_file()
    (tmp_path / "posthoc_sign.txt").write_text("median +0.127\n", encoding="utf-8")
    rep = autocheck.run(load(path), "audit")
    assert not rep["ok"] and any("changed since it was sealed" in p for p in rep["problems"])
    (tmp_path / "posthoc_sign.txt").write_text("median -0.127\n", encoding="utf-8")
    (tmp_path / ck).write_text("{}", encoding="utf-8")
    rep = autocheck.run(load(path), "audit")
    assert any("manifest says" in p for p in rep["problems"]) and any("checkpoint result.json changed" in p for p in rep["problems"])


def test_unregistered_post_hoc_file_is_reported(tmp_path):
    path = locked_spec(tmp_path)
    (tmp_path / "posthoc_extra.txt").write_text("x\n", encoding="utf-8")
    rep = autocheck.run(load(path), "audit")
    assert rep["unregistered_posthoc"] == ["posthoc_extra.txt"] and not rep["ok"]


def locked_spec(tmp, **kw):
    path = make(tmp, **kw)
    prereg.write(load(path))
    return path


# --- forecasts ------------------------------------------------------------------------------------

def test_brier_and_log_score_per_verdict_and_untestable_is_not_scored():
    res = {"verdicts": {"A": {"verdict": "PASS"}, "B": {"verdict": "FAIL"}, "C": {"verdict": "UNTESTABLE"}},
           "analysis": {"d": 1.2}}
    sc = forecast.score({"verdicts": {"A": 0.8, "B": 0.3, "C": 0.5},
                         "quantities": {"analysis.d": {"point": -0.05, "lo": -0.3, "hi": 0.2}}}, res)
    a, b = sc["verdicts"]
    assert a["brier"] == pytest.approx(0.04) and a["log_score"] == pytest.approx(math.log(0.8))
    assert b["brier"] == pytest.approx(0.09) and b["log_score"] == pytest.approx(math.log(0.7))
    assert sc["summary"]["untestable_not_scored"] == ["C"] and sc["summary"]["n_scored"] == 2
    q = sc["quantities"][0]
    assert q["inside"] is False and "log10_ratio" not in q  # sign wrong: no ratio, only the miss
    assert sc["summary"]["interval_coverage"] == 0


def test_forecast_scores_land_in_result_and_ledger(tmp_path):
    path = locked_spec(tmp_path, forecasts={"verdicts": {"P1": 0.9}, "quantities": {"analysis.diff": {"point": 0.5}}})
    res = stage.run(path)
    assert res["forecast_scores"]["verdicts"][0]["brier"] == pytest.approx(0.01)
    assert "**Forecast score:** Brier 0.010" in (tmp_path / "LEDGER.txt").read_text(encoding="utf-8")


# --- spec/2 and the CLI ---------------------------------------------------------------------------

def test_spec_v2_refuses_a_lock_without_the_upgrade_steps(tmp_path):
    path = make(tmp_path, schema="studyrun.spec/2")
    with pytest.raises(prereg.PreregError) as e:
        prereg.write(load(path))
    for need in ("forecasts.verdicts", "power section", "planted section", "limits list", "at least one constant"):
        assert need in str(e.value)


def test_spec_v2_with_every_step_locks_runs_and_autochecks(tmp_path):
    (tmp_path / "derive.py").write_text("def seven(ctx):\n    return 7\n", encoding="utf-8")
    sims = write_json(tmp_path / "sims.json", {"w": [sim(1.0)] * 10})
    path = make(tmp_path, schema="studyrun.spec/2", forecasts={"verdicts": {"P1": 0.8}},
                power={"bar": 0.8, "simulations": sims, "verdicts": {"P1": "w"}},
                planted={"none": "the toy plants no world"}, limits=[],
                constants=[{"name": "seed", "value_path": "analysis.n", "derive": "derive.py:seven", "tol": 100}])
    prereg.write(load(path))
    res = stage.run(path)
    assert res["verdicts"]["P1"]["verdict"] == "PASS" and res["verdicts"]["P1"]["binding"] is True
    assert res["autocheck"]["ok"] and res["autocheck"]["constants"][0]["derived"] == 7


def test_cli_check_still_works_and_reports_unresolved_paths(tmp_path, capsys):
    path = locked_spec(tmp_path)
    assert main(["check", str(path)]) == 0
    write_json(tmp_path / "r.json", {"analysis": {}, "controls": {}})
    assert main(["check", str(path), "--result", str(tmp_path / "r.json")]) == 2
    assert "unresolved_paths" in capsys.readouterr().out
