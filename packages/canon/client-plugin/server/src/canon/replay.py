from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ReplayError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ReplayClaim:
    principal: str
    source_state_sha256: str
    capsule_sha256: str
    nonce: str
    expires_ord: int

    def __post_init__(self) -> None:
        _require_text("principal", self.principal)
        _require_sha256("source_state_sha256", self.source_state_sha256)
        _require_sha256("capsule_sha256", self.capsule_sha256)
        _require_text("nonce", self.nonce)
        _require_positive_ord("expires_ord", self.expires_ord)


def replay_key(claim: ReplayClaim) -> str:
    checked = _require_claim(claim)
    payload = {
        "principal": checked.principal,
        "source_state_sha256": checked.source_state_sha256,
        "capsule_sha256": checked.capsule_sha256,
        "nonce": checked.nonce,
        "expires_ord": checked.expires_ord,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def check_replay_claim(
    claim: ReplayClaim,
    *,
    seen: set[str],
    current_ord: int,
) -> str:
    checked = _require_claim(claim)
    checked_seen = _require_seen(seen)
    checked_ord = _require_current_ord(current_ord)
    if checked_ord >= checked.expires_ord:
        raise ReplayError("stale", "claim has expired")
    key = replay_key(checked)
    if key in checked_seen:
        raise ReplayError("replay", "claim key was already seen")
    checked_seen.add(key)
    return key


def _require_claim(claim: object) -> ReplayClaim:
    if type(claim) is not ReplayClaim:
        raise ReplayError("invalid-replay-claim", "claim must be exact ReplayClaim")
    _require_text("principal", claim.principal)
    _require_sha256("source_state_sha256", claim.source_state_sha256)
    _require_sha256("capsule_sha256", claim.capsule_sha256)
    _require_text("nonce", claim.nonce)
    _require_positive_ord("expires_ord", claim.expires_ord)
    return claim


def _require_seen(seen: object) -> set[str]:
    if type(seen) is not set:
        raise ReplayError("invalid-seen", "seen must be a set")
    if not all(isinstance(item, str) and _SHA256_RE.fullmatch(item) for item in seen):
        raise ReplayError("invalid-seen", "seen contains invalid replay keys")
    return seen


def _require_current_ord(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReplayError("invalid-current-ord", "current_ord must be a non-bool int")
    return value


def _require_positive_ord(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReplayError("invalid-replay-claim", f"{name} must be a positive non-bool int")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or value == "":
        raise ReplayError("invalid-replay-claim", f"{name} must be a non-empty string")
    if "\0" in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ReplayError("invalid-replay-claim", f"{name} contains control characters")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ReplayError("invalid-replay-claim", f"{name} must be sha256:<64 lowercase hex>")
