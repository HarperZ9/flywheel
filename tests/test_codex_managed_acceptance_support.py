from harness.codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycleError
from scripts.codex_managed_acceptance_support import reason_from_exception


class ForeignCodeError(RuntimeError):
    code = "BASELINE_ACCEPTED_INVENTORY_REQUIRED"


def test_reason_from_exception_exposes_only_known_lifecycle_codes():
    assert reason_from_exception(CodexManagedInventoryLifecycleError(
        "BASELINE_ACCEPTED_INVENTORY_REQUIRED")) == "BASELINE_ACCEPTED_INVENTORY_REQUIRED"
    assert reason_from_exception(ForeignCodeError("hidden")) == "ForeignCodeError"
    assert reason_from_exception(CodexManagedInventoryLifecycleError(
        "C:/Users/example/.codex/auth.json")) == "CodexManagedInventoryLifecycleError"
