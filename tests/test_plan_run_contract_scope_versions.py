"""A stored plan-run v2 result still verifies, and only under its own scope key."""
from copy import deepcopy

from harness.plan_run_contract import (PLAN_LIMITATIONS_V2, RECEIPT_SCHEMA_V2, RESULT_SCHEMA_V2,
                                      build_plan_run_result, verify_plan_result)
from harness.scope import LEGACY_SCOPE_KEY
from tests.test_plan_run_contract import _fixture, _receipt_inputs, _workflow, canonical_sha256


def _as_v2(result: dict, *, key: str = LEGACY_SCOPE_KEY) -> dict:
    """Rebuild a stored v2 result: the older key and its own list, digests re-sealed."""
    old = deepcopy(result)
    receipt = {k: v for k, v in old["receipt"].items()
               if k not in ("scope", "receipt_sha256")}
    receipt.update(schema=RECEIPT_SCHEMA_V2, **{key: list(PLAN_LIMITATIONS_V2)})
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    old = {"schema": RESULT_SCHEMA_V2, "plan_run_ref": old["plan_run_ref"],
           "receipt": receipt, "workflow_run": old["workflow_run"]}
    old["result_sha256"] = canonical_sha256(old)
    return old


def test_a_stored_v2_result_still_verifies_and_only_under_its_own_key():
    result = build_plan_run_result(
        workflow_run=_workflow(), **_receipt_inputs(_fixture()["binding"]))
    assert verify_plan_result(_as_v2(result))["verdict"] == "MATCH"
    assert verify_plan_result(_as_v2(result, key="scope"))["verdict"] == "DRIFT"
