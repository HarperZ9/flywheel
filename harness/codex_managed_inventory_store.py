"""Safe store reads for managed Codex accepted inventories."""
from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from typing import Any

from .codex_managed_profile_manifest import CodexProfileInventoryRef, read_restart_manifest, verify_restart_inventory
from .evidence_json import strict_load_json
from .private_artifact_fs import PrivateArtifactError, open_artifact_root

BASELINE_REF_SCHEMA = 'flywheel.codex-managed-baseline-inventory-ref/v1'
_HEX64_JSON = re.compile(r'[0-9a-f]{64}\.json')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_MAX_RECORD = 262_144
_MAX_ACCEPTED = 64


class CodexManagedInventoryStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def accepted_inventory_records(policy_root: Path, binding_sha: str) -> list[dict[str, Any]]:
    rel = f'codex-policy/{binding_sha}/accepted-inventories'
    try:
        with open_artifact_root(policy_root, writable=False) as root:
            names = root.list_names(rel, max_entries=_MAX_ACCEPTED)
            out = []
            for name in sorted(names, key=str.casefold):
                if not _HEX64_JSON.fullmatch(name):
                    raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
                out.append(strict_load_json(root.read_bytes(f'{rel}/{name}', max_bytes=_MAX_RECORD),
                                            max_bytes=_MAX_RECORD, max_depth=24))
            return out
    except CodexManagedInventoryStoreError:
        raise
    except PrivateArtifactError as exc:
        if exc.code == 'NOT_FOUND':
            return []
        raise CodexManagedInventoryStoreError('BASELINE_POLICY_READ_' + exc.code) from exc
    except ValueError as exc:
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED') from exc


def record_ref(record: dict[str, Any], *, binding: dict[str, Any], binding_sha: str,
               policy_root: Path) -> CodexProfileInventoryRef:
    if (record.get('schema') != BASELINE_REF_SCHEMA or record.get('binding_sha256') != binding_sha
            or record.get('binding') != binding):
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
    inv = record.get('inventory')
    if type(inv) is not dict:
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
    return CodexProfileInventoryRef(path=policy_root / _safe_rel(inv.get('path')),
                                    sha256=_hex(inv.get('sha256')))


def inventory_matches(profile, ref: CodexProfileInventoryRef, *, policy_root: Path, executable: Path,
                      executable_sha256: str, configured_version: str) -> bool:
    try:
        if not isinstance(ref, CodexProfileInventoryRef):
            raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
        _hex(ref.sha256)
        policy_rel(policy_root, ref.path)
        manifest = read_restart_manifest(ref)
        if manifest['codex']['version'] != configured_version:
            raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
        verify_restart_inventory(profile, ref, executable=executable, executable_sha256=executable_sha256)
        return True
    except CodexManagedInventoryStoreError:
        raise
    except Exception as exc:
        if getattr(exc, 'code', '') == 'MANIFEST_ROOT_MISMATCH':
            return False
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED') from exc


def policy_rel(policy_root: Path, path: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
    try:
        return candidate.resolve(strict=False).relative_to(Path(policy_root).resolve(strict=True)).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED') from exc


def _safe_rel(value: object) -> str:
    if type(value) is not str or not value:
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
    windows = PureWindowsPath(value)
    if (Path(value).is_absolute() or windows.is_absolute() or windows.drive or windows.root
            or any(part in {'', '.', '..'} for part in value.replace('\\', '/').split('/'))):
        raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
    return value


def _hex(value: object) -> str:
    if type(value) is str and _HEX64.fullmatch(value):
        return value
    raise CodexManagedInventoryStoreError('BASELINE_INVENTORY_REJECTED')
