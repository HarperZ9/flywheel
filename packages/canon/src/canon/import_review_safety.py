from __future__ import annotations

import re
from dataclasses import dataclass

from .atom import CanonAtom, validate_atom
from .canonical_json import canonical_sha256, sha256_text

_SECRET_MARKERS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\d{3}-\d{2}-\d{4}"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_CRITICAL_CODES = frozenset((
    "critical-disclosure-omission", "critical-secret", "duplicate-atom-id",
    "invalid-atom", "invalid-current-ord", "invalid-import-item", "invalid-items",
    "invalid-pinned-key-ids", "invalid-replay-claim", "invalid-seen",
    "invalid-source-state", "invalid-source-state-item", "invalid-text", "replay",
    "source_changed", "stale",
))
_SIGNATURE_STATUSES = frozenset({"valid", "none"})


@dataclass(frozen=True, slots=True)
class ImportItemIssue:
    code: str
    subject_id: str
    message: str


def validate_import_item_fields(item: object, index: int) -> tuple[ImportItemIssue, ...]:
    issues: list[ImportItemIssue] = []
    subject_id = f"item:{index}"
    if not _safe_text_key(item.source_id, allow_secret=False):  # type: ignore[attr-defined]
        issues.append(_issue("invalid-source-id", subject_id))
    if not _safe_text_blob(item.text):  # type: ignore[attr-defined]
        issues.append(_issue("invalid-text", subject_id))
    if type(item.signature_status) is not str or item.signature_status not in _SIGNATURE_STATUSES:  # type: ignore[attr-defined]
        issues.append(_issue("invalid-signature-status", subject_id))
    if item.key_id is not None and not _safe_text_key(item.key_id, allow_secret=False):  # type: ignore[attr-defined]
        issues.append(_issue("invalid-key-id", subject_id))
    if type(item.local) is not bool:  # type: ignore[attr-defined]
        issues.append(_issue("invalid-local-flag", subject_id))
    if type(item.model_synthesized) is not bool:  # type: ignore[attr-defined]
        issues.append(_issue("invalid-model-synthesized-flag", subject_id))
    if not _safe_text_key(item.replay_nonce, allow_secret=False):  # type: ignore[attr-defined]
        issues.append(_issue("invalid-replay-nonce", subject_id))
    if type(item.replay_expires_ord) is not int or item.replay_expires_ord <= 0:  # type: ignore[attr-defined]
        issues.append(_issue("invalid-replay-expires-ord", subject_id))
    return tuple(issues)


def snapshot_atom(atom: object) -> tuple[CanonAtom | None, str]:
    if type(atom) is not CanonAtom:
        return None, "item atom must be an exact CanonAtom"
    try:
        snapshot = CanonAtom.from_dict(atom.to_dict())
    except (KeyError, TypeError, ValueError):
        return None, "item atom snapshot failed"
    if validate_atom(snapshot):
        return None, "item atom failed validation"
    return snapshot, ""


def import_content_sha256(item: object) -> str:
    atom_hash = canonical_sha256(item.atom.to_dict())  # type: ignore[attr-defined]
    key_id = item.key_id  # type: ignore[attr-defined]
    payload = {
        "atom_sha256": atom_hash,
        "key_id_sha256": sha256_text(key_id) if key_id is not None else None,
        "local": item.local,  # type: ignore[attr-defined]
        "model_synthesized": item.model_synthesized,  # type: ignore[attr-defined]
        "replay_expires_ord": item.replay_expires_ord,  # type: ignore[attr-defined]
        "replay_nonce_sha256": sha256_text(item.replay_nonce),  # type: ignore[attr-defined]
        "signature_status": item.signature_status,  # type: ignore[attr-defined]
        "source_id_sha256": sha256_text(item.source_id),  # type: ignore[attr-defined]
        "text_sha256": sha256_text(item.text),  # type: ignore[attr-defined]
    }
    return canonical_sha256(payload)


def safe_subject_id(value: object, *, fallback: str = "source") -> str:
    if type(value) is not str:
        return f"{fallback}:invalid"
    if value == "" or _unsafe_text(value):
        return f"{fallback}:{_safe_hash(value)}"
    return value


def severity(code: str) -> str:
    return "critical" if code in _CRITICAL_CODES or code.startswith("invalid-") else "warning"


def quarantine_code(code: str) -> str:
    return "secret-quarantined" if code == "secret" else code


def error_code(exc: Exception) -> str:
    text = str(exc)
    return text.split(":", 1)[0] if ":" in text else type(exc).__name__


def _issue(code: str, subject_id: str) -> ImportItemIssue:
    return ImportItemIssue(code, subject_id, f"{code} blocked import activation")


def _safe_text_key(value: object, *, allow_secret: bool) -> bool:
    return (
        type(value) is str
        and value != ""
        and _is_utf8(value)
        and not _has_control(value)
        and (allow_secret or not _looks_secret(value))
    )


def _safe_text_blob(value: object) -> bool:
    return type(value) is str and _is_utf8(value) and "\0" not in value


def _unsafe_text(value: str) -> bool:
    return not _is_utf8(value) or _has_control(value) or _looks_secret(value)


def _has_control(value: str) -> bool:
    return "\0" in value or any(ord(char) < 32 or ord(char) == 127 for char in value)


def _looks_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_MARKERS)


def _is_utf8(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _safe_hash(value: str) -> str:
    try:
        return sha256_text(value)
    except UnicodeEncodeError:
        return "invalid"
