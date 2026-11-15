from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .canonical_json import canonical_sha256, sha256_text
from .omission import Omission
from .path_policy import PathPolicyError, classify_protected_path, is_reparse_point, is_windows_ads_path
from .transform import TransformReceipt

_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai-api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
)
_METHOD_ID = "deterministic-regex-secret-quarantine-v1"
_LIMITATION = (
    "This secret quarantine proves only deterministic local pattern matches; "
    "it does not prove all sensitive values were detected or that omitted "
    "content was irrelevant."
)


@dataclass(frozen=True, slots=True)
class SecretFinding:
    code: str
    source_id: str
    start: int
    end: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SecretQuarantine:
    safe_text: str | None
    findings: tuple[SecretFinding, ...]
    omissions: tuple[Omission, ...]
    receipts: tuple[TransformReceipt, ...]
    reason_codes: tuple[str, ...]


class SecretQuarantineError(ValueError):
    pass


def scan_text(text: str, *, source_id: str) -> tuple[SecretFinding, ...]:
    checked_text = _require_text(text)
    checked_source = _require_source_id(source_id)
    return _findings(checked_text, checked_source)


def quarantine_text(text: str, *, source_id: str, critical: bool = False) -> SecretQuarantine:
    checked_text = _require_text(text)
    checked_source = _require_source_id(source_id)
    findings = _findings(checked_text, checked_source)
    if not findings:
        return SecretQuarantine(checked_text, (), (), (), ())
    if critical is True:
        raise SecretQuarantineError(f"critical-secret: {checked_source}")
    return _quarantine(findings, source_id=checked_source, input_hash=sha256_text(checked_text))


def quarantine_path(path: str | Path, *, source_id: str, critical: bool = False) -> SecretQuarantine:
    checked_source = _require_source_id(source_id)
    checked_path, raw_path = _require_path(path)
    unresolved = _unresolved_absolute(checked_path)
    ads_path = _ads_path(raw_path, unresolved)
    if ads_path is not None:
        return _path_quarantine("ads-path", checked_source, ads_path, critical)
    if _has_protected_path(raw_path, unresolved):
        return _path_quarantine("protected-path", checked_source, raw_path, critical)
    _reject_reparse_chain(unresolved, checked_source)
    resolved = _resolve_target(unresolved)
    ads_path = _ads_path(resolved)
    if ads_path is not None:
        return _path_quarantine("ads-path", checked_source, ads_path, critical)
    if _has_protected_path(resolved):
        return _path_quarantine("protected-path", checked_source, str(resolved), critical)
    text = _read_utf8_text(resolved, checked_source)
    return quarantine_text(text, source_id=checked_source, critical=critical)


def _findings(text: str, source_id: str) -> tuple[SecretFinding, ...]:
    found: list[SecretFinding] = []
    seen: set[tuple[str, int, int, str]] = set()
    for code, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            digest = sha256_text(match.group(0))
            key = (code, match.start(), match.end(), digest)
            if key in seen:
                continue
            seen.add(key)
            found.append(SecretFinding(code, source_id, match.start(), match.end(), digest))
    return tuple(sorted(found, key=lambda item: (item.start, item.end, item.code, item.sha256)))


def _quarantine(
    findings: tuple[SecretFinding, ...],
    *,
    source_id: str,
    input_hash: str,
) -> SecretQuarantine:
    omission = Omission(
        reason="secret",
        count=1,
        affected_ids=(source_id,),
        affected_source_refs=(source_id,),
        critical=False,
        decision="omitted",
        does_not_prove=(_LIMITATION,),
    )
    output_hash = canonical_sha256({
        "kind": "secret-quarantine-marker",
        "finding_sha256": tuple(finding.sha256 for finding in findings),
        "source_sha256": sha256_text(source_id),
    })
    receipt = TransformReceipt(
        transform="redaction",
        method_id=_METHOD_ID,
        input_refs=(source_id,),
        input_span_hash=input_hash,
        output_ref="secret-quarantine:" + output_hash.removeprefix("sha256:"),
        output_hash=output_hash,
        lossy=True,
        retained_critical_atom_ids=(),
        omissions=(omission,),
        verifier="deterministic",
        does_not_prove=(_LIMITATION,),
    )
    return SecretQuarantine(None, findings, (omission,), (receipt,), ("secret",))


def _require_text(text: object) -> str:
    if not isinstance(text, str):
        raise SecretQuarantineError("invalid-text: expected str")
    _require_utf8(text, "invalid-text")
    if "\0" in text:
        raise SecretQuarantineError("invalid-text: contains NUL")
    return text


def _require_source_id(source_id: object) -> str:
    if not isinstance(source_id, str):
        raise SecretQuarantineError("invalid-source-id: expected str")
    _require_utf8(source_id, "invalid-source-id")
    if source_id == "" or "\0" in source_id or any(ord(char) < 32 for char in source_id):
        raise SecretQuarantineError(f"invalid-source-id: {sha256_text(source_id)}")
    if any(pattern.search(source_id) for _code, pattern in _PATTERNS):
        raise SecretQuarantineError(f"invalid-source-id: {sha256_text(source_id)}")
    return source_id


def _require_path(path: object) -> tuple[Path, str]:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise SecretQuarantineError("invalid-path: expected str or Path") from exc
    if not isinstance(raw, str) or raw == "":
        raise SecretQuarantineError("invalid-path: expected text path")
    _require_utf8(raw, "invalid-path")
    if "\0" in raw:
        raise SecretQuarantineError(f"invalid-path: {sha256_text(raw)}")
    return Path(raw), raw


def _require_utf8(value: str, code: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SecretQuarantineError(f"{code}: non-utf8 text") from exc


def _unresolved_absolute(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _resolve_target(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SecretQuarantineError("invalid-path: cannot resolve path") from exc


def _has_protected_path(*paths: str | Path) -> bool:
    return any(_classify_protected(path) for path in paths)


def _ads_path(*paths: str | Path) -> str | None:
    for path in paths:
        try:
            if is_windows_ads_path(path):
                return os.fspath(path)
        except PathPolicyError as exc:
            raise SecretQuarantineError("invalid-path: rejected by path policy") from exc
    return None


def _classify_protected(path: str | Path) -> bool:
    try:
        return bool(classify_protected_path(path))
    except PathPolicyError as exc:
        raise SecretQuarantineError("invalid-path: rejected by path policy") from exc


def _path_quarantine(code: str, source_id: str, path_ref: str, critical: bool) -> SecretQuarantine:
    finding = _metadata_finding(code, source_id, path_ref)
    if critical is True:
        raise SecretQuarantineError(f"critical-secret: {source_id}")
    return _quarantine((finding,), source_id=source_id, input_hash=finding.sha256)


def _metadata_finding(code: str, source_id: str, raw_path: str) -> SecretFinding:
    digest = canonical_sha256({
        "code": code,
        "path_sha256": sha256_text(raw_path),
        "source_sha256": sha256_text(source_id),
    })
    return SecretFinding(code, source_id, 0, 0, digest)


def _reject_reparse_chain(path: Path, source_id: str) -> None:
    current = path
    candidates: list[Path] = []
    while current not in candidates:
        candidates.append(current)
        if current.parent == current:
            break
        current = current.parent
    for candidate in candidates:
        try:
            exists = candidate.exists() or candidate.is_symlink()
        except OSError:
            raise SecretQuarantineError(f"unreadable-source: {source_id}")
        if exists and is_reparse_point(candidate):
            raise SecretQuarantineError(f"reparse-path: {source_id}")


def _read_utf8_text(path: Path, source_id: str) -> str:
    try:
        if not path.is_file():
            raise SecretQuarantineError(f"unreadable-source: {source_id}")
        data = path.read_bytes()
    except SecretQuarantineError:
        raise
    except OSError as exc:
        raise SecretQuarantineError(f"unreadable-source: {source_id}") from exc
    if b"\0" in data:
        raise SecretQuarantineError(f"binary-source: {source_id}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretQuarantineError(f"invalid-utf8-source: {source_id}") from exc
