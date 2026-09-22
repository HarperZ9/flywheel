"""Claude managed profile custody helpers."""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .evidence_json import canonical_sha256
from .journey_types import SHA256_PATTERN
from .private_artifact_fs import (
    NOT_FOUND,
    ArtifactIdentity,
    PrivateArtifactError,
    open_artifact_root,
)
from .provider_session_contract import ProviderSessionError


@dataclass(frozen=True)
class ClaudeManagedProfile:
    owner_ref: str
    profile_home: Path
    workspace: Path
    auth_directory: Path
    executable: Path
    executable_sha256: str
    profile_identity: ArtifactIdentity
    workspace_identity: ArtifactIdentity
    auth_directory_identity: ArtifactIdentity
    settings_sha256: str
    mcp_sha256: str
    config_digest: str


def prepare_claude_profile(
        *, state_root: Path, workspace: Path, owner_ref: str,
        executable: Path, executable_sha256: str, auth_directory: Path,
        policy_payload: Mapping[str, Any], settings: Mapping[str, Any],
        mcp_config: Mapping[str, Any], limitations: tuple[str, ...]) -> ClaudeManagedProfile:
    state_root = _existing_dir(state_root)
    workspace = _existing_dir(workspace)
    auth_directory = _existing_dir(auth_directory)
    executable = _existing_file(executable)
    _validate_owner(owner_ref)
    _validate_layout(state_root, workspace, auth_directory)
    _verify_executable_hash(executable, executable_sha256)
    settings_bytes = _json_bytes(settings)
    mcp_bytes = _json_bytes(mcp_config)
    settings_sha = hashlib.sha256(settings_bytes).hexdigest()
    mcp_sha = hashlib.sha256(mcp_bytes).hexdigest()
    try:
        with open_artifact_root(workspace, writable=False) as work, \
                open_artifact_root(auth_directory, writable=False) as auth, \
                open_artifact_root(state_root) as state:
            _verify_workspace_boundary(work)
            digest = canonical_sha256({
                "schema": "flywheel.claude-managed-runtime/v1",
                "owner_ref": owner_ref,
                "workspace": str(workspace).lower(),
                "workspace_identity": work.identity.to_json_dict(),
                "auth_directory_identity": auth.identity.to_json_dict(),
                "executable": str(executable).lower(),
                "executable_sha256": executable_sha256,
                "policy": dict(policy_payload),
                "limitations": list(limitations),
            })
            rel = "claude-managed/" + digest
            state.write_new_or_same(rel + "/settings.json", settings_bytes)
            state.write_new_or_same(rel + "/mcp.json", mcp_bytes)
            for marker in (
                "runtime/Temp/.flywheel-owned",
                "runtime/AppData/Roaming/.flywheel-owned",
                "runtime/AppData/Local/.flywheel-owned",
            ):
                state.write_new_or_same(rel + "/" + marker, b"")
            state.write_new_or_same(rel + "/manifest.json", _json_bytes({
                "schema": "flywheel.claude-managed-runtime-manifest/v1",
                "admitted": False,
                "limitations": list(limitations),
                "settings_sha256": settings_sha,
                "mcp_sha256": mcp_sha,
            }))
            profile_home = state_root / rel
            with open_artifact_root(profile_home, writable=False) as profile:
                return ClaudeManagedProfile(
                    owner_ref=owner_ref,
                    profile_home=profile_home,
                    workspace=workspace,
                    auth_directory=auth_directory,
                    executable=executable,
                    executable_sha256=executable_sha256,
                    profile_identity=profile.identity,
                    workspace_identity=work.identity,
                    auth_directory_identity=auth.identity,
                    settings_sha256=settings_sha,
                    mcp_sha256=mcp_sha,
                    config_digest=digest,
                )
    except ProviderSessionError:
        raise
    except Exception:
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED") from None


@contextmanager
def lease_claude_profile(profile: ClaudeManagedProfile):
    with ExitStack() as stack:
        try:
            profile_root = stack.enter_context(open_artifact_root(
                profile.profile_home, writable=False, expected=profile.profile_identity))
            workspace = stack.enter_context(open_artifact_root(
                profile.workspace, writable=False, expected=profile.workspace_identity))
            stack.enter_context(open_artifact_root(
                profile.auth_directory, writable=False,
                expected=profile.auth_directory_identity))
            stack.enter_context(open_artifact_root(profile.profile_home.parent, writable=False))
            _verify_profile(profile, profile_root, workspace)
            yield lambda: _verify_profile(profile, profile_root, workspace)
        except ProviderSessionError:
            raise
        except Exception:
            raise ProviderSessionError("AGENT_BINDING_DRIFT") from None


def _verify_profile(profile: ClaudeManagedProfile, profile_root, workspace) -> None:
    _verify_workspace_boundary(workspace)
    _verify_profile_file(profile_root, "settings.json", profile.settings_sha256)
    _verify_profile_file(profile_root, "mcp.json", profile.mcp_sha256)
    _verify_executable_hash(profile.executable, profile.executable_sha256)


def _existing_dir(path: Path) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except Exception:
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED") from None
    if not resolved.is_dir():
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    return resolved


def _existing_file(path: Path) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except Exception:
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED") from None
    if not resolved.is_file():
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    return resolved


def _validate_owner(owner_ref: str) -> None:
    if (type(owner_ref) is not str or not owner_ref.strip() or len(owner_ref) > 256
            or any(ord(c) < 32 for c in owner_ref)):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")


def _validate_layout(state_root: Path, workspace: Path, auth_directory: Path) -> None:
    pairs = ((state_root, workspace), (state_root, auth_directory), (workspace, auth_directory))
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a) for a, b in pairs):
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")


def _verify_executable_hash(executable: Path, expected: str) -> None:
    if SHA256_PATTERN.fullmatch(expected or "") is None:
        raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")
    with executable.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != expected:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")


def _verify_workspace_boundary(workspace_root) -> None:
    _reject_present(workspace_root, ".claude", directory=True)
    _reject_present(workspace_root, ".mcp.json", directory=False)


def _reject_present(root, rel: str, *, directory: bool) -> None:
    try:
        if directory:
            root.list_names(rel, max_entries=1)
        else:
            root.read_bytes(rel, max_bytes=1)
    except PrivateArtifactError as exc:
        if exc.code == NOT_FOUND:
            return
    raise ProviderSessionError("AGENT_NATIVE_RUNTIME_DISABLED")


def _verify_profile_file(root, rel: str, expected_hash: str) -> None:
    data = root.read_bytes(rel, max_bytes=1024 * 1024)
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ProviderSessionError("AGENT_BINDING_DRIFT")


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
