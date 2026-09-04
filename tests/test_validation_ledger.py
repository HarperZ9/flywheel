"""The output contract on the loop's critical path, and the ledger behind it.

PR #75 shipped the checker with an honest null: nothing ran it. These are the
falsifiers for closing that. The load-bearing one is
`test_a_candidate_its_oracle_passes_is_not_accepted_when_it_holds`: the oracle
is satisfied, the tests are green, and the answer still disagrees with the
source that decides it. Before this wiring that run was an accepted run.
"""
import json
from pathlib import Path

import pytest

from harness.contract_stage import answer_from, holds, stage_payload, validate_output
from harness.contract_terms import CRITICAL, HOLD, RELEASE, RELEASE_WITH_CAVEAT
from harness.loop import run_loop
from harness.oracle import PytestOracle
from harness.output_contract import RECOMPUTE, new_contract
from harness.proposer import StubProposer
from harness.task import load_task
from harness.validation_ledger import (GOAL, SESSION, TASK, ledger_path,
                                       outstanding, read_ledger, record,
                                       roll_up)
from harness.verdict import Verdict

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"
CORRECT = "def add(a, b):\n    return a + b\n"

CONTRACT = new_contract([{"name": "tax", "authority": RECOMPUTE,
                          "source": "table:2026", "criticality": CRITICAL}])
AUTHORITIES = {"table:2026": lambda _a: 4169.0}


def _answer(value):
    return lambda _candidate: {"tax": {"value": value, "source": "table:2026"}}


# --- the answer extractor --------------------------------------------------

def test_a_bare_json_object_is_the_answer():
    assert answer_from('{"tax": {"value": 1}}') == {"tax": {"value": 1}}


def test_a_fenced_json_block_is_the_answer():
    text = "Here it is:\n```json\n{\"tax\": {\"value\": 1}}\n```\nHope that helps."
    assert answer_from(text) == {"tax": {"value": 1}}


def test_prose_with_no_answer_in_it_is_empty_rather_than_an_error():
    assert answer_from("I think the tax is about four thousand dollars.") == {}


def test_a_dict_passes_through():
    assert answer_from({"tax": {"value": 1}}) == {"tax": {"value": 1}}


def test_an_unparsable_candidate_holds_a_critical_contract(tmp_path):
    report = validate_output("sorry, no idea", CONTRACT, AUTHORITIES,
                             ledger=tmp_path / "v.jsonl")
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert report["release"] == HOLD


# --- the ledger ------------------------------------------------------------

def test_a_check_lands_in_the_ledger_with_its_scope_and_subject(tmp_path):
    path = tmp_path / "v.jsonl"
    validate_output("", CONTRACT, AUTHORITIES, scope=TASK, subject="t-1",
                    ledger=path)
    (entry,) = read_ledger(path)
    assert entry["scope"] == TASK
    assert entry["subject"] == "t-1"
    assert entry["blocking"] == ["tax"]


def test_a_ledger_entry_never_carries_the_authoritative_value(tmp_path):
    """The same rule feedback follows. A summary is not an answer key."""
    path = tmp_path / "v.jsonl"
    validate_output(json.dumps({"tax": {"value": 4165.5, "source": "table:2026"}}),
                    CONTRACT, AUTHORITIES, ledger=path)
    assert "4169" not in path.read_text(encoding="utf-8")


def test_a_dry_run_writes_nothing(tmp_path):
    path = tmp_path / "v.jsonl"
    validate_output("", CONTRACT, AUTHORITIES, ledger=path, write=False)
    assert not path.exists()


def test_reading_narrows_by_scope_and_subject(tmp_path):
    path = tmp_path / "v.jsonl"
    for scope, subject in ((TASK, "t-1"), (TASK, "t-2"), (GOAL, "g-1")):
        validate_output("", CONTRACT, AUTHORITIES, scope=scope,
                        subject=subject, ledger=path)
    assert len(read_ledger(path)) == 3
    assert len(read_ledger(path, scope=TASK)) == 2
    assert [e["subject"] for e in read_ledger(path, subject="g-1")] == ["g-1"]


def test_an_unknown_scope_is_refused(tmp_path):
    with pytest.raises(LookupError):
        record({}, scope="quarter", path=tmp_path / "v.jsonl")


def test_a_torn_line_is_skipped_rather_than_stopping_the_summary(tmp_path):
    path = tmp_path / "v.jsonl"
    validate_output("", CONTRACT, AUTHORITIES, ledger=path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"scope": "task", "verdi\n')
    assert len(read_ledger(path)) == 1


def test_a_missing_ledger_reads_as_empty(tmp_path):
    assert read_ledger(tmp_path / "nothing-here.jsonl") == []


def test_flywheel_home_decides_where_the_ledger_lives(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    assert ledger_path() == tmp_path / "validation.jsonl"


# --- the roll-up -----------------------------------------------------------

def test_a_session_that_held_once_does_not_roll_up_clean(tmp_path):
    """Worst, not latest. A clean last check is how a bad session disappears."""
    path = tmp_path / "v.jsonl"
    validate_output("", CONTRACT, AUTHORITIES, scope=SESSION, ledger=path)
    validate_output(json.dumps({"tax": {"value": 4169.0, "source": "table:2026"}}),
                    CONTRACT, AUTHORITIES, scope=SESSION, ledger=path)
    summary = roll_up(read_ledger(path))
    assert summary["entries"] == 2
    assert summary["verdict"] == Verdict.UNVERIFIABLE.value
    assert summary["release"] == HOLD
    assert summary["held"] == 1
    assert summary["critical_unresolved"] == ["tax"]


def test_a_clean_run_of_entries_rolls_up_to_release(tmp_path):
    path = tmp_path / "v.jsonl"
    good = json.dumps({"tax": {"value": 4169.0, "source": "table:2026"}})
    validate_output(good, CONTRACT, AUTHORITIES, ledger=path)
    summary = roll_up(read_ledger(path))
    assert summary["verdict"] == Verdict.PASS.value
    assert summary["release"] == RELEASE
    assert summary["blocking"] == []


def test_an_empty_ledger_rolls_up_to_nothing_rather_than_to_pass():
    summary = roll_up([])
    assert summary["entries"] == 0
    assert summary["verdict"] == ""
    assert summary["release"] == ""


def test_outstanding_names_what_held_and_which_fields(tmp_path):
    path = tmp_path / "v.jsonl"
    validate_output("", CONTRACT, AUTHORITIES, subject="t-9", ledger=path)
    (held,) = outstanding(read_ledger(path))
    assert held["subject"] == "t-9"
    assert held["blocking"] == ["tax"]


def test_a_caveat_is_not_a_hold(tmp_path):
    path = tmp_path / "v.jsonl"
    contract = new_contract([{"name": "tax", "authority": RECOMPUTE,
                              "source": "table:2026"}])
    validate_output(json.dumps({"tax": {"value": 4169.0, "source": "elsewhere"}}),
                    contract, AUTHORITIES, ledger=path)
    summary = roll_up(read_ledger(path))
    assert summary["release"] == RELEASE_WITH_CAVEAT
    assert summary["held"] == 0
    assert outstanding(read_ledger(path)) == []


# --- the chain payload -----------------------------------------------------

def test_the_chain_payload_records_codes_and_not_prose():
    report = validate_output("", CONTRACT, AUTHORITIES, write=False)
    payload = stage_payload(report)
    assert payload["codes"] == {"tax": "FIELD_ABSENT"}
    assert "reason" not in json.dumps(payload)


def test_a_passing_report_records_no_codes():
    good = json.dumps({"tax": {"value": 4169.0, "source": "table:2026"}})
    payload = stage_payload(validate_output(good, CONTRACT, AUTHORITIES,
                                            write=False))
    assert payload["codes"] == {}
    assert payload["passed"] == 1


# --- the loop --------------------------------------------------------------

def test_a_candidate_its_oracle_passes_is_not_accepted_when_it_holds(
        tmp_path, monkeypatch):
    """The failure the oracle was never asked about.

    The tests are green. The witness matches. The answer charges $4,165.50
    where the table charges $4,169, and before this wiring that was an accepted
    run with a receipt on it.
    """
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    task = load_task(TASK_DIR, workdir=tmp_path / "ws")
    task.task_id = "held"
    result = run_loop(task, StubProposer(CORRECT), PytestOracle(),
                      envelopes_dir=tmp_path / "env",
                      output_contract=CONTRACT,
                      output_authorities=AUTHORITIES,
                      output_extract=_answer(4165.5))
    assert result.oracle.verdict() == "PASS"
    assert result.witness.verdict == "MATCH"
    assert result.accepted is False
    assert result.output["release"] == HOLD
    assert not list((tmp_path / "env").glob("held-*.json"))


def test_an_agreeing_answer_leaves_acceptance_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    task = load_task(TASK_DIR, workdir=tmp_path / "ws2")
    task.task_id = "clean"
    result = run_loop(task, StubProposer(CORRECT), PytestOracle(),
                      envelopes_dir=tmp_path / "env",
                      output_contract=CONTRACT,
                      output_authorities=AUTHORITIES,
                      output_extract=_answer(4169.0))
    assert result.accepted is True
    assert result.output["release"] == RELEASE


def test_the_loop_writes_its_check_to_the_ledger_under_the_task_id(
        tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    task = load_task(TASK_DIR, workdir=tmp_path / "ws3")
    task.task_id = "ledgered"
    run_loop(task, StubProposer(CORRECT), PytestOracle(),
             envelopes_dir=tmp_path / "env", output_contract=CONTRACT,
             output_authorities=AUTHORITIES, output_extract=_answer(4165.5))
    (entry,) = read_ledger(scope=TASK)
    assert entry["subject"] == "ledgered"
    assert entry["release"] == HOLD


def test_the_output_stage_is_in_the_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    task = load_task(TASK_DIR, workdir=tmp_path / "ws4")
    task.task_id = "chained"
    result = run_loop(task, StubProposer(CORRECT), PytestOracle(),
                      envelopes_dir=tmp_path / "env", output_contract=CONTRACT,
                      output_authorities=AUTHORITIES,
                      output_extract=_answer(4169.0))
    stages = [s["stage"] for s in result.envelope.chain]
    assert "output" in stages
    stage = result.envelope.chain[stages.index("output")]
    assert stage["verdict"] == RELEASE


def test_a_loop_with_no_contract_runs_exactly_as_before(tmp_path, monkeypatch):
    """The wiring is opt-in. A lane that declares nothing is untouched."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    task = load_task(TASK_DIR, workdir=tmp_path / "ws5")
    task.task_id = "plain"
    result = run_loop(task, StubProposer(CORRECT), PytestOracle(),
                      envelopes_dir=tmp_path / "env")
    assert result.accepted is True
    assert result.output is None
    assert "output" not in [s["stage"] for s in result.envelope.chain]
    assert read_ledger() == []


def test_holds_reads_the_release_and_not_the_verdict():
    assert holds({"release": HOLD}) is True
    assert holds({"release": RELEASE_WITH_CAVEAT}) is False
    assert holds({}) is False
