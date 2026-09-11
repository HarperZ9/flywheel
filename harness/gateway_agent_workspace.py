"""Freeze parent workspace policy and pin the approved directory at use."""
from contextlib import contextmanager
import os
from pathlib import Path

from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError
from .private_artifact_fs import ArtifactIdentity, open_artifact_root, root_identity


def freeze_workspace(requested, default: Path) -> dict:
    try:
        root = Path(requested if requested is not None else default).expanduser().resolve(strict=True)
        raw = os.environ.get("FLYWHEEL_WORKSPACE_ROOTS", "")
        allowed = sorted(set(str(Path(p.strip()).expanduser().resolve(strict=True))
            for p in raw.split(os.pathsep) if p.strip()))
        if raw.strip() and not allowed:
            raise ValueError
        if allowed and not any(root.is_relative_to(Path(p)) for p in allowed):
            raise ValueError
        policy = {"mode": "configured" if allowed else "legacy_open",
                  "allowed_roots": allowed}
        return {"root": str(root), "root_identity": root_identity(root).to_json_dict(),
                "policy": policy, "policy_sha256": canonical_sha256(policy)}
    except Exception:
        raise GatewayOperationError("AGENT_BINDING_DRIFT") from None


def validate_workspace(value) -> None:
    try:
        if (type(value) is not dict or set(value) != {
                "root", "root_identity", "policy", "policy_sha256"}
                or type(value["root"]) is not str or not Path(value["root"]).is_absolute()
                or set(value["root_identity"]) != {"platform", "device", "inode"}):
            raise ValueError
        ArtifactIdentity.from_json_dict(value["root_identity"])
        policy = value["policy"]
        if (set(policy) != {"mode", "allowed_roots"}
                or type(policy["allowed_roots"]) is not list
                or len(policy["allowed_roots"]) > 64
                or any(type(p) is not str or not Path(p).is_absolute() for p in policy["allowed_roots"])
                or policy["allowed_roots"] != sorted(set(policy["allowed_roots"]))
                or policy["mode"] != ("configured" if policy["allowed_roots"] else "legacy_open")
                or value["policy_sha256"] != canonical_sha256(policy)
                or policy["allowed_roots"] and not any(Path(value["root"]).is_relative_to(Path(p))
                    for p in policy["allowed_roots"])):
            raise ValueError
    except Exception:
        raise GatewayOperationError("AGENT_BINDING_DRIFT") from None


@contextmanager
def pinned_workspace(value):
    """Windows custody holds the root and ancestors against rename until exit.

    POSIX pins identity for validation; supervised production execution currently
    requires windows_job_v1. This does not claim POSIX path tools resist swaps.
    """
    validate_workspace(value)
    try:
        cap = open_artifact_root(value["root"], writable=False,
            expected=ArtifactIdentity.from_json_dict(value["root_identity"]))
        cap.__enter__()
    except Exception:
        raise GatewayOperationError("AGENT_BINDING_DRIFT") from None
    try:
        yield Path(value["root"])
    finally:
        cap.close()
