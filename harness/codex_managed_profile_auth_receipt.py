"""Receipt validation for managed Codex profile auth extensions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PureWindowsPath
import re
from typing import Any

from .evidence_json import strict_load_json
from .private_artifact_fs import PrivateArtifactError, open_artifact_root

LOGIN_RECEIPT_SCHEMA = 'flywheel.codex-managed-profile-login-receipt/v1'
MAX_LOGIN_RECEIPT = 2_000_000
MAX_AUTH_METADATA = 16 * 1024 * 1024
_HEX64 = re.compile(r'[0-9a-f]{64}')


class CodexProfileLoginReceiptError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CodexProfileLoginReceiptRef:
    path: Path
    sha256: str


def read_login_receipt(ref: CodexProfileLoginReceiptRef) -> dict[str, Any]:
    if not isinstance(ref, CodexProfileLoginReceiptRef) or not _hex(ref.sha256):
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_REF')
    try:
        with open_artifact_root(Path(ref.path).parent, writable=False) as root:
            raw = root.read_bytes(Path(ref.path).name, max_bytes=MAX_LOGIN_RECEIPT)
    except PrivateArtifactError as exc:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_READ_' + exc.code) from exc
    if hashlib.sha256(raw).hexdigest() != ref.sha256:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_HASH_MISMATCH')
    try:
        return validate_login_receipt(strict_load_json(raw, max_bytes=MAX_LOGIN_RECEIPT))
    except ValueError as exc:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_JSON') from exc


def validate_login_receipt(value: object) -> dict[str, Any]:
    data = _dict(value)
    if data.get('schema') != LOGIN_RECEIPT_SCHEMA or not _hex(data.get('source_inventory_sha256')):
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_SCHEMA')
    codex, bindings = _dict(data.get('codex')), _dict(data.get('bindings'))
    if type(codex.get('version')) is not str or not codex['version'].strip() or not _hex(codex.get('executable_sha256')):
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_BINDING')
    if not _identity(bindings.get('home_identity')) or not _identity(bindings.get('workspace_identity')):
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_BINDING')
    login, completion, cleanup = _dict(data.get('login')), _dict(data.get('completion')), _dict(data.get('cleanup'))
    if type(login.get('mode')) is not str or not login['mode'] or not _hex(login.get('login_id_sha256')):
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_LOGIN')
    if completion.get('success') is not True:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_NOT_AUTHENTICATED')
    if not all(cleanup.get(key) is True for key in ('exited', 'job_closed', 'stderr_drain_complete')):
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_CLEANUP_REQUIRED')
    entries = data.get('auth_entries')
    if type(entries) is not list or not entries:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_AUTH')
    seen: set[str] = set()
    for row in entries:
        _auth_entry(row, seen)
    return data


def _auth_entry(row: object, seen: set[str]) -> None:
    row = _dict(row)
    path = row.get('path')
    if not _safe_root_path(path) or path.casefold() in seen:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_AUTH')
    seen.add(path.casefold())
    if row.get('kind') != 'file':
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_AUTH')
    limit = row.get('max_bytes')
    if type(limit) is not int or isinstance(limit, bool) or limit < 0 or limit > MAX_AUTH_METADATA:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_AUTH')


def _safe_root_path(value: object) -> bool:
    if type(value) is not str or not value or '/' in value or '\\' in value:
        return False
    windows = PureWindowsPath(value)
    return not (Path(value).is_absolute() or windows.is_absolute() or windows.drive or windows.root
                or value in {'.', '..'} or any(char in value for char in '*?[]:'))


def _identity(value: object) -> bool:
    return (type(value) is dict and value.get('platform') in {'windows', 'posix'}
            and type(value.get('device')) is int and type(value.get('inode')) is int)


def _dict(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise CodexProfileLoginReceiptError('LOGIN_RECEIPT_INVALID_SCHEMA')
    return value


def _hex(value: object) -> bool:
    return type(value) is str and bool(_HEX64.fullmatch(value))
