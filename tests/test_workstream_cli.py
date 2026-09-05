"""The shell surface: what a caller who reads only the exit code learns.

The exit code is the part that gets wired into a build, so it carries the same
distinction the standings do. 0 means the goal is established. 1 means something
under it was refused. 2 means nothing decided it yet, which a build must not
read as success, and which is also what a malformed declaration returns.
"""
import json
from pathlib import Path

import pytest

from harness import cli_entry
from harness.workstream import Obligation
from harness.workstream_audit import statement_digest
from harness.workstream_cli import EXAMPLE, main


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def _run(capsys, *args):
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_example_it_prints_is_a_declaration_it_can_run(tmp_path, capsys):
    code, out, _ = _run(capsys, "example")
    assert code == 0
    path = tmp_path / "example.json"
    path.write_text(out, encoding="utf-8")
    code, rendered, _ = _run(capsys, "run", str(path))
    assert code == 0
    assert "goal label is VERIFIED" in rendered
    assert "carried, not checked:" in rendered and "statute" in rendered


def test_a_refuted_obligation_exits_one_and_says_which(tmp_path, capsys):
    document = json.loads(json.dumps(EXAMPLE))
    for entry in document["obligations"]:
        if entry["id"] == "conversion":
            entry["statement"] = json.dumps(
                {"value": 500, "from": "mg", "to": "g", "expected": 5})
    code, out, _ = _run(capsys, "run", _write(tmp_path / "bad.json", document))
    assert code == 1
    assert "goal label is BLOCKED" in out
    assert "refuted" in out and "conversion" in out
    # The assay above the bad conversion was never handed to a checker.
    assert "checked 1, skipped 2" in out


def test_an_unfinished_stack_exits_two_rather_than_zero(tmp_path, capsys):
    document = {"goal": "top", "obligations": [
        {"id": "base", "check": "citation", "environment": "e",
         "statement": "a source nothing here can read"},
        {"id": "top", "check": "citation", "environment": "e",
         "depends_on": ["base"], "statement": "the claim above it"}]}
    code, out, _ = _run(capsys, "run", _write(tmp_path / "open.json", document))
    assert code == 2
    assert "BLOCKED" in out
    assert "no checker is registered" in out


def test_settle_recomposes_results_decided_elsewhere(tmp_path, capsys):
    document = {"goal": "top", "obligations": [
        {"id": "base", "check": "lean", "environment": "lean4:v4.9.0",
         "statement": "theorem base : True := trivial", "result": "PASS"},
        {"id": "top", "check": "lean", "environment": "lean4:v4.9.0",
         "depends_on": ["base"], "statement": "theorem top : True := trivial",
         "result": "PASS"}]}
    path = _write(tmp_path / "farm.json", document)
    code, out, _ = _run(capsys, "settle", path)
    assert code == 0 and "goal top is VERIFIED" in out
    # No checker ran, so there is no run block to report.
    assert "checked" not in out


def test_settle_refuses_a_result_that_is_not_a_verdict(tmp_path, capsys):
    document = {"goal": "a", "obligations": [
        {"id": "a", "check": "lean", "environment": "e",
         "statement": "theorem a : True := trivial", "result": "probably"}]}
    code, _, err = _run(capsys, "settle", _write(tmp_path / "x.json", document))
    assert code == 2 and "must be one of" in err


def test_run_says_it_is_ignoring_results_carried_in_the_declaration(tmp_path, capsys):
    document = json.loads(json.dumps(EXAMPLE))
    document["obligations"][1]["result"] = "PASS"
    code, _, err = _run(capsys, "run", _write(tmp_path / "mixed.json", document))
    assert code == 0
    assert "ignored by run" in err


@pytest.mark.parametrize("document, fragment", [
    ({"obligations": []}, "a goal string and an obligations list"),
    ({"goal": "a", "obligations": [{"id": "a"}]}, "statement must be"),
    ({"goal": "a", "obligations": [
        {"id": "a", "check": "lean", "environment": "e", "statement": "s",
         "depends_on": "b"}]}, "depends_on is a list"),
    ({"goal": "z", "obligations": [
        {"id": "a", "check": "lean", "environment": "e", "statement": "s"}]},
     "is not one of the obligations"),
])
def test_a_malformed_declaration_is_refused_with_the_reason(tmp_path, capsys,
                                                            document, fragment):
    code, _, err = _run(capsys, "run", _write(tmp_path / "bad.json", document))
    assert code == 2 and fragment in err


def test_a_missing_file_is_refused_rather_than_traced(capsys, tmp_path):
    code, _, err = _run(capsys, "run", str(tmp_path / "nothing.json"))
    assert code == 2 and "no declaration at" in err


def test_the_json_form_carries_the_caveat_and_the_identity(tmp_path, capsys):
    path = _write(tmp_path / "e.json", EXAMPLE)
    code, out, _ = _run(capsys, "run", path, "--json")
    receipt = json.loads(out)
    assert code == 0
    assert receipt["schema"] == "flywheel.workstream/v1"
    assert len(receipt["workstream_id"]) == 64
    assert receipt["does_not_prove"]
    assert receipt["run"]["registered_kinds"] == [
        "arithmetic", "dimensional", "instrument", "lean", "readback"]


def test_the_command_is_reachable_from_the_flywheel_entry_point():
    assert cli_entry._PACKAGED["workstream"] == "harness.workstream_cli"


def _audit_declaration(pins):
    """Two obligations, with a reading recorded against whichever ids are given."""
    document = {"goal": "top", "obligations": [
        {"id": "base", "check": "arithmetic", "environment": "e",
         "statement": '{"value": 1, "interval": [0, 2]}'},
        {"id": "top", "check": "arithmetic", "environment": "e",
         "depends_on": ["base"], "statement": '{"value": 1, "interval": [0, 2]}'}]}
    for entry in document["obligations"]:
        pin = pins.get(entry["id"])
        if pin is not None:
            entry["audited"] = pin
    return document


def _pins(document):
    return {entry["id"]: statement_digest(Obligation(
        obligation_id=entry["id"], statement=entry["statement"],
        check=entry["check"], environment=entry["environment"],
        depends_on=tuple(entry.get("depends_on", []))))
        for entry in document["obligations"]}


def test_an_audit_with_every_statement_read_and_current_exits_zero(tmp_path, capsys):
    blank = _audit_declaration({})
    document = _audit_declaration(_pins(blank))
    code, out, _ = _run(capsys, "audit", _write(tmp_path / "read.json", document))
    assert code == 0
    assert "2 read, 0 stale, 0 unread" in out
    assert out.count("audited    ") == 2


def test_a_statement_edited_after_it_was_read_exits_one(tmp_path, capsys):
    # Stale lands with the refusals rather than with unfinished work. Someone
    # read a statement, the statement changed, and the record still carried the
    # earlier reading, which is drift and not a build that has not run yet.
    blank = _audit_declaration({})
    document = _audit_declaration(_pins(blank))
    document["obligations"][1]["statement"] = '{"value": 1, "interval": [0, 3]}'
    code, out, _ = _run(capsys, "audit", _write(tmp_path / "drift.json", document))
    assert code == 1
    assert "stale" in out and "top" in out
    assert "changed after they were read" in out


def test_an_unread_surface_exits_two_rather_than_zero(tmp_path, capsys):
    path = _write(tmp_path / "fresh.json", _audit_declaration({}))
    code, out, _ = _run(capsys, "audit", path)
    assert code == 2
    assert "0 read, 0 stale, 2 unread" in out
    assert "have no recorded reading" in out


def test_the_audit_json_form_carries_the_pin_a_reader_records(tmp_path, capsys):
    path = _write(tmp_path / "fresh.json", _audit_declaration({}))
    code, out, _ = _run(capsys, "audit", path, "--json")
    surface = json.loads(out)
    assert code == 2
    assert surface["schema"] == "flywheel.workstream.audit/v1"
    assert len(surface["surface"]["top"]["statement_digest"]) == 64
    assert surface["surface"]["top"]["reasons"] == ["the goal statement"]
    assert surface["does_not_prove"]


WORKSTREAMS = Path(__file__).resolve().parents[1] / "examples" / "workstreams"
EXAMPLES = sorted(WORKSTREAMS.glob("*.json"))
BY_NAME = {path.stem: path for path in EXAMPLES}
# Driver reference files sit under references/ rather than beside the
# declarations, because a reference is an input to a run and not a thing that
# can be run. Mixing them would put a file with no obligations in every
# parametrization below.
REFERENCES = sorted(str(path) for path in (WORKSTREAMS / "references").glob("*.json"))


def _lean_obligations(path):
    body = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for entry in body["obligations"] if entry["check"] == "lean")


# Running a declaration costs one toolchain invocation per lean obligation on a
# machine that has Lean, and pytest.ini caps a test at 60 s. So the cheap
# examples get run, and every example gets audited, which exercises the same
# parsing and reachability without paying for a proof assistant.
CHEAP = [path for path in EXAMPLES if _lean_obligations(path) <= 3]


def test_there_are_shipped_examples_to_check():
    # Without this, a rename would empty the parametrizations below and the
    # examples would go unchecked while the suite stayed green.
    assert [path.name for path in EXAMPLES] == [
        "formalization.json", "instrument.json", "mission.json"]
    assert [path.name for path in CHEAP] == ["formalization.json", "instrument.json"]


@pytest.mark.parametrize("path", CHEAP, ids=lambda p: p.stem)
def test_a_shipped_example_still_runs(capsys, path):
    code, out, err = _run(capsys, "run", str(path))
    assert not err
    assert "does not prove:" in out
    # 0 established, 2 nothing decided it yet, which is what a machine with no
    # Lean toolchain gets. 1 would mean a shipped example refutes itself.
    assert code in (0, 2)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_a_shipped_example_names_the_reading_it_owes(capsys, path):
    code, out, err = _run(capsys, "audit", str(path))
    assert not err
    assert code == 2  # shipped declarations carry no readings
    assert "obligations to read" in out and "does not prove:" in out


def test_the_instrument_example_needs_the_driver_files_to_settle(capsys):
    # Without a reference the device claims are unchecked, and the example says
    # so rather than passing. This is the whole point of the kind: a stack whose
    # instrument claims are carried is a stack where the device cannot fail.
    code, out, _ = _run(capsys, "run", str(BY_NAME["instrument"]))
    assert code == 2
    assert "goal dose_delivered is BLOCKED" in out
    assert "no driver reference for liquid-handler-2 was supplied" in out


def test_the_instrument_example_settles_against_its_references(capsys):
    flags = [flag for path in REFERENCES for flag in ("--reference", path)]
    code, out, _ = _run(capsys, "run", str(BY_NAME["instrument"]), *flags)
    assert code == 0
    assert "goal dose_delivered is VERIFIED" in out
    assert "checked 4, skipped 0" in out
    assert "dispense on liquid-handler-2 driver 1.4.0" in out
    # Narrower than it sounds, and the receipt keeps saying so.
    assert "not that the device performed the run" in out


def test_the_mission_example_delegates_most_of_its_stack(capsys):
    # The demonstration the audit surface exists for: the stack grows and the
    # reading does not. Eighteen obligations, six of them on the surface.
    code, out, _ = _run(capsys, "audit", str(BY_NAME["mission"]))
    assert code == 2
    assert "6 of 18 obligations to read, 12 delegated" in out
