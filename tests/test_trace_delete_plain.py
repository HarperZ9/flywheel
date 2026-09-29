"""FW-07b: plaintext and legacy stores are deleted with the same plan, apply
and tombstone as encrypted ones. A fold note, a legacy run with its bench
row, a deleted trace's CLI profile folder and sealed result, and a v1 receipt
go; a frozen page the receipt cited stays and is listed; the report says the
profile folder's contents were never classified."""
import json

import pytest

from delete_fixtures import OWNER
from harness.trace_delete_apply import apply_plan
from harness.trace_delete_plan import make_plan
from harness.trace_presence import confirm
from harness.trace_witness import MemorySink
from plain_fixtures import (PROFILE, plant_legacy_run, plant_note, plant_profile_trace,
                            plant_v1_receipt)
from trace_enc_fakes import StreamTestProvider, using

TEXT = "PLAIN-CANARY-" + "m5" * 20


@pytest.fixture
def roots(tmp_path, monkeypatch):
    home, run = tmp_path / "home", tmp_path / "run"
    (home / "state").mkdir(parents=True)
    run.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run))
    (run / "snapshots").mkdir()
    (run / "snapshots" / ("c" * 64 + ".bin")).write_bytes(b"frozen page")
    with using(StreamTestProvider()):
        yield home, run


def _delete(home, selection):
    plan = make_plan(home, OWNER, selection)
    ref = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    return plan, apply_plan(home, OWNER, plan["plan_digest"], ref, sink=MemorySink())


def test_note_run_profile_result_and_receipt_are_removed(roots):
    home, run = roots
    note = plant_note(run, TEXT + " note")
    legacy = plant_legacy_run(run, TEXT + " goal")
    trace = plant_profile_trace(home, TEXT + " result")
    receipt = plant_v1_receipt(home, TEXT + " degraded")
    plan, report = _delete(home, {"trace_refs": [trace], "note_refs": [note],
                                  "legacy_runs": [legacy], "receipt_eids": [receipt]})
    assert {"S1", "S2", "S6", "S7", "S9", "S10", "S11"} <= set(plan["counts"])
    assert report["state"] == "DELETED", report
    assert not (home / "state" / PROFILE).exists()
    assert not (run / "agent_runs" / f"{legacy}.json").exists()
    assert note not in json.loads((run / "fold_index.json").read_text())["spans"]
    rows = (run / "bench" / "trace-tasks.jsonl").read_text()
    assert "kept task" in rows and TEXT not in rows
    assert "residual_scan" in report["checks"]


def test_a_frozen_page_cited_by_a_legacy_receipt_is_kept_and_listed(roots):
    home, run = roots
    receipt = plant_v1_receipt(home, TEXT)
    _, report = _delete(home, {"receipt_eids": [receipt]})
    assert (run / "snapshots" / ("c" * 64 + ".bin")).exists()
    assert report["residue"]["legacy_snapshots_kept"] == 1
    assert report["residue"]["legacy_fingerprint"] == 1


def test_the_report_says_profile_contents_were_unknown(roots):
    home, _ = roots
    trace = plant_profile_trace(home, TEXT)
    _, report = _delete(home, {"trace_refs": [trace]})
    assert any("never classified" in note for note in report["notes"])


def test_the_report_names_every_store_it_does_not_cover(roots):
    home, run = roots
    _, report = _delete(home, {"note_refs": [plant_note(run, TEXT)]})
    assert {"S3", "S13", "S4", "L1"} <= set(report["not_covered"])
    assert "S7" not in report["not_covered"] and "S1" not in report["not_covered"]
