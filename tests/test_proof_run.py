"""Falsifiers for handing the emitted file to Lean and reading what it said.

The direction that matters is which way an unknown falls. A kernel that did not
run, timed out, or printed nothing has not agreed with anything, and reporting
that as a pass would make the whole artifact decorative. So every path that
does not end in a closed obligation ends in UNVERIFIABLE or FAIL, never PASS.

The Lean-dependent tests run only where Lean is installed. Skipping them is the
honest null: it says the emitter was not checked against a kernel on this
machine, rather than asserting something weaker and calling it green.
"""
import shutil

import pytest

from harness.contract_terms import TABLE
from harness.proof_lean import lean_source
from harness.proof_run import diagnostics, lean_path, prove, read_result, run_proof
from harness.verdict import Verdict

NAME = "'Flywheel.Answer.confirmed'"
CLEAN = NAME + " depends on axioms: [Decided, tax_decided]\n"
NOTHING = NAME + " does not depend on any axioms\n"
REFUSED = (r"C:\somewhere\deep\Answer.lean:35:80: error: Tactic `decide` proved "
           "that the proposition\n  tax_source = \"the-table\"\nis false\n"
           + NAME + " depends on axioms: [sorryAx]\n")

ANSWER = {"tax": {"value": 4169, "source": "the-table", "method": "table"}}
ROWS = [{"field": "tax", "authority": TABLE, "source": "the-table",
         "verdict": Verdict.PASS.value, "code": "AGREES", "reason": "",
         "criticality": "critical"}]
REPORT = {"verdict": Verdict.PASS.value, "release": "RELEASE", "blocking": [],
          "checked": 1, "passed": 1, "fields": ROWS}
needs_lean = pytest.mark.skipif(shutil.which("lean") is None,
                                reason="lean is not installed on this machine")


# --- reading Lean's own output ----------------------------------------------

def test_a_closed_file_reports_the_axioms_it_rests_on():
    result = read_result(CLEAN, 0)
    assert result["verdict"] == Verdict.PASS.value
    assert result["axioms"] == ["Decided", "tax_decided"]


def test_a_file_resting_on_nothing_is_the_strongest_result_not_a_missing_one():
    result = read_result(NOTHING, 0)
    assert result["verdict"] == Verdict.PASS.value
    assert result["axioms"] == []


def test_a_refused_obligation_is_a_disagreement_not_an_error_to_swallow():
    result = read_result(REFUSED, 1)
    assert result["verdict"] == Verdict.FAIL.value
    assert "35:80" in result["reason"]


def test_sorry_alone_is_enough_to_refuse_even_on_a_zero_exit():
    """`sorryAx` reaches the axiom list through the same channel a real
    assumption does, which is why the list is what gets read."""
    result = read_result(NAME + " depends on axioms: [sorryAx]\n", 0)
    assert result["verdict"] == Verdict.FAIL.value


def test_a_non_zero_exit_with_nothing_said_about_the_file_is_unverified():
    assert read_result("", 2)["verdict"] == Verdict.UNVERIFIABLE.value


def test_output_with_no_axiom_line_is_unverified_rather_than_passed():
    assert read_result("Lean says something else.\n", 0)["verdict"] == \
        Verdict.UNVERIFIABLE.value


# --- what a diagnostic is allowed to carry ----------------------------------

def test_the_directory_a_proof_was_checked_in_never_reaches_the_report():
    """A report can be written to a file that leaves this machine, and the
    path is not a fact about the answer."""
    (line,) = diagnostics(REFUSED)
    assert line.startswith("Answer.lean:35:80:")
    assert "somewhere" not in line


def test_a_posix_directory_is_taken_off_as_well_as_a_windows_one():
    """Which separator a path carries is a fact about the machine that ran
    Lean, and the report is read somewhere else."""
    posix = REFUSED.replace(chr(92).join(["C:", "somewhere", "deep", ""]),
                            "/somewhere/deep/")
    (line,) = diagnostics(posix)
    assert line.startswith("Answer.lean:35:80:")
    assert "somewhere" not in line


def test_the_proposition_that_failed_survives_its_own_line_wrapping():
    (line,) = diagnostics(REFUSED)
    assert 'tax_source = "the-table" is false' in line


def test_the_axiom_report_is_not_swallowed_into_the_error_message():
    (line,) = diagnostics(REFUSED)
    assert "depends on axioms" not in line


def test_a_warning_is_not_reported_as_an_error():
    warning = "Answer.lean:1:0: warning: unused variable\n" + NOTHING
    assert diagnostics(warning) == []
    assert read_result(warning, 0)["verdict"] == Verdict.PASS.value


# --- never guessing at a checker --------------------------------------------

def test_an_explicit_path_that_is_not_there_resolves_to_no_checker(tmp_path):
    assert lean_path(str(tmp_path / "lean.exe")) is None


def test_a_missing_checker_leaves_the_run_unverified_not_passing(tmp_path):
    result = run_proof(tmp_path / "Answer.lean", lean=str(tmp_path / "nope.exe"))
    assert result["verdict"] == Verdict.UNVERIFIABLE.value
    assert "not on PATH" in result["reason"]


def test_the_file_is_written_even_when_no_checker_reads_it(tmp_path):
    """A caller that asked for a proof and got a refusal wants the file that
    was refused, not only a sentence about it."""
    path = tmp_path / "Answer.lean"
    result = prove("-- nothing\n", path, lean=str(tmp_path / "nope.exe"))
    assert path.read_text(encoding="utf-8") == "-- nothing\n"
    assert result["file"] == str(path)


# --- against a real kernel --------------------------------------------------

@needs_lean
def test_the_emitted_file_closes_against_the_kernel(tmp_path):
    body = lean_source(REPORT, ANSWER,
                       [{"name": "tax", "authority": TABLE, "method": "table",
                         "source": "the-table"}],
                       relations=["0 <= tax"])
    result = prove(body, tmp_path / "Good.lean")
    assert result["verdict"] == Verdict.PASS.value, result["reason"]
    assert result["axioms"] == ["Decided", "tax_decided"]


@needs_lean
def test_the_kernel_refuses_a_source_the_answer_only_asserts(tmp_path):
    """The contract requires one source and the answer states another. Both
    are literals in the file, and they came from two different documents."""
    answer = {"tax": dict(ANSWER["tax"], source="a-schedule-nobody-asked-for")}
    body = lean_source(REPORT, answer,
                       [{"name": "tax", "authority": TABLE,
                         "source": "the-table"}])
    result = prove(body, tmp_path / "Bad.lean")
    assert result["verdict"] == Verdict.FAIL.value
    # The other axioms are the assumptions the file declared on purpose. What
    # makes this a refusal is that `sorryAx` joined them.
    assert "sorryAx" in result["axioms"]


@needs_lean
def test_an_answer_with_nothing_to_prove_rests_on_no_axioms(tmp_path):
    body = lean_source({"verdict": Verdict.PASS.value, "release": "RELEASE",
                        "blocking": [], "checked": 0, "passed": 0,
                        "fields": []}, {})
    result = prove(body, tmp_path / "Empty.lean")
    assert result["verdict"] == Verdict.PASS.value
    assert result["axioms"] == []
