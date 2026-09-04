"""Falsifiers for turning a declared authority into one that runs.

The declaration is the part a task ships, so these check the two directions it
can go wrong. A declaration that cannot work must fail where its author will
see it, and an authority that fails at the moment it runs must leave the field
unchecked rather than passed, without taking the other fields down with it.

The command checker here is a real separate process. Faking the subprocess
would test the fake, and independence from the producer is the entire reason a
command authority exists.
"""
import json
import sys
from pathlib import Path

import pytest

from harness.authority_registry import (COMMAND, AuthorityError,
                                        build_authorities)
from harness.output_contract import (AUTHORITY_UNAVAILABLE, DISAGREES,
                                     OUT_OF_RANGE, TABLE, check_answer,
                                     new_contract)
from harness.verdict import Verdict

FIXTURE = Path(__file__).resolve().parent / "tax_authority_fixture.py"
SOURCE = "irs-2025-tax-table-single"
CONTRACT = new_contract([{"name": "tax", "authority": TABLE, "source": SOURCE}])
FROM_THE_TABLE = 4169
FROM_THE_SCHEDULE = 4165.50

TAX_COMMAND = {"kind": COMMAND, "argv": [sys.executable, str(FIXTURE)]}


def answer(value, income=36700):
    return {"taxable_income": {"value": income, "source": "the return"},
            "tax": {"value": value, "source": SOURCE}}


def run(value, declaration=None, income=36700, **build):
    authorities = build_authorities({SOURCE: declaration or TAX_COMMAND}, **build)
    return check_answer(answer(value, income), CONTRACT, authorities)


def only(report):
    return report["fields"][0]


def test_a_command_authority_that_is_not_granted_leaves_the_field_unchecked():
    """The safe direction. A check nobody was allowed to run must never read as
    a check that passed, and it must not read as a wrong answer either."""
    report = run(FROM_THE_SCHEDULE)
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert only(report)["code"] == AUTHORITY_UNAVAILABLE
    assert "not granted" in only(report)["reason"]


def test_a_granted_command_authority_decides_the_field():
    assert run(FROM_THE_TABLE, allow_commands=True)["verdict"] == Verdict.PASS.value
    wrong = run(FROM_THE_SCHEDULE, allow_commands=True)
    assert wrong["verdict"] == Verdict.FAIL.value
    assert only(wrong)["code"] == DISAGREES


def test_a_checker_that_declines_is_out_of_range_and_not_a_crash():
    """Exit 3 is the difference between `I do not cover this` and `I broke`.
    Merging them would let a contract publish a guess."""
    report = run(9999, income=60000, allow_commands=True)
    assert only(report)["code"] == OUT_OF_RANGE
    assert "48,475" in only(report)["reason"]


def test_a_checker_that_breaks_is_unchecked_rather_than_failed(tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("import sys\nsys.exit(9)\n", encoding="utf-8")
    report = run(FROM_THE_TABLE, {"kind": COMMAND, "argv": [sys.executable, str(broken)]},
                 allow_commands=True)
    assert report["verdict"] == Verdict.UNVERIFIABLE.value
    assert only(report)["code"] == AUTHORITY_UNAVAILABLE
    assert "exit 9" in only(report)["reason"]


def test_a_checker_that_prints_nothing_usable_is_unchecked_rather_than_passed(tmp_path):
    """Empty stdout parses as nothing, and nothing is not agreement."""
    mute = tmp_path / "mute.py"
    mute.write_text("pass\n", encoding="utf-8")
    report = run(FROM_THE_TABLE, {"kind": COMMAND, "argv": [sys.executable, str(mute)]},
                 allow_commands=True)
    assert only(report)["code"] == AUTHORITY_UNAVAILABLE


def test_a_checker_that_hangs_is_unchecked_rather_than_passed(tmp_path):
    slow = tmp_path / "slow.py"
    slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    report = run(FROM_THE_TABLE, {"kind": COMMAND, "argv": [sys.executable, str(slow)]},
                 allow_commands=True, timeout=0.5)
    assert only(report)["code"] == AUTHORITY_UNAVAILABLE
    assert "Timeout" in only(report)["reason"]


def test_the_answer_reaches_the_checker_on_stdin_and_never_through_argv(tmp_path):
    """Arguments are readable by every process on the machine. The answer is
    the caller's data and does not belong there."""
    seen = tmp_path / "argv.json"
    spy = tmp_path / "spy.py"
    spy.write_text(
        "import json, sys\n"
        f"open({str(seen)!r}, 'w').write(json.dumps(sys.argv))\n"
        "body = sys.stdin.read()\n"
        "print(json.dumps({'value': json.loads(body)['tax']['value']}))\n",
        encoding="utf-8")
    report = run(FROM_THE_TABLE, {"kind": COMMAND, "argv": [sys.executable, str(spy)]},
                 allow_commands=True)
    assert report["verdict"] == Verdict.PASS.value  # it read the answer on stdin
    assert "36700" not in seen.read_text(encoding="utf-8")


def test_a_table_authority_reads_the_file_that_shipped_with_the_task(tmp_path):
    (tmp_path / "rows.json").write_text(json.dumps({"36700": FROM_THE_TABLE}),
                                        encoding="utf-8")
    declaration = {"kind": "table", "path": "rows.json", "key_field": "taxable_income"}
    assert run(FROM_THE_TABLE, declaration, base_dir=tmp_path)["verdict"] == Verdict.PASS.value


def test_a_key_the_table_does_not_list_is_declined_rather_than_guessed(tmp_path):
    (tmp_path / "rows.json").write_text(json.dumps({"36700": FROM_THE_TABLE}),
                                        encoding="utf-8")
    declaration = {"kind": "table", "path": "rows.json", "key_field": "taxable_income"}
    report = run(1, declaration, income=99, base_dir=tmp_path)
    assert only(report)["code"] == OUT_OF_RANGE


def test_a_table_file_that_is_not_there_is_one_unchecked_field(tmp_path):
    """Read on first use rather than at build, so a bad path costs one field
    instead of discarding every other verdict in the run."""
    declaration = {"kind": "table", "path": "gone.json", "key_field": "taxable_income"}
    report = run(FROM_THE_TABLE, declaration, base_dir=tmp_path)
    assert only(report)["code"] == AUTHORITY_UNAVAILABLE
    assert "gone.json" in only(report)["reason"]


def test_one_broken_authority_does_not_discard_the_other_fields(tmp_path):
    contract = new_contract([
        {"name": "tax", "authority": TABLE, "source": SOURCE},
        {"name": "total", "authority": TABLE, "source": "missing-table"},
    ])
    authorities = build_authorities(
        {SOURCE: TAX_COMMAND,
         "missing-table": {"kind": "table", "path": "gone.json", "key_field": "tax"}},
        allow_commands=True, base_dir=tmp_path)
    stated = answer(FROM_THE_SCHEDULE)
    stated["total"] = {"value": 1, "source": "missing-table"}
    report = check_answer(stated, contract, authorities)
    codes = {row["field"]: row["code"] for row in report["fields"]}
    assert codes == {"tax": DISAGREES, "total": AUTHORITY_UNAVAILABLE}
    assert report["verdict"] == Verdict.FAIL.value  # the worst field still decides


def test_a_declaration_that_could_never_work_is_refused_where_its_author_sees_it():
    """Structure fails loudly. A misspelled kind that degraded to `unchecked`
    would let a contract quietly stop checking anything."""
    for declaration, match in (
        ({"kind": "vibes"}, "unknown kind"),
        ({"kind": COMMAND}, "needs argv"),
        ({"kind": "table", "path": "rows.json"}, "needs key_field"),
        ("not an object", "must be an object"),
    ):
        with pytest.raises(AuthorityError, match=match):
            build_authorities({SOURCE: declaration})


def test_a_contract_with_no_authorities_is_refused():
    with pytest.raises(AuthorityError, match="checks nothing"):
        build_authorities({})
