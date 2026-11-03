"""One verifier rechecks receipts from gather, crucible and emet.

The fixtures in tests/fixtures/spine were emitted by each tool's own code at a
pinned commit (SOURCE.txt there), not written by hand. The spine's checkers
were written from the tools' published formats. Agreement between the two is
the test: if a recipe here drifted from the tool, these fixtures would fail.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.spine import from_native, link, verify_chain, verify_record
from harness.spine import natives
from harness.spine.record import seal
from harness.verdict import Verdict

FIXTURES = Path(__file__).parent / "fixtures" / "spine"
CASES = [
    ("emet-receipt-match.json", natives.EMET, "MATCH", "PASS"),
    ("emet-receipt-drift.json", natives.EMET, "DRIFT", "FAIL"),
    ("crucible-assessment-warn.json", natives.CRUCIBLE, "warn", "UNDECIDED"),
    ("crucible-assessment-drift.json", natives.CRUCIBLE, "fail", "FAIL"),
    ("gather-digest.json", natives.GATHER, "MATCH", "PASS"),
]


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _names(result, verdict):
    return [n for n, v, _ in result.checks if v is verdict]


@pytest.mark.parametrize("name,schema,term,spine", CASES)
def test_each_tool_receipt_rechecks_in_spine_form(name, schema, term, spine):
    record = from_native(schema, _load(name))
    assert (record["source_verdict"], record["verdict"]) == (term, spine)
    result = verify_record(record)
    assert result.verdict is Verdict.PASS, result.checks
    assert result.record_verdict == spine
    assert "native" in _names(result, Verdict.PASS)


def test_a_record_that_honestly_carries_drift_rechecks_as_pass():
    """The recheck verdict and the record verdict answer different questions."""
    result = verify_record(from_native(natives.EMET, _load("emet-receipt-drift.json")))
    assert (result.verdict, result.record_verdict) == (Verdict.PASS, "FAIL")


def test_all_three_tools_chain_and_verify_together():
    records = link([from_native(s, _load(n)) for n, s, _, _ in CASES])
    assert records[1]["prev_sha256"] == records[0]["record_sha256"]
    assert verify_chain(records).verdict is Verdict.PASS


def _tamper(record, edit):
    bad = copy.deepcopy(record)
    edit(bad)
    return seal({k: v for k, v in bad.items() if k != "record_sha256"})


def test_an_edited_spine_field_breaks_the_seal():
    record = from_native(natives.GATHER, _load("gather-digest.json"))
    record["scope"] = "covers everything"
    result = verify_record(record)
    assert result.verdict is Verdict.FAIL and "seal" in _names(result, Verdict.FAIL)


def test_a_resealed_verdict_that_contradicts_its_source_term_fails():
    record = from_native(natives.EMET, _load("emet-receipt-drift.json"))
    forged = _tamper(record, lambda r: r.update(verdict="PASS"))
    assert "vocabulary" in _names(verify_record(forged), Verdict.FAIL)


def test_a_resealed_source_term_the_payload_does_not_yield_fails():
    """Both spine fields rewritten together and resealed: only the native
    recheck can catch it, because the payload still says DRIFT."""
    record = from_native(natives.EMET, _load("emet-receipt-drift.json"))
    forged = _tamper(record, lambda r: r.update(source_verdict="MATCH", verdict="PASS"))
    result = verify_record(forged)
    assert result.verdict is Verdict.FAIL and "native" in _names(result, Verdict.FAIL)


@pytest.mark.parametrize("name,schema,edit", [
    ("emet-receipt-match.json", natives.EMET,
     lambda p: p["verdict_record"][0].update(verdict="DRIFT")),
    ("crucible-assessment-warn.json", natives.CRUCIBLE,
     lambda p: p["verdicts"][0].update(deviation=0.5)),
    ("gather-digest.json", natives.GATHER,
     lambda p: p["receipts"][0].update(title="Something else")),
])
def test_an_edited_payload_resealed_with_its_digest_still_fails_natively(name, schema, edit):
    record = from_native(schema, _load(name))

    def rewrite(r):
        edit(r["payload"])
        from harness.spine.record import digest
        r["payload_sha256"] = digest(r["payload"])
    result = verify_record(_tamper(record, rewrite))
    assert result.verdict is Verdict.FAIL and "native" in _names(result, Verdict.FAIL)


def test_a_crucible_status_that_does_not_follow_from_its_deviation_fails():
    a = _load("crucible-assessment-drift.json")
    assert natives.check_crucible(a)[0] is True
    a["verdicts"][0]["status"] = "MATCH"   # deviation 0.09 > tolerance 0.05
    assert natives.check_crucible(a)[0] is False


def test_a_record_without_its_payload_is_unverifiable_not_a_pass():
    record = from_native(natives.GATHER, _load("gather-digest.json"), embed=False)
    result = verify_record(record)
    assert result.verdict is Verdict.UNVERIFIABLE


def test_a_signed_emet_receipt_with_no_key_is_unverifiable():
    receipt = _load("emet-receipt-match.json")
    receipt["signature"] = "0" * 64
    assert natives.check_emet(receipt)[0] is None


def test_the_cli_exit_code_carries_the_recheck_verdict(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(from_native(natives.EMET, _load("emet-receipt-match.json"))),
                    encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "harness.spine", "verify", str(good)],
                         capture_output=True, text=True, cwd=Path(__file__).parent.parent)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["verdict"] == "PASS"
