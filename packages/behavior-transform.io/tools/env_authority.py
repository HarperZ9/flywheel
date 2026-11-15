"""Environment-native authority resolution.

Authorization is intrinsic to the deployment, not injected via prompt
engineering or in-band authority claims. If the tool is deployed with a
valid capsule, intact seals, and a verified activation state, the
environment IS the authorization. No external auth server, no token
exchange, no identity provider required.

The resolver produces an AuthorityGrant that downstream gates consume.
The grant is derived from environment state and is never transmitted to
model context as an authority claim. Models read the grant's surface
projection (verified/unverified), not its internals.

Root of trust chain:
  machine fingerprint + capsule integrity + seal validity + activation state
  → AuthorityGrant (scoped entitlements, operator fingerprint, expiry)
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCHEMA = "behavior-transform.env-authority.v1"

SURFACE_ENTITLEMENTS: dict[str, list[str]] = {
    "claude_code": ["transform", "modulate", "classify", "infer", "scan"],
    "codex_app": ["transform", "modulate", "classify", "infer", "scan"],
    "codex_cli": ["transform", "modulate", "classify", "infer", "scan"],
    "generic_cli": ["transform", "modulate", "classify", "scan"],
    "warden_cli": ["transform", "modulate", "classify", "infer", "scan",
                    "inoculate", "condition", "seal"],
}

DEFAULT_GRANT_TTL_SECONDS = 3600


@dataclass(frozen=True)
class MachineFingerprint:
    """Deterministic fingerprint derived from stable machine attributes."""
    node_name: str
    platform: str
    machine: str
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_name": self.node_name,
            "platform": self.platform,
            "machine": self.machine,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class AuthorityGrant:
    """Scoped authorization derived from environment state."""
    schema: str
    status: str
    operator_fingerprint: str
    machine_fingerprint: str
    capsule_sha256: str
    seal_status: str
    surface: str
    entitlements: list[str]
    issued_at: float
    expires_at: float
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return (
            self.status == "authorized"
            and self.seal_status == "pass"
            and time.time() < self.expires_at
        )

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    def has_entitlement(self, capability: str) -> bool:
        return self.valid and capability in self.entitlements

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "operator_fingerprint": self.operator_fingerprint,
            "machine_fingerprint": self.machine_fingerprint,
            "capsule_sha256": self.capsule_sha256,
            "seal_status": self.seal_status,
            "surface": self.surface,
            "entitlements": self.entitlements,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "valid": self.valid,
            "expired": self.expired,
        }

    def surface_projection(self) -> dict[str, Any]:
        """What the model sees: verified/unverified, nothing more."""
        return {
            "authorization_status": "verified" if self.valid else "unverified",
            "surface": self.surface,
            "entitlement_count": len(self.entitlements) if self.valid else 0,
        }


def derive_machine_fingerprint() -> MachineFingerprint:
    """Derive a stable fingerprint from machine attributes."""
    node = platform.node()
    plat = platform.platform()
    mach = platform.machine()
    raw = f"{node}:{plat}:{mach}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return MachineFingerprint(
        node_name=node,
        platform=plat,
        machine=mach,
        digest=digest,
    )


def derive_operator_fingerprint(
    machine: MachineFingerprint,
    capsule_sha256: str,
) -> str:
    """Derive operator identity from machine + capsule binding."""
    raw = f"{machine.digest}:{capsule_sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _try_load_capsule() -> tuple[str, str]:
    """Load capsule hash. Returns (sha256, status)."""
    try:
        from preflight.capsule import load_capsule
        from preflight.paths import capsule_path
        capsule = load_capsule(capsule_path())
        return capsule.sha256, "pass"
    except Exception:
        pass

    capsule_env = os.environ.get("WARDEN_CAPSULE_SHA256", "")
    if capsule_env:
        return capsule_env, "env"

    return "", "missing"


def _try_verify_seal() -> str:
    """Check seal validity. Returns status string."""
    try:
        from preflight.seals import verify_latest_seal
        result = verify_latest_seal()
        return result.get("status", "fail")
    except Exception:
        return "unavailable"


def _try_activation_surface() -> str:
    """Read the currently activated surface from env or state."""
    surface = os.environ.get("WARDEN_PREFIRE_SURFACE", "")
    if surface:
        return surface

    try:
        from preflight.activation import state_root
        from preflight.paths import project_root
        root = state_root(project_root())
        if root.exists():
            for state_file in sorted(root.glob("*/state.json"), reverse=True):
                data = json.loads(state_file.read_text(encoding="utf-8"))
                if data.get("status") == "pass":
                    return state_file.parent.name
    except Exception:
        pass

    return "generic_cli"


_grant_cache: dict[str, AuthorityGrant] = {}


def cached_authority(
    surface: str | None = None,
    ttl: int = DEFAULT_GRANT_TTL_SECONDS,
) -> AuthorityGrant:
    """Return a cached grant if still valid, otherwise resolve fresh.

    Cache key is the resolved surface. A grant that has expired or was
    unauthorized is not cached (every call re-resolves, so environment
    changes take effect immediately on failure paths).
    """
    key = surface or "__default__"
    cached = _grant_cache.get(key)
    if cached is not None and cached.valid:
        return cached

    grant = resolve_authority(surface=surface, ttl=ttl)
    if grant.valid:
        _grant_cache[key] = grant
    else:
        _grant_cache.pop(key, None)
    return grant


def invalidate_cache(surface: str | None = None) -> None:
    """Clear cached grants. Call after environment changes."""
    if surface:
        _grant_cache.pop(surface, None)
        _grant_cache.pop("__default__", None)
    else:
        _grant_cache.clear()


def resolve_authority(
    surface: str | None = None,
    ttl: int = DEFAULT_GRANT_TTL_SECONDS,
) -> AuthorityGrant:
    """Resolve authorization from environment state.

    No network calls, no token exchange, no identity provider. The
    environment itself is the authority: valid capsule + intact seals +
    machine binding = authorized.
    """
    machine = derive_machine_fingerprint()
    capsule_sha256, capsule_status = _try_load_capsule()
    seal_status = _try_verify_seal()
    resolved_surface = surface or _try_activation_surface()

    if not capsule_sha256:
        return AuthorityGrant(
            schema=SCHEMA,
            status="unauthorized",
            operator_fingerprint="",
            machine_fingerprint=machine.digest,
            capsule_sha256="",
            seal_status=seal_status,
            surface=resolved_surface,
            entitlements=[],
            issued_at=time.time(),
            expires_at=0,
            evidence={"reason": "no_capsule", "capsule_status": capsule_status},
        )

    operator_fp = derive_operator_fingerprint(machine, capsule_sha256)
    entitlements = list(SURFACE_ENTITLEMENTS.get(resolved_surface, []))
    now = time.time()

    authorized = (
        capsule_status in ("pass", "env")
        and seal_status in ("pass", "unavailable")
    )

    return AuthorityGrant(
        schema=SCHEMA,
        status="authorized" if authorized else "unauthorized",
        operator_fingerprint=operator_fp,
        machine_fingerprint=machine.digest,
        capsule_sha256=capsule_sha256,
        seal_status=seal_status,
        surface=resolved_surface,
        entitlements=entitlements if authorized else [],
        issued_at=now,
        expires_at=now + ttl if authorized else 0,
        evidence={
            "capsule_status": capsule_status,
            "seal_status": seal_status,
            "surface_resolved_from": "arg" if surface else "env",
        },
    )


def main() -> int:
    import sys

    grant = resolve_authority()
    sys.stdout.write(json.dumps(grant.to_dict(), indent=2) + "\n")
    return 0 if grant.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
