"""buildc receipt bridge: the scope block and the inconclusive state on a timeout."""
import json

from harness import buildc_receipt_bridge as B
from harness.buildc_receipt_scope import TIMEOUT_EXIT, scope_block


def _receipt(tmp_path, status="PASS"):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"status": status, "source_digest": "ab" * 32}), encoding="utf-8")
    return p


def _run(code):
    return B.CommandResult(["buildc", "receipt", "verify", "r.json"], ".", code, "", "")


def test_no_verification_is_unverifiable_and_lists_only_hashing(tmp_path):
    packet = B.bridge_buildc_receipt(_receipt(tmp_path))
    assert packet["flywheel"]["verdict"] == B.UNVERIFIABLE
    assert packet["scope"]["checked"][0] == "receipt_bytes_hashed"
    assert "buildc_receipt_verify_ran" not in packet["scope"]["checked"]
    assert packet["scope"]["inconclusive"] is False
    assert packet["verification"]["budget_exhausted"] is False


def test_passing_verify_is_match_and_says_so(tmp_path):
    packet = B.bridge_buildc_receipt(_receipt(tmp_path), command_result=_run(0))
    assert packet["flywheel"]["verdict"] == B.MATCH
    assert {"buildc_receipt_verify_ran", "buildc_receipt_verify_exit_zero"} <= set(
        packet["scope"]["checked"])


def test_timeout_is_inconclusive_never_match(tmp_path):
    packet = B.bridge_buildc_receipt(_receipt(tmp_path, "PASS"),
                                     command_result=_run(TIMEOUT_EXIT))
    assert packet["flywheel"]["verdict"] == B.UNVERIFIABLE
    assert packet["flywheel"]["failure_code"] == "buildc_verification_budget_exhausted"
    assert packet["scope"]["inconclusive"] is True
    assert packet["verification"]["budget_exhausted"] is True
    assert "buildc_receipt_verify_exit_zero" not in packet["scope"]["checked"]


def test_timeout_on_a_recorded_failure_is_still_inconclusive(tmp_path):
    packet = B.bridge_buildc_receipt(_receipt(tmp_path, "FAIL_UNEXPECTED"),
                                     command_result=_run(TIMEOUT_EXIT))
    assert packet["flywheel"]["failure_code"] == "buildc_verification_budget_exhausted"


def test_scope_block_names_the_export_when_present():
    assert scope_block({}, None, True)["checked"] == ["receipt_bytes_hashed",
                                                      "export_bytes_hashed"]
