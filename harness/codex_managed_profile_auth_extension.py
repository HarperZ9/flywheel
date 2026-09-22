"""Manifest extension for post-login Codex auth metadata."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .evidence_json import canonical_bytes, canonical_sha256
from .private_artifact_fs import PrivateArtifactError, open_artifact_root
from .codex_managed_profile_auth_receipt import (
    CodexProfileLoginReceiptError,
    CodexProfileLoginReceiptRef,
    read_login_receipt,
)

AUTH_EXTENSION_SCHEMA = 'flywheel.codex-managed-profile-auth-extension/v1'


def extend_manifest_after_explicit_login(profile, inventory, *, executable: Path,
                                         executable_sha256: str, codex_version: str,
                                         login_receipt: CodexProfileLoginReceiptRef,
                                         policy_root: Path, expected_login_id: str | None = None,
                                         expected_mode: str | None = None):
    from . import codex_managed_profile_manifest as manifest
    try:
        receipt = read_login_receipt(login_receipt)
    except CodexProfileLoginReceiptError as exc:
        raise manifest.CodexProfileManifestError(exc.code) from exc
    executable, policy_root = Path(executable), Path(policy_root)
    base = manifest.read_restart_manifest(inventory)
    _check_binding(manifest, profile, base, executable, executable_sha256, codex_version)
    _check_receipt(manifest, profile, inventory, receipt, executable_sha256, codex_version,
                   expected_login_id, expected_mode)
    if manifest._overlaps(policy_root, profile.home):
        raise manifest.CodexProfileManifestError('MANIFEST_POLICY_OVERLAP')
    root_rows = _refresh_dynamic_root_rows(manifest, profile, base['root_entries'],
                                           executable)
    base_rows = {row['path'].casefold(): row for row in root_rows}
    auth_rows = _auth_rows(manifest, profile, receipt, base_rows)
    actual = {name.casefold(): name for name in manifest._dir_names(profile.home)}
    expected = set(base_rows) | {row['path'].casefold() for row in auth_rows}
    if set(actual) != expected:
        raise manifest.CodexProfileManifestError('MANIFEST_ROOT_MISMATCH')
    if manifest._sha256_file(profile.home / 'config.toml', max_bytes=manifest._MAX_TEXT_META) != profile.config_sha256:
        raise manifest.CodexProfileManifestError('MANIFEST_CONFIG_DRIFT')
    for key, row in base_rows.items():
        manifest._verify_entry(profile.home / actual[key], row, executable)
    manifest._verify_builtin_tree(profile.home, base['builtin_tree'])
    extended = dict(base)
    extended['root_entries'] = root_rows + auth_rows
    extended['auth_extension'] = {
        'schema': AUTH_EXTENSION_SCHEMA,
        'source_inventory_sha256': inventory.sha256,
        'login_receipt_sha256': login_receipt.sha256,
        'content_read': False,
        'exact_paths_only': True,
        'auth_paths': [row['path'] for row in auth_rows],
    }
    data = manifest.validate_restart_manifest(extended)
    digest = canonical_sha256(data)
    rel = f'codex-policy/{digest}/restart-manifest.json'
    payload = canonical_bytes(data)
    try:
        with open_artifact_root(policy_root) as root:
            root.write_new_or_same(rel, payload)
    except PrivateArtifactError as exc:
        raise manifest.CodexProfileManifestError('MANIFEST_WRITE_' + exc.code) from exc
    return manifest.CodexProfileInventoryRef(path=policy_root / rel,
                                             sha256=hashlib.sha256(payload).hexdigest())


def _check_binding(manifest, profile, base: dict[str, Any], executable: Path,
                   executable_sha256: str, codex_version: str) -> None:
    if (not manifest._hex(executable_sha256) or type(codex_version) is not str
            or not codex_version.strip() or not executable.is_absolute()):
        raise manifest.CodexProfileManifestError('MANIFEST_INVALID_REQUEST')
    if (base['codex']['executable_sha256'] != executable_sha256
            or base['codex']['version'] != codex_version
            or manifest._sha256_file(executable, max_bytes=manifest._MAX_EXECUTABLE) != executable_sha256):
        raise manifest.CodexProfileManifestError('MANIFEST_EXECUTABLE_MISMATCH')
    bindings = base['bindings']
    if (bindings['home_identity'] != profile.home_identity.to_json_dict()
            or bindings['workspace_identity'] != profile.workspace_identity.to_json_dict()
            or bindings['config_sha256'] != profile.config_sha256):
        raise manifest.CodexProfileManifestError('MANIFEST_BINDING_MISMATCH')


def _check_receipt(manifest, profile, inventory, receipt: dict[str, Any],
                   executable_sha256: str, codex_version: str,
                   expected_login_id: str | None, expected_mode: str | None) -> None:
    if receipt['source_inventory_sha256'] != inventory.sha256:
        raise manifest.CodexProfileManifestError('MANIFEST_BINDING_MISMATCH')
    if (receipt['codex']['executable_sha256'] != executable_sha256
            or receipt['codex']['version'] != codex_version):
        raise manifest.CodexProfileManifestError('MANIFEST_EXECUTABLE_MISMATCH')
    bindings = receipt['bindings']
    if (bindings['home_identity'] != profile.home_identity.to_json_dict()
            or bindings['workspace_identity'] != profile.workspace_identity.to_json_dict()):
        raise manifest.CodexProfileManifestError('MANIFEST_BINDING_MISMATCH')
    if (type(expected_login_id) is not str or not expected_login_id
            or type(expected_mode) is not str or not expected_mode):
        raise manifest.CodexProfileManifestError('MANIFEST_LOGIN_CONTEXT_MISMATCH')
    expected_hash = hashlib.sha256(expected_login_id.encode('utf-8')).hexdigest()
    login = receipt['login']
    if login['mode'] != expected_mode or login['login_id_sha256'] != expected_hash:
        raise manifest.CodexProfileManifestError('MANIFEST_LOGIN_CONTEXT_MISMATCH')


def _auth_rows(manifest, profile, receipt: dict[str, Any], base_rows: dict[str, dict]) -> list[dict[str, Any]]:
    rows = []
    for item in receipt['auth_entries']:
        path = item['path']
        if path.casefold() in base_rows:
            raise manifest.CodexProfileManifestError('MANIFEST_INVALID_ROOTS')
        info = manifest._file_stat(profile.home / path)
        if info.st_size > item['max_bytes']:
            raise manifest.CodexProfileManifestError('MANIFEST_PROVIDER_DATA_TOO_LARGE')
        rows.append({'path': path, 'kind': 'file', 'policy': 'auth_metadata_only',
                     'max_bytes': item['max_bytes']})
    return rows


def _refresh_dynamic_root_rows(manifest, profile, rows, executable: Path) -> list[dict[str, Any]]:
    refreshed = []
    for row in rows:
        if (row.get('path') == 'tmp'
                and row.get('policy') in {'empty_or_harness_owned_temp',
                                           'codex_arg0_temp_tree'}):
            refreshed.append(_current_tmp_row(manifest, profile, executable))
        else:
            refreshed.append(dict(row))
    return refreshed


def _current_tmp_row(manifest, profile, executable: Path) -> dict[str, Any]:
    tree = manifest._from_fs(
        manifest.fs.codex_arg0_temp_tree,
        profile.home / 'tmp',
        max_file_bytes=manifest._MAX_TEXT_META,
        executable=executable)
    if tree is None:
        return {'path': 'tmp', 'kind': 'dir', 'policy': 'empty_or_harness_owned_temp'}
    return {'path': 'tmp', 'kind': 'dir',
            'policy': 'codex_arg0_temp_tree', 'tree': tree}
