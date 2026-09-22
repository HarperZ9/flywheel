"""Producer for managed Codex login receipts.

The receipt binds a successful managed-login completion to a reviewed baseline
inventory and metadata-only auth path policy. It never reads credential content.
"""
from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import Any

from .codex_account_binding import LoginCompletionContext, ManagedCodexAccountBinding
from .codex_managed_account_client import ManagedCodexAccountClient
from .codex_managed_profile_auth_receipt import (
    LOGIN_RECEIPT_SCHEMA,
    MAX_AUTH_METADATA,
    CodexProfileLoginReceiptRef,
    validate_login_receipt,
)
from .codex_managed_profile_manifest import (
    CodexProfileInventoryRef,
    extend_manifest_after_explicit_login,
    read_restart_manifest,
)
from .evidence_json import canonical_bytes
from .private_artifact_fs import PrivateArtifactError, open_artifact_root


class CodexManagedLoginReceiptWriterError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def record_login_success(ctx: LoginCompletionContext) -> CodexProfileInventoryRef:
    ctx = _context(ctx)
    receipt = write_login_receipt(ctx)
    binding = ctx.binding
    return extend_manifest_after_explicit_login(
        binding.profile,
        binding.inventory,
        executable=binding.executable,
        executable_sha256=binding.executable_sha256,
        codex_version=binding.codex_version,
        login_receipt=receipt,
        policy_root=binding.policy_root,
        expected_login_id=ctx.login_id,
        expected_mode=ctx.mode,
    )


def write_login_receipt(ctx: LoginCompletionContext) -> CodexProfileLoginReceiptRef:
    ctx = _context(ctx)
    binding = ctx.binding
    base = _base_inventory(binding)
    cleanup = _cleanup_evidence(binding.client)
    _check_completion(ctx)
    _check_binding(binding, base)
    _check_auth_policy(binding.profile, base)
    receipt = validate_login_receipt({
        'schema': LOGIN_RECEIPT_SCHEMA,
        'source_inventory_sha256': binding.inventory.sha256,
        'codex': {
            'version': binding.codex_version,
            'executable_sha256': binding.executable_sha256,
        },
        'bindings': {
            'home_identity': binding.profile.home_identity.to_json_dict(),
            'workspace_identity': binding.profile.workspace_identity.to_json_dict(),
        },
        'login': {
            'mode': ctx.mode,
            'login_id_sha256': hashlib.sha256(ctx.login_id.encode('utf-8')).hexdigest(),
        },
        'completion': {'success': True},
        'cleanup': {
            'exited': cleanup['exited'],
            'job_closed': cleanup['job_closed'],
            'stderr_drain_complete': cleanup['stderr_drain_complete'],
        },
        'auth_policy': {
            'credential_storage': 'file',
            'content_read': False,
            'exact_paths_only': True,
            'source': 'codex-auth-docs-auth-json-file-storage-2026-09-16',
        },
        'auth_entries': [{
            'path': 'auth.json',
            'kind': 'file',
            'max_bytes': MAX_AUTH_METADATA,
        }],
    })
    raw = canonical_bytes(receipt)
    digest = hashlib.sha256(raw).hexdigest()
    rel = f'codex-policy/{binding.inventory.sha256}/login-receipts/{digest}.json'
    try:
        with open_artifact_root(Path(binding.policy_root)) as root:
            root.write_new_or_same(rel, raw)
    except PrivateArtifactError as exc:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_WRITE_' + exc.code) from exc
    return CodexProfileLoginReceiptRef(path=Path(binding.policy_root) / rel, sha256=digest)


def _context(value: object) -> LoginCompletionContext:
    if not isinstance(value, LoginCompletionContext):
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_WRONG_CONTEXT')
    if not isinstance(value.binding, ManagedCodexAccountBinding):
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_WRONG_CONTEXT')
    return value


def _base_inventory(binding: ManagedCodexAccountBinding) -> dict[str, Any]:
    try:
        base = read_restart_manifest(binding.inventory)
    except Exception as exc:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_BASE_REQUIRED') from exc
    if base.get('auth_extension') is not None:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_BASE_NOT_BASELINE')
    return base


def _cleanup_evidence(client: object) -> dict[str, bool]:
    if not isinstance(client, ManagedCodexAccountClient):
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_CLEANUP_REQUIRED')
    try:
        evidence = client.cleanup_evidence()
    except Exception as exc:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_CLEANUP_REQUIRED') from exc
    required = ('session_closed', 'transport_closed', 'exited', 'job_closed',
                'stderr_drain_complete')
    if not isinstance(evidence, dict) or not all(evidence.get(key) is True for key in required):
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_CLEANUP_REQUIRED')
    return evidence


def _check_completion(ctx: LoginCompletionContext) -> None:
    if (not isinstance(ctx.login_id, str) or not ctx.login_id
            or not isinstance(ctx.mode, str) or not ctx.mode
            or not isinstance(ctx.completed, dict)
            or ctx.completed.get('success') is not True
            or ctx.completed.get('loginId') != ctx.login_id):
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_COMPLETION_MISMATCH')


def _check_binding(binding: ManagedCodexAccountBinding, base: dict[str, Any]) -> None:
    try:
        codex, bindings = base['codex'], base['bindings']
        valid = (
            codex['version'] == binding.codex_version
            and codex['executable_sha256'] == binding.executable_sha256
            and bindings['home_identity'] == binding.profile.home_identity.to_json_dict()
            and bindings['workspace_identity'] == binding.profile.workspace_identity.to_json_dict()
            and bindings['config_sha256'] == binding.profile.config_sha256
        )
    except Exception:
        valid = False
    if not valid:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_BINDING_MISMATCH')


def _check_auth_policy(profile: object, base: dict[str, Any]) -> None:
    base_roots = {row['path'].casefold() for row in base['root_entries']}
    if 'auth.json' in base_roots:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_BASE_NOT_BASELINE')
    home = Path(profile.home)
    try:
        actual = {item.name.casefold() for item in home.iterdir()}
    except OSError as exc:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_AUTH_POLICY_REQUIRED') from exc
    expected = set(base_roots) | {'auth.json'}
    if 'auth.json' not in actual:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_AUTH_POLICY_REQUIRED')
    if actual != expected:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_AUTH_ROOT_MISMATCH')
    _check_auth_json(home / 'auth.json')


def _check_auth_json(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_AUTH_POLICY_REQUIRED') from exc
    reparse = bool(getattr(info, 'st_file_attributes', 0)
                   & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))
    if (not stat.S_ISREG(info.st_mode) or reparse
            or getattr(info, 'st_nlink', 1) != 1):
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_AUTH_PATH_UNSAFE')
    if info.st_size > MAX_AUTH_METADATA:
        raise CodexManagedLoginReceiptWriterError('LOGIN_RECEIPT_AUTH_TOO_LARGE')
