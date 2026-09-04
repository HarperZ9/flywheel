"""Falsifiers for the command a harness calls before an answer reaches a reader.

A harness branches on the exit code, so the exit code is the interface and it
gets tested as one. The three outcomes have to stay distinguishable from each
other and from the code argparse already uses, because a harness that read a
mistyped flag as an unverified answer would retry until it ran out of money.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.output_check_cli import check, main, render

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "tax_authority_fixture.py"
CLI = ROOT / "scripts" / "run_output_check.py"
SOURCE = "irs-2025-tax-table-single"
FROM_THE_TABLE = 4169
FROM_THE_SCHEDULE = 4165.50

CONTRACT = {"fields": [{"name": "tax", "authority": "TABLE", "source": SOURCE,
                        "describes": "Form 1040 line 16"}],
            "authorities": {SOURCE: {"kind": "command",
                                     "argv": [sys.executable, str(FIXTURE)]}}}


def written(tmp_path, value, contract=None):
    (tmp_path / "contract.json").write_text(json.dumps(contract or CONTRACT),
                                            encoding="utf-8")
    (tmp_path / "answer.json").write_text(json.dumps(
        {"taxable_income": {"value": 36700, "source": "the return"},
         "tax": {"value": value, "source": SOURCE}}), encoding="utf-8")
    return tmp_path / "contract.json", tmp_path / "answer.json"


def cli(tmp_path, value, *extra, contract=None):
    contract_path, answer_path = written(tmp_path, value, contract)
    done = subprocess.run([sys.executable, str(CLI), "--contract", str(contract_path),
                           "--answer", str(answer_path), *extra],
                          capture_output=True, text=True, cwd=ROOT, check=False)
    return done


def test_an_answer_that_agrees_with_the_authority_exits_clean(tmp_path):
    done = cli(tmp_path, FROM_THE_TABLE, "--allow-commands")
    assert done.returncode == 0
    assert "PASS" in done.stdout


def test_the_published_demo_answer_exits_one(tmp_path):
    """$4,165.50 is what the rate schedule gives. The form requires the table."""
    done = cli(tmp_path, FROM_THE_SCHEDULE, "--allow-commands")
    assert done.returncode == 1
    assert "disagrees" in done.stdout


def test_an_answer_nothing_was_allowed_to_check_exits_three(tmp_path):
    """Not zero, because nothing confirmed it. Not one, because nothing
    contradicted it either."""
    done = cli(tmp_path, FROM_THE_TABLE)
    assert done.returncode == 3
    assert "UNVERIFIABLE" in done.stdout


def test_a_mistyped_flag_is_not_mistaken_for_an_unverified_answer(tmp_path):
    """Argparse owns exit 2, which is why the unverified code is 3. A harness
    that retried on a usage error would loop until the budget ran out.

    This caught something worse than an exit code. Argparse accepts any
    unambiguous prefix by default, so `--allow-command` was granting command
    execution and exiting zero. A near-miss of a flag that hands out a
    capability has to be a usage error, so abbreviation is off.
    """
    done = cli(tmp_path, FROM_THE_TABLE, "--allow-command")
    assert done.returncode == 2
    assert done.returncode not in (0, 1, 3)


def test_no_abbreviation_can_hand_out_the_execution_grant(tmp_path):
    """Every prefix of the flag, not just the one that happened to be typed."""
    for near_miss in ("--allow", "--allow-", "--allow-comm", "--allow-command"):
        done = cli(tmp_path, FROM_THE_TABLE, near_miss)
        assert done.returncode == 2, near_miss
        assert "PASS" not in done.stdout


def test_the_written_report_never_carries_the_value_that_would_pass(tmp_path):
    contract_path, answer_path = written(tmp_path, FROM_THE_SCHEDULE)
    out = tmp_path / "report.json"
    code = main(["--contract", str(contract_path), "--answer", str(answer_path),
                 "--allow-commands", "--out", str(out)])
    assert code == 1
    text = out.read_text(encoding="utf-8")
    assert "4169" not in text
    assert json.loads(text)["next"]["fields"][0]["source"] == SOURCE


def test_a_relative_authority_path_resolves_beside_the_contract(tmp_path):
    """A task and its checkers travel together, so the contract's own directory
    is the anchor rather than wherever the command happened to be run."""
    (tmp_path / "rows.json").write_text(json.dumps({"36700": FROM_THE_TABLE}),
                                        encoding="utf-8")
    contract = {"fields": CONTRACT["fields"],
                "authorities": {SOURCE: {"kind": "table", "path": "rows.json",
                                         "key_field": "taxable_income"}}}
    assert cli(tmp_path, FROM_THE_TABLE, contract=contract).returncode == 0


def test_the_failing_field_is_printed_before_the_ones_that_passed():
    """A reader who stops after one line should stop on the field that decided
    the run."""
    contract = {"fields": [{"name": "ok", "authority": "CITED", "source": "a"},
                           {"name": "tax", "authority": "TABLE", "source": "b"}],
                "authorities": {"a": {"kind": "citation"},
                                "b": {"kind": "table", "path": "rows.json",
                                      "key_field": "tax"}}}
    report = check(contract, {"ok": {"value": 1, "source": "a"},
                              "tax": {"value": 1, "source": "b"}},
                   base_dir=".", allow_commands=False)
    lines = render(report).splitlines()
    # Line 0 is the verdict, line 1 the release decision, then the
    # fields worst first.
    assert lines[1].startswith("RELEASE_WITH_CAVEAT")
    assert lines[2].strip().startswith("UNVERIFIABLE")
    assert "PASS" in lines[3]


def test_a_contract_that_requires_nothing_is_refused_rather_than_passing(tmp_path):
    """An empty contract would exit zero on any answer at all."""
    with pytest.raises(ValueError, match="accepts everything"):
        check({"fields": [], "authorities": {"a": {"kind": "citation"}}}, {},
              base_dir=tmp_path, allow_commands=False)


def test_the_shipped_example_still_produces_the_three_outcomes_it_documents():
    """The example directory is the thing a reader runs first, so a change that
    quietly alters what it prints is a defect in the documentation as much as in
    the code. Every exit code in its README is asserted here."""
    example = ROOT / "examples" / "output-validation"
    contract = example / "form-1040.contract.json"

    def run(answer_name, *extra):
        return subprocess.run(
            [sys.executable, str(CLI), "--contract", str(contract),
             "--answer", str(example / answer_name), *extra],
            capture_output=True, text=True, cwd=example, check=False)

    as_filed = run("answer-as-filed.json", "--allow-commands")
    assert as_filed.returncode == 1
    assert "4169" not in as_filed.stdout  # the report never hands over the value

    assert run("answer-from-the-table.json", "--allow-commands").returncode == 0
    assert run("answer-from-the-table.json").returncode == 3
