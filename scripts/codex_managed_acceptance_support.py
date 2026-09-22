"""Support helpers for managed Codex no-generation acceptance receipts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from harness.codex_account_safety import owner_ref as safe_owner_ref, safe_error
from harness.codex_consumer_account import read_account_state
from harness.codex_managed_account_client import ManagedCodexAccountClient
from harness.evidence_json import canonical_sha256
from harness.private_artifact_fs import root_identity

SCHEMA = "flywheel.codex-managed-no-generation-acceptance/v1"
AUTH_EXTENSION_SCHEMA = "flywheel.codex-managed-profile-auth-extension/v1"
DOES_NOT_PROVE = ["Does not initiate login, password entry, browser consent, provider generation, or tool approval.",
                  "Does not prove installed desktop packaging, Android, Relay, Plexus, or public release readiness.",
                  "Uses an owner-supplied existing managed profile; it does not copy ambient credentials."]


@dataclass(frozen=True)
class AcceptanceConfig:
    owner_ref: str; state_root: Path; policy_root: Path; workspace: Path
    profile_home: Path; executable: Path; executable_sha256: str
    codex_version: str; version_provenance: str; model: str; out: Path


class AcceptanceError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any] | None = None) -> None:
        self.code = code
        self.detail = detail or {}
        super().__init__(code)


def preflight_roots(cfg: AcceptanceConfig, receipt: dict, owner: str) -> dict[str, Path]:
    state = _existing_dir(cfg.state_root, "state_root_unavailable")
    policy = _existing_dir(cfg.policy_root, "policy_root_unavailable")
    workspace = _existing_dir(cfg.workspace, "workspace_unavailable")
    executable = Path(cfg.executable).expanduser().resolve()
    exe_ok = executable.is_file() and _sha256_file(executable) == cfg.executable_sha256.lower()
    add_assertion(receipt, "P01_codex_executable_hash", pass_if(exe_ok),
                  {"sha256": cfg.executable_sha256.lower()})
    if not exe_ok:
        raise AcceptanceError("codex_executable_mismatch")
    add_assertion(receipt, "P02_policy_root_ready", "PASS")
    expected_home = expected_profile_home(state, workspace, owner)
    actual_home = Path(cfg.profile_home).expanduser().resolve()
    home_ok = actual_home == expected_home and actual_home.is_dir()
    add_assertion(receipt, "P03_owner_supplied_profile_home", pass_if(home_ok), {
        "profile_home_matches_owner_workspace": actual_home == expected_home,
        "profile_home_preexists": actual_home.is_dir(),
        "profile_home_ref": path_ref(actual_home),
    })
    if not home_ok:
        raise AcceptanceError("owner_supplied_profile_required")
    add_assertion(receipt, "P04_no_ambient_credential_copying", "PASS",
                  {"profile_home_required": True, "ambient_profile_inputs": []})
    add_assertion(receipt, "P05_no_generation_scope", "PASS", {"allowed_methods": [
        "initialize", "initialized", "config/read", "configRequirements/read", "account/read", "model/list"]})
    add_assertion(receipt, "P06_login_flow_not_started", "PASS")
    return {"state_root": state, "policy_root": policy, "workspace": workspace,
            "executable": executable}


def expected_profile_home(state_root: Path, workspace: Path, owner_ref: str) -> Path:
    state = Path(state_root).expanduser().resolve()
    work = Path(workspace).expanduser().resolve()
    identity = root_identity(work).to_json_dict()
    key = canonical_sha256({"owner": owner_ref, "workspace": str(work).lower(),
                            "identity": identity})
    return state / "codex-managed" / key


def probe(lifecycle, owner: str, model: str, phase: str) -> dict[str, Any]:
    session = account = None
    result: dict[str, Any] = {"phase": phase}
    try:
        session, _profile, inventory, manifest = lifecycle.runtime_session_for_owner(
            owner_ref=owner)
        inspection = session.client.check_configuration()
        account = ManagedCodexAccountClient(session)
        account_summary = account_summary_from(account.get_account(refresh_token=False))
        model_summary = model_summary_from(account.list_models(include_hidden=False), model)
        result.update({
            "inventory_sha256": str(getattr(inventory, "sha256", "")),
            "auth_extension_present": auth_extension_present(manifest),
            "config_digest": str(getattr(session.client, "config_digest", "")),
            "config_inspection": inspection_result(inspection),
            "account_read": account_summary,
            "model_list": model_summary,
        })
    except Exception as exc:
        result["error"] = reason_from_exception(exc)
    finally:
        result["cleanup"] = close_probe(account, session)
    if not result.get("error"):
        result["error"] = probe_error(result)
    return result


def close_probe(account, session) -> dict[str, Any]:
    if account is None and session is None:
        return {"session_closed": False, "reason": "AGENT_NATIVE_RUNTIME_DISABLED"}
    try:
        if account is not None:
            account.close()
            return account.cleanup_evidence()
        if session.close() is True:
            return cleanup_evidence_from(session)
    except Exception:
        pass
    return {**cleanup_evidence_from(session), "reason": "AGENT_NATIVE_CLEANUP_REQUIRED"}


def cleanup_evidence_from(session) -> dict[str, Any]:
    cleanup = getattr(session, "cleanup", None)
    transport = getattr(session, "transport", None)
    return {"session_closed": getattr(session, "closed", False) is True,
            "transport_closed": getattr(transport, "closed", False) is True,
            "exited": getattr(cleanup, "exited", False) is True,
            "job_closed": getattr(cleanup, "job_closed", False) is True,
            "stderr_drain_complete": getattr(cleanup, "stderr_drain_complete", False) is True}


def probe_error(row: dict[str, Any]) -> str:
    account_read = row["account_read"]
    if (not account_read.get("authenticated")
            or account_read.get("usable_for_codex") is not True):
        return "AGENT_NATIVE_AUTH_REQUIRED"
    if not row["model_list"].get("configured_model_present"):
        return "AGENT_MODEL_MISMATCH"
    if not row.get("auth_extension_present"):
        return "AGENT_NATIVE_AUTH_REQUIRED"
    if row["config_inspection"].get("configuration_ready") is not True:
        return "AGENT_NATIVE_RUNTIME_DISABLED"
    if not cleanup_complete(row.get("cleanup", {})):
        return "AGENT_NATIVE_CLEANUP_REQUIRED"
    return ""


def probe_summary(row: dict[str, Any]) -> dict[str, Any]:
    cleanup = row.get("cleanup", {})
    return {"configuration_ready": row.get("config_inspection", {}).get("configuration_ready") is True,
            "auth_extension_present": row.get("auth_extension_present") is True,
            "account_authenticated": row.get("account_read", {}).get("authenticated") is True,
            "configured_model_present": row.get("model_list", {}).get("configured_model_present") is True,
            "cleanup_complete": cleanup_complete(cleanup)}


def cleanup_complete(cleanup: dict[str, Any]) -> bool:
    return all(cleanup.get(k) is True for k in
               ("session_closed", "transport_closed", "exited", "job_closed",
                "stderr_drain_complete"))


def account_summary_from(value: object) -> dict[str, Any]:
    state = read_account_state(_StaticAccountClient(value),
                               key_source=lambda _env: "absent")
    consumer = state.get("consumer") if isinstance(state.get("consumer"), dict) else {}
    api_key = state.get("api_key") if isinstance(state.get("api_key"), dict) else {}
    return {
        "response_type": type(value).__name__,
        "authenticated": consumer.get("state") == "authenticated",
        "usable_for_codex": state.get("usable_for_codex") is True,
        "effective_auth_source": safe_public_token(state.get("effective_auth_source")),
        "consumer": {
            "state": safe_public_token(consumer.get("state")),
            "type": safe_public_token(consumer.get("type")),
            "plan_type": safe_public_token(consumer.get("plan_type")),
            "email_present": consumer.get("email_present") is True,
        },
        "api_key_present": api_key.get("state") == "present",
    }


class _StaticAccountClient:
    def __init__(self, response: object) -> None:
        self._response = response

    def get_account(self, *, refresh_token: bool = False) -> object:
        return self._response


def safe_public_token(value: object) -> str:
    return value if isinstance(value, str) else ""


def model_summary_from(value: object, model: str) -> dict[str, Any]:
    data = value.get("data") if isinstance(value, dict) else []
    rows = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
    ids = [str(row.get("id", "")) for row in rows if isinstance(row.get("id"), str)]
    return {"response_type": type(value).__name__, "count": len(rows),
            "configured_model_present": model in ids}


def auth_extension_present(manifest: object) -> bool:
    return (isinstance(manifest, dict) and isinstance(manifest.get("auth_extension"), dict)
            and manifest["auth_extension"].get("schema") == AUTH_EXTENSION_SCHEMA)


def inspection_result(value: object) -> dict[str, Any]:
    result = value.as_result() if hasattr(value, "as_result") else {}
    if not isinstance(result, dict):
        return {"configuration_ready": False, "issues": ["inspection_malformed"]}
    return {"schema": result.get("schema"),
            "configuration_ready": result.get("configuration_ready") is True,
            "config_digest": str(result.get("config_digest", "")),
            "issues": [str(item)[:120] for item in result.get("issues", []) if isinstance(item, str)]}


def base_receipt(repo_root: Path, cfg: AcceptanceConfig, owner: str, started: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "complete": False, "started_utc": started,
            "source": {"repo_root": str(repo_root), "head": git_head(repo_root)},
            "owner_ref": owner, "model": cfg.model, "codex_version": cfg.codex_version,
            "assertions": [], "does_not_prove": DOES_NOT_PROVE}


def add_assertion(receipt: dict, assertion_id: str, state: str,
                  observed: dict[str, Any] | None = None) -> None:
    receipt["assertions"].append({"id": assertion_id, "state": state,
                                  "observed": observed or {}})


def pass_if(value: bool) -> str:
    return "PASS" if value else "FAIL"


_PUBLIC_LIFECYCLE_ERROR_CODES = frozenset({
    "AGENT_NATIVE_AUTH_REQUIRED",
    "BASELINE_ACCEPTED_INVENTORY_REQUIRED",
    "BASELINE_INVENTORY_AMBIGUOUS",
    "BASELINE_INVENTORY_REJECTED",
})


def reason_from_exception(exc: BaseException) -> str:
    if _is_public_lifecycle_error(exc):
        return exc.code
    return safe_error(exc)


def _is_public_lifecycle_error(exc: BaseException) -> bool:
    try:
        from harness.codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycleError
    except Exception:
        return False
    return (isinstance(exc, CodexManagedInventoryLifecycleError)
            and getattr(exc, "code", None) in _PUBLIC_LIFECYCLE_ERROR_CODES)


def safe_owner(value: str) -> str:
    return safe_owner_ref(value)


def dt_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def path_ref(path: Path) -> str:
    return "sha256:" + hashlib.sha256(str(path).lower().encode("utf-8")).hexdigest()


def git_head(root: Path) -> str:
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            check=False, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def _existing_dir(path: Path, code: str) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.is_dir():
        raise AcceptanceError(code)
    return value


def _sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()
