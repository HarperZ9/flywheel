"""The shell surface: what a caller who reads only the exit code learns.

The exit code is the part that gets wired into a build, so it carries the same
distinction the standings do. 0 means the goal is established. 1 means something
under it was refused. 2 means nothing decided it yet, which a build must not
read as success, and which is also what a malformed declaration returns.
"""
import json

import pytest

from harness import cli_entry
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
    assert receipt["run"]["registered_kinds"] == ["arithmetic", "dimensional", "lean"]


def test_the_command_is_reachable_from_the_flywheel_entry_point():
    assert cli_entry._PACKAGED["workstream"] == "harness.workstream_cli"
