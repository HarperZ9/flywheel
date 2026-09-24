"""The single-use sealed confirm, its preconditions, the report and the command
line, end to end on a synthetic suite in a temporary directory."""
import hashlib
import json
import sys
import types

import pytest

import harness
from harness import decision_bench as bench
from harness import decision_bench_sealed as sealed
from tests.decision_bench_fixtures import PATH_ARM, make_manifest, write_card, write_suite


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def ready(tmp_path):
    """A sealed suite whose calibration controls passed, with the path arm and
    lexical run on both open splits. Lexical's card may not act."""
    path = write_suite(tmp_path, make_manifest(dev=20, cal=120, sealed=120))
    bench.seal(path)
    for split in ("development", "calibration"):
        bench.run(path, split, ["controls", "lexical", PATH_ARM])
    write_card(path, PATH_ARM, threshold=0.9)
    write_card(path, "lexical", status="insufficient_risk_evidence", threshold=None)
    return path


def test_the_calibration_battery_is_written_and_passes(ready):
    record = json.loads((ready.parent / "runs" / "calibration" / "battery.json").read_text())
    assert record["status"] == "pass"
    assert record["seal_sha256"] == bench.seal(ready)["seal_sha256"]


def test_a_second_confirm_on_the_same_seal_is_refused(ready):
    first = sealed.confirm(ready, PATH_ARM)
    assert first["status"] == "completed" and first["diagnostic"] is False
    spent = ready.parent / "confirm.json"
    before = _digest(spent)
    with pytest.raises(bench.BenchRefused) as again:
        sealed.confirm(ready, PATH_ARM)
    assert again.value.code == "confirm_already_spent"
    with pytest.raises(bench.BenchRefused) as other_arm:
        sealed.confirm(ready, "lexical")
    assert other_arm.value.code == "confirm_already_spent"
    assert _digest(spent) == before


def test_a_diagnostic_rerun_needs_a_spent_seal_and_never_rewrites_it(ready):
    with pytest.raises(bench.BenchRefused) as early:
        sealed.confirm(ready, PATH_ARM, diagnostic=True)
    assert early.value.code == "diagnostic_before_confirm"
    assert not (ready.parent / "confirm.json").exists()
    sealed.confirm(ready, PATH_ARM)
    before = _digest(ready.parent / "confirm.json")
    rerun = sealed.confirm(ready, PATH_ARM, diagnostic=True)
    assert rerun["diagnostic"] is True
    assert len(list((ready.parent / "diagnostics").glob("*.json"))) == 1
    assert _digest(ready.parent / "confirm.json") == before


def test_a_crash_after_the_claim_still_spends_the_seal(ready, monkeypatch):
    def crash(*args, **kwargs):
        raise RuntimeError("backend died after the claim")
    monkeypatch.setattr(bench, "run_arms", crash)
    with pytest.raises(RuntimeError):
        sealed.confirm(ready, PATH_ARM)
    claim = json.loads((ready.parent / "confirm.json").read_text())
    assert claim["status"] == "claimed"
    monkeypatch.undo()
    with pytest.raises(bench.BenchRefused) as again:
        sealed.confirm(ready, PATH_ARM)
    assert again.value.code == "confirm_already_spent"


@pytest.mark.parametrize("remove, code", [
    ("runs/calibration/battery.json", "calibration_controls_not_passed"),
    ("cards/" + bench.slug(PATH_ARM) + ".json", "no_card_for_arm"),
    ("runs/calibration/lexical.json", "baseline_not_run_on_calibration"),
])
def test_confirm_preconditions_refuse_before_the_claim(ready, remove, code):
    (ready.parent / remove).unlink()
    with pytest.raises(bench.BenchRefused) as refused:
        sealed.confirm(ready, PATH_ARM)
    assert refused.value.code == code
    assert not (ready.parent / "confirm.json").exists()


def test_a_void_calibration_battery_blocks_the_confirm(ready):
    target = ready.parent / "runs" / "calibration" / "battery.json"
    record = json.loads(target.read_text())
    record["status"] = "void"
    target.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(bench.BenchRefused) as refused:
        sealed.confirm(ready, PATH_ARM)
    assert refused.value.code == "calibration_controls_not_passed"


def test_the_confirm_reads_the_arm_and_every_baseline_once(ready):
    result = sealed.confirm(ready, PATH_ARM)
    assert set(result["arms"]) == {PATH_ARM, "lexical", "control.include_all",
                                   "control.exclude_all", "control.random",
                                   "control.label_shuffle", "control.oracle"}
    assert all(rec["split"] == "sealed" and len(rec["rows"]) == 480
               for rec in result["arms"].values())
    assert result["battery"]["status"] == "pass"
    cert = result["headline"]["certification_units"]
    assert cert["errors"] == 0 and cert["acted"] == sum(
        r["certification_unit"] and r["target"] == "false"
        for r in result["arms"][PATH_ARM]["rows"])


def test_the_report_covers_every_arm_and_control_and_the_criteria(ready):
    sealed.confirm(ready, PATH_ARM)
    body = sealed.report(ready, gpu_rate=1.0)
    assert body["void"] is False and body["headline"]["confirm"] == "completed"
    for split in ("development", "calibration"):
        assert set(body["runs"][split]) >= {PATH_ARM, "lexical", "control.oracle"}
    assert set(body["batteries"]) == {"calibration", "development", "sealed"}
    assert len(body["confirm"]["arms"]) == 7
    crit = body["criteria"]
    assert crit["1_miss_rate_bound"]["pass"] is True
    assert crit["2_negatives_excluded"]["act_recall"] == 1.0
    assert crit["3_more_tokens_than_lexical"]["pass"] is True   # lexical may not act
    assert crit["3_more_tokens_than_lexical"]["mean_token_difference"]["low"] > 0
    assert crit["4_p95_latency"]["pass"] is True and crit["5_full_pass"]["pass"] is True
    head = body["runs"]["calibration"][PATH_ARM]["headline"]
    assert head["cost_per_correct_act"] == pytest.approx(
        head["gpu_seconds"] / 3600 / head["correct_acts"])
    assert (ready.parent / "report.json").exists()


def test_the_report_is_void_when_a_battery_failed(ready):
    target = ready.parent / "runs" / "development" / "battery.json"
    record = json.loads(target.read_text())
    record["status"] = "void"
    target.write_text(json.dumps(record), encoding="utf-8")
    assert sealed.report(ready)["void"] is True


def test_fit_policy_hands_the_policy_its_documented_row_shape(ready, monkeypatch):
    calls = {}

    def fit_card(dev_rows, calibration_rows, **kwargs):
        calls.update(dev=dev_rows, cal=calibration_rows, **kwargs)
        return {"status": "statistical_candidate_only", "threshold": 0.95}
    fake = types.ModuleType("harness.decision_policy")
    fake.fit_card = fit_card
    monkeypatch.setitem(sys.modules, "harness.decision_policy", fake)
    monkeypatch.setattr(harness, "decision_policy", fake, raising=False)
    card = bench.fit_policy(ready, PATH_ARM)
    assert len(calls["dev"]) == 80 and len(calls["cal"]) == 120   # one unit per commit
    assert {r["split"] for r in calls["dev"]} == {"development"}
    assert {r["split"] for r in calls["cal"]} == {"calibration"}
    assert len({r["source_group"] for r in calls["cal"]}) == 120
    assert set(calls["cal"][0]["reading"]) == {"type", "raw", "order_agreement", "label_mass"}
    assert (calls["alpha"], calls["delta"], calls["act_on"]) == (.05, .05, ["false"])
    assert calls["meta"]["backend_id"] == "fixture:path-arm"
    assert calls["min_useful_coverage"] == 0.3
    assert len(card["bench_receipt_sha256"]) == 64
    stored = json.loads((ready.parent / "cards" / f"{bench.slug(PATH_ARM)}.json").read_text())
    assert stored == card


def test_the_fit_policy_command_maps_risk_and_confidence_onto_the_card(ready, monkeypatch,
                                                                       capsys):
    calls = []
    fake = types.ModuleType("harness.decision_policy")
    fake.fit_card = lambda dev, cal, **kw: calls.append(kw) or {"status": "uncalibrated"}
    monkeypatch.setitem(sys.modules, "harness.decision_policy", fake)
    monkeypatch.setattr(harness, "decision_policy", fake, raising=False)
    base = ["fit-policy", "--suite", str(ready), "--arm", PATH_ARM, "--act-on", "false"]
    # Section 5.4 names select_threshold's keywords: --max-error is the risk
    # target and --alpha the confidence. Distinct values show which goes where.
    assert bench.main(base + ["--max-error", "0.04", "--alpha", "0.1"]) == 0
    assert bench.main(base + ["--delta", "0.2"]) == 0
    assert bench.main(base + ["--max-error", "0.05", "--alpha", "0.05"]) == 0
    capsys.readouterr()
    assert [(c["alpha"], c["delta"]) for c in calls] == [(.04, .1), (.05, .2), (.05, .05)]
    assert all(c["act_on"] == ["false"] for c in calls)


def test_a_failed_read_blocks_fitting(ready):
    target = ready.parent / "runs" / "calibration" / f"{bench.slug(PATH_ARM)}.json"
    record = json.loads(target.read_text())
    cert = next(r for r in record["rows"] if r["certification_unit"])
    cert["raw"], cert["error_type"] = None, "RuntimeError"
    target.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(bench.BenchRefused) as refused:
        bench.fit_policy(ready, PATH_ARM)
    assert refused.value.code == "arm_runs_have_failed_reads"


def test_a_real_policy_card_flows_through_the_confirm_and_the_report(tmp_path):
    path = write_suite(tmp_path, make_manifest(dev=20, cal=160, sealed=160))
    bench.seal(path)
    for split in ("development", "calibration"):
        bench.run(path, split, ["controls", "lexical", PATH_ARM])
    card = bench.fit_policy(path, PATH_ARM)
    assert card["schema"] == "flywheel.decision-policy-card/v1"
    assert card["status"] == "statistical_candidate_only" and card["threshold"] == 0.5
    lexical = bench.fit_policy(path, "lexical")      # lexical drops changed files too
    assert lexical["status"] == "insufficient_risk_evidence"
    sealed.confirm(path, PATH_ARM)
    body = sealed.report(path)
    assert body["void"] is False
    assert {k: v["pass"] for k, v in body["criteria"].items()} == {
        "1_miss_rate_bound": True, "2_negatives_excluded": True,
        "3_more_tokens_than_lexical": True, "4_p95_latency": True, "5_full_pass": True}
    assert body["confirm"]["arms"]["lexical"]["gate"]["threshold"] == sealed.UNREACHABLE


def test_the_command_line_refuses_a_second_confirm_with_exit_2(ready, capsys):
    suite = str(ready)
    assert bench.main(["confirm", "--suite", suite, "--split", "sealed",
                       "--arm", PATH_ARM]) == 0
    capsys.readouterr()
    assert bench.main(["confirm", "--suite", suite, "--split", "sealed",
                       "--arm", PATH_ARM]) == 2
    assert json.loads(capsys.readouterr().err) == {"refused": "confirm_already_spent"}
    assert bench.main(["confirm", "--suite", suite, "--split", "calibration",
                       "--arm", PATH_ARM]) == 2
    assert bench.main(["report", "--suite", suite]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["void"] is False
