"""Safe account-status fields for native CLI endpoint roster rows."""
from __future__ import annotations


def native_account_extra(name: str, claude_status, codex_status) -> dict:
    if name == "claude-cli":
        account = claude_status()
        return {"account_state": account.get("state", "unknown"),
                "account_authenticated": account.get("authenticated") is True,
                "account_executable": account.get("executable", "")}
    if name != "codex-cli":
        return {}
    account = codex_status()
    return {"account_state": account.get("account_state", account.get("state", "unknown")),
            "account_authenticated": account.get("authenticated") is True,
            "account_executable": account.get("executable", ""),
            "plan_type": account.get("plan_type", ""),
            "route_ready": account.get("route_ready") is True,
            "route_ready_reason": account.get("route_ready_reason", ""),
            "run_ready": account.get("run_ready") is True,
            "run_ready_reason": account.get("run_ready_reason", ""),
            "readiness_check_available": account.get("readiness_check_available") is True,
            "readiness_checked": account.get("readiness_checked") is True,
            "readiness_probe": account.get("readiness_probe", ""),
            "supervised_run_ready": account.get("supervised_run_ready") is True}
