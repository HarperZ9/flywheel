"""Decision bench acceptance tests (design record section 5.5, Bench): the seal,
the leak detector, and the control battery on a synthetic suite.

Synthetic suites only; a pass here says the harness separates its controls,
never that any arm is good.
"""
import copy
import json

import pytest

from harness import decision_bench as bench
from harness import decision_bench_metrics as metrics
from harness.decision_backends import read_items, resolve
from harness.decision_backends.controls import CONTROL_ARMS, battery
from tests.decision_bench_fixtures import make_items, make_manifest, state_for, write_suite

ACT_ON = ["false"]


@pytest.fixture(scope="module")
def manifest():
    return make_manifest()


@pytest.fixture(scope="module")
def control_rows(manifest):
    items = [i for i in manifest["items"] if i["split"] == "calibration"]
    arms = resolve("controls", items=items, act_on=ACT_ON, seed=1709, coverage=.3)
    return {arm: read_items(backend, items)[0] for arm, backend in arms}


def _clear_leak(manifest):
    return metrics.leak_report(manifest["items"])


# ---- the seal -------------------------------------------------------------

MUTATIONS = {
    "state": lambda it: it.update(state=it["state"] + " x"),
    "question": lambda it: it["question"].update(instructions="Does it change?"),
    "target": lambda it: it.update(target="true" if it["target"] == "false" else "false"),
    "tokens": lambda it: it.update(tokens=it["tokens"] + 1),
    "certification_unit": lambda it: it.update(certification_unit=not it["certification_unit"]),
    "label_kind": lambda it: it.update(label_kind="teacher"),
    "label_source_ref": lambda it: it.update(label_source_ref="synthetic:other"),
    "item_id": lambda it: it.update(item_id=it["item_id"] + "b"),
    "split": lambda it: it.update(split="sealed" if it["split"] != "sealed" else "development"),
}


@pytest.mark.parametrize("field", sorted(MUTATIONS))
@pytest.mark.parametrize("index", [0, 517, -1])
def test_changing_any_item_changes_the_seal_hash(manifest, field, index):
    changed = copy.deepcopy(manifest)
    MUTATIONS[field](changed["items"][index])
    assert bench.seal_sha256(changed) != bench.seal_sha256(manifest)


def test_reordering_items_or_dropping_one_changes_the_seal_hash(manifest):
    reordered = copy.deepcopy(manifest)
    reordered["items"][0], reordered["items"][1] = reordered["items"][1], reordered["items"][0]
    dropped = copy.deepcopy(manifest)
    dropped["items"].pop()
    base = bench.seal_sha256(manifest)
    assert bench.seal_sha256(reordered) != base
    assert bench.seal_sha256(dropped) != base
    assert bench.seal_sha256(copy.deepcopy(manifest)) == base


def test_a_sealed_suite_refuses_a_changed_manifest_and_a_second_seal(tmp_path):
    path = write_suite(tmp_path)
    record = bench.seal(path)
    assert record["seal_sha256"] == bench.seal_sha256(json.loads(path.read_text()))
    assert bench.seal(path)["seal_sha256"] == record["seal_sha256"]   # idempotent
    changed = json.loads(path.read_text())
    changed["items"][3]["tokens"] += 7
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(bench.BenchRefused) as later:
        bench.run(path, "development", ["lexical"])
    assert later.value.code == "manifest_changed_after_seal"
    with pytest.raises(bench.BenchRefused) as reseal:
        bench.seal(path)
    assert reseal.value.code == "seal_exists_with_other_hash"


def test_run_refuses_the_sealed_split_and_an_unsealed_suite(tmp_path):
    path = write_suite(tmp_path)
    with pytest.raises(bench.BenchRefused) as unsealed:
        bench.run(path, "development", ["lexical"])
    assert unsealed.value.code == "suite_not_sealed"
    bench.seal(path)
    with pytest.raises(bench.BenchRefused) as sealed:
        bench.run(path, "sealed", ["lexical"])
    assert sealed.value.code == "sealed_split_is_confirm_only"
    assert not (path.parent / "runs" / "sealed").exists()


@pytest.mark.parametrize("defect, code", [
    (lambda m: m["items"][1].update(state="another state"), "unit_split_or_state_mismatch"),
    (lambda m: m["items"][0].update(target="maybe"), "item_target"),
    (lambda m: m["items"][0].update(certification_unit=not m["items"][0]["certification_unit"]),
     "one_certification_unit_per_unit"),
    (lambda m: m["items"][0]["question"].update(type="unknown"), "item_question"),
    (lambda m: m["items"][0].update(label_kind="guess"), "item_provenance"),
    (lambda m: m["items"].append(copy.deepcopy(m["items"][0])), "item_id_duplicate"),
])
def test_manifest_defects_are_refused_with_fixed_codes(defect, code):
    broken = make_manifest(dev=2, cal=2, sealed=2)
    defect(broken)
    with pytest.raises(bench.BenchRefused) as refused:
        bench.validate_manifest(broken)
    assert refused.value.code == code


# ---- the leak detector ----------------------------------------------------

def test_a_clean_suite_does_not_trip_the_leak_detector(manifest):
    leak = _clear_leak(manifest)
    assert leak["tripped"] is False
    assert leak["splits"]["sealed"]["flagged"] == 0
    assert leak["splits"]["calibration"]["flagged"] == 0


def test_a_planted_duplicate_state_trips_the_leak_detector():
    items = make_items("development", 10) + make_items("calibration", 10) + make_items("sealed", 40)
    planted = state_for("dev0003")
    for item in items:
        if item["unit_id"] == "sea0007":
            item["state"] = planted
    leak = metrics.leak_report(items)
    sealed = leak["splits"]["sealed"]
    assert sealed["flagged_units"] == [{"unit_id": "sea0007", "containment": 1.0}]
    assert sealed["share"] == 1 / 40 and leak["tripped"] is True


def test_a_near_duplicate_state_is_flagged_and_the_two_percent_line_holds():
    items = make_items("development", 10) + make_items("sealed", 100)
    words = state_for("dev0001", words=30).split()
    words[-1] = "edited"                       # 1 of 24 shingles differs
    for item in items:
        if item["unit_id"] in ("sea0010", "sea0011"):
            item["state"] = " ".join(words)
    for item in items:
        if item["unit_id"] == "dev0001":
            item["state"] = state_for("dev0001", words=30)
    leak = metrics.leak_report(items)
    flagged = leak["splits"]["sealed"]["flagged_units"]
    assert [f["unit_id"] for f in flagged] == ["sea0010", "sea0011"]
    assert all(0.5 < f["containment"] < 1 for f in flagged)
    assert leak["splits"]["sealed"]["share"] == 0.02 and leak["tripped"] is False


# ---- the control battery --------------------------------------------------

def test_label_shuffle_certifies_nothing_on_the_synthetic_suite(control_rows):
    result = metrics.certify(control_rows["control.label_shuffle"], ACT_ON)
    assert result["status"] == "insufficient_risk_evidence"
    assert result["threshold"] is None and result["units"] == 200


def test_the_screen_can_certify_so_the_shuffle_null_is_not_vacuous(control_rows):
    result = metrics.certify(control_rows["control.oracle"], ACT_ON)
    assert result["status"] == metrics.CERTIFIED
    assert result["threshold"] == 0.5


def test_the_oracle_scores_100_percent(control_rows):
    rows = control_rows["control.oracle"]
    views = [metrics.view(r, ACT_ON) for r in rows]
    assert len(rows) == 800 and all(v["correct"] for v in views)
    assert metrics.selective_risk(rows, views, ACT_ON)["errors"] == 0


def test_include_all_saves_zero_tokens(control_rows):
    rows = control_rows["control.include_all"]
    risk = metrics.selective_risk(rows, [metrics.view(r, ACT_ON) for r in rows], ACT_ON)
    assert risk["acted"] == 0 and risk["tokens_excluded"] == 0
    assert risk["tokens_total"] == 200 * (100 + 200 + 300 + 400)


def test_exclude_all_fails_the_risk_bound(control_rows):
    cert = [r for r in control_rows["control.exclude_all"] if r["certification_unit"]]
    risk = metrics.selective_risk(cert, [metrics.view(r, ACT_ON) for r in cert], ACT_ON)
    positives = sum(r["target"] == "true" for r in cert)
    assert risk["acted"] == 200 and risk["errors"] == positives > 0
    assert risk["upper_error_bound"] > 0.05


def test_the_battery_passes_on_the_synthetic_suite(control_rows, manifest):
    result = battery(control_rows, ACT_ON, leak=_clear_leak(manifest))
    assert result["status"] == "pass"
    assert all(check["pass"] for check in result["checks"].values())
    assert result["checks"]["oracle_scores_100"]["top1_accuracy"] == 1.0


def _flip_one_target(rows):
    rows = copy.deepcopy(rows)
    rows[5]["target"] = "true" if rows[5]["target"] == "false" else "false"
    return rows


PLANTED_FAULTS = {
    # labels joined to the wrong items: the oracle misses one
    "oracle_scores_100": lambda runs: runs.update(
        {"control.oracle": _flip_one_target(runs["control.oracle"])}),
    # abstention scored as exclusion: include-all drops tokens
    "include_all_saves_zero": lambda runs: runs.update(
        {"control.include_all": runs["control.exclude_all"]}),
    # labels leak into the arm: the shuffle certifies
    "label_shuffle_certifies_nothing": lambda runs: runs.update(
        {"control.label_shuffle": runs["control.oracle"]}),
}


@pytest.mark.parametrize("check", sorted(PLANTED_FAULTS))
def test_a_planted_harness_fault_voids_the_battery(control_rows, manifest, check):
    runs = dict(control_rows)
    PLANTED_FAULTS[check](runs)
    result = battery(runs, ACT_ON, leak=_clear_leak(manifest))
    assert result["status"] == "void"
    assert [k for k, c in result["checks"].items() if not c["pass"]] == [check]


def test_exclude_all_passing_the_bound_voids_the_battery(manifest):
    items = [dict(i, target="false") for i in manifest["items"] if i["split"] == "calibration"]
    arms = resolve("controls", items=items, act_on=ACT_ON)
    runs = {arm: read_items(backend, items)[0] for arm, backend in arms}
    result = battery(runs, ACT_ON, leak=_clear_leak(manifest))
    assert result["status"] == "void"
    assert result["checks"]["exclude_all_fails_bound"]["pass"] is False


def test_a_tripped_leak_voids_the_battery_and_every_control_is_required(control_rows, manifest):
    leak = dict(_clear_leak(manifest), tripped=True)
    assert battery(control_rows, ACT_ON, leak=leak)["status"] == "void"
    partial = {k: v for k, v in control_rows.items() if k != CONTROL_ARMS[0]}
    with pytest.raises(ValueError):
        battery(partial, ACT_ON, leak=_clear_leak(manifest))
