"""The anchoring ceremony's two stages, and above all their refusals.

The run stage must be computable from the journal alone, carry no outcome, and
refuse before run_end. The analysis stage must refuse until every artifact
exists, so the ledger can never hold an anchor to a report that was still being
produced. Neither stage has an override flag; these tests satisfy the gates
honestly, with journals that really carry run_end.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "anchor_confirmatory", ROOT / "scripts" / "anchor_confirmatory.py")
ac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ac)


def _journal(tmp_path, with_run_end=True) -> Path:
    rows = [
        {"event": "run_start", "pairs": 4},
        {"event": "pair_done", "family": "zarankiewicz", "rung": "r1",
         "exit_code": 0, "wall_seconds": 10.0},
        {"event": "pair_skipped_complete", "family": "zarankiewicz",
         "rung": "r1"},
        {"event": "pair_done", "family": "zarankiewicz", "rung": "r2",
         "exit_code": 0, "wall_seconds": 20.0},
        {"event": "pair_done", "family": "rectilinear_crossing", "rung": "r1",
         "exit_code": 2, "wall_seconds": 5.5},
    ]
    if with_run_end:
        rows.append({"event": "run_end", "pairs_failed": 1})
    p = tmp_path / "confirmatory-journal.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def _reports(tmp_path) -> Path:
    d = tmp_path / "reports"
    d.mkdir(exist_ok=True)
    (d / "endpoint-report.json").write_text(json.dumps({
        "schema": "flywheel.endpoint/v1",
        "families": {"zarankiewicz": {"primary": {
            "n_bodies": 7, "n_disagreements": 0, "met": True}}},
    }), encoding="utf-8")
    (d / "arms-report.json").write_text(json.dumps(
        {"schema": "flywheel.pool-arm/v1"}), encoding="utf-8")
    (d / "confirmatory-report.md").write_text("# report\n", encoding="utf-8")
    return d


# --- refusals ---------------------------------------------------------------

def test_the_run_stage_refuses_before_run_end(tmp_path):
    journal = _journal(tmp_path, with_run_end=False)
    ce = ac._load_compute_endpoint()
    with pytest.raises(ce.EndpointGate):
        ac.run_payload(journal)


def test_the_analysis_stage_refuses_before_run_end(tmp_path):
    journal = _journal(tmp_path, with_run_end=False)
    ce = ac._load_compute_endpoint()
    with pytest.raises(ce.EndpointGate):
        ac.analysis_payload(journal, _reports(tmp_path))


def test_the_analysis_stage_refuses_a_missing_artifact(tmp_path):
    journal = _journal(tmp_path)
    reports = _reports(tmp_path)
    (reports / "arms-report.json").unlink()
    ce = ac._load_compute_endpoint()
    with pytest.raises(ce.EndpointGate) as e:
        ac.analysis_payload(journal, reports)
    assert "arms-report.json" in str(e.value)


def test_the_cli_refuses_cleanly_with_exit_three(tmp_path):
    journal = _journal(tmp_path, with_run_end=False)
    code = ac.main(["--stage", "run", "--journal", str(journal),
                    "--reports", str(tmp_path / "out")])
    assert code == 3
    assert not (tmp_path / "out" / "anchor-run-payload.json").exists()


def test_a_key_without_a_timestamp_is_refused(tmp_path):
    journal = _journal(tmp_path)
    code = ac.main(["--stage", "run", "--journal", str(journal),
                    "--reports", str(tmp_path / "out"),
                    "--key", str(tmp_path / "nope.key")])
    assert code == 3


# --- the run payload is mechanical ------------------------------------------

def test_the_run_payload_counts_and_hashes_and_nothing_else(tmp_path):
    journal = _journal(tmp_path)
    p = ac.run_payload(journal)
    assert p["pairs_done"] == 3
    assert p["pairs_failed_nonzero_exit"] == 1
    assert p["pairs_failed_reported_at_run_end"] == 1
    assert p["per_family_pairs"] == {"rectilinear_crossing": 1,
                                     "zarankiewicz": 2}
    assert p["total_wall_seconds"] == 35.5
    assert p["events"]["pair_skipped_complete"] == 1
    assert p["journal_sha256"] == ac._sha(journal)
    # The note is prose ABOUT the absence of outcomes, so it legitimately
    # contains the word "verdict"; every data field must not.
    blob = json.dumps({k: v for k, v in p.items() if k != "note"})
    for word in ("PASS", "FAIL", "verdict", "candidate_sha", "accept"):
        assert word not in blob, f"the run payload leaked {word!r}"


def test_the_run_payload_cites_the_frozen_parent(tmp_path):
    p = ac.run_payload(_journal(tmp_path))
    assert p["cites_parent_sha256"].startswith("31055c924d48fe67")


# --- the analysis payload ---------------------------------------------------

def test_the_analysis_payload_hashes_every_artifact(tmp_path):
    journal = _journal(tmp_path)
    reports = _reports(tmp_path)
    p = ac.analysis_payload(journal, reports)
    assert set(p["artifact_sha256"]) == {"endpoint-report.json",
                                         "arms-report.json",
                                         "confirmatory-report.md"}
    for name, sha in p["artifact_sha256"].items():
        assert sha == ac._sha(reports / name)
    assert p["primary_endpoint"]["zarankiewicz"] == {
        "n_bodies": 7, "n_disagreements": 0, "met": True}


def test_the_cli_writes_the_payload_and_prints_the_ceremony(tmp_path, capsys):
    journal = _journal(tmp_path)
    code = ac.main(["--stage", "run", "--journal", str(journal),
                    "--reports", str(tmp_path / "out")])
    assert code == 0
    written = json.loads((tmp_path / "out" / "anchor-run-payload.json")
                         .read_text(encoding="utf-8"))
    assert written["pairs_done"] == 3
    out = capsys.readouterr().out
    assert "prereg_event.py" in out and "--kind confirmatory-run" in out
    assert "--key <seed-path>" in out, "the command must not embed a key path"
