"""Restart manifest for generated Codex profile state."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .private_artifact_fs import PrivateArtifactError, open_artifact_root
from .codex_managed_profile_auth_extension import AUTH_EXTENSION_SCHEMA
from .codex_managed_profile_auth_receipt import CodexProfileLoginReceiptRef, LOGIN_RECEIPT_SCHEMA
from . import codex_managed_profile_manifest_fs as fs

MANIFEST_SCHEMA = 'flywheel.codex-managed-profile-restart-manifest/v1'
_HEX64 = re.compile(r'[0-9a-f]{64}')
_META_FILES = {'.personality_migration', 'installation_id', 'models_cache.json'}
_OPTIONAL_META_FILES = {'models_cache.json': 1024 * 1024}
_SQLITE_FILES = {
    'goals_1.sqlite', 'goals_1.sqlite-shm', 'goals_1.sqlite-wal',
    'logs_2.sqlite', 'logs_2.sqlite-shm', 'logs_2.sqlite-wal',
    'memories_1.sqlite', 'memories_1.sqlite-shm', 'memories_1.sqlite-wal',
    'state_5.sqlite', 'state_5.sqlite-shm', 'state_5.sqlite-wal',
}
_MAX_TEXT_META = 4096
_MAX_SQLITE = 256 * 1024 * 1024
_MAX_BUILTIN = 32 * 1024 * 1024
_MAX_MANIFEST = 2_000_000
_MAX_EXECUTABLE = 1024 * 1024 * 1024
_MAX_AUTH = 16 * 1024 * 1024

class CodexProfileManifestError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

@dataclass(frozen=True)
class CodexProfileInventoryRef:
    path: Path
    sha256: str

def manifest_identity(value: Mapping[str, Any]) -> str:
    return canonical_sha256(validate_restart_manifest(value))

def manifest_root_names(value: Mapping[str, Any]) -> set[str]:
    data = validate_restart_manifest(value)
    return {row['path'].casefold() for row in data['root_entries']}

def read_restart_manifest(ref: CodexProfileInventoryRef) -> dict[str, Any]:
    if not isinstance(ref, CodexProfileInventoryRef) or not _hex(ref.sha256):
        raise CodexProfileManifestError('MANIFEST_INVALID_REF')
    raw = _read_policy_file(ref.path)
    if hashlib.sha256(raw).hexdigest() != ref.sha256:
        raise CodexProfileManifestError('MANIFEST_HASH_MISMATCH')
    try:
        return validate_restart_manifest(strict_load_json(raw, max_bytes=_MAX_MANIFEST))
    except ValueError as exc:
        raise CodexProfileManifestError('MANIFEST_INVALID_JSON') from exc


def capture_generated_profile_manifest(profile, *, executable: Path, executable_sha256: str,
                                       codex_version: str, bootstrap_receipt_sha256: str,
                                       policy_root: Path) -> CodexProfileInventoryRef:
    executable, policy_root = Path(executable), Path(policy_root)
    if (not _hex(executable_sha256) or not _hex(bootstrap_receipt_sha256)
            or type(codex_version) is not str or not codex_version.strip()
            or not executable.is_absolute() or not policy_root.is_absolute()):
        raise CodexProfileManifestError('MANIFEST_INVALID_REQUEST')
    if _sha256_file(executable, max_bytes=_MAX_EXECUTABLE) != executable_sha256:
        raise CodexProfileManifestError('MANIFEST_EXECUTABLE_MISMATCH')
    if _overlaps(policy_root, profile.home):
        raise CodexProfileManifestError('MANIFEST_POLICY_OVERLAP')
    if _sha256_file(profile.home / 'config.toml', max_bytes=_MAX_TEXT_META) != profile.config_sha256:
        raise CodexProfileManifestError('MANIFEST_CONFIG_DRIFT')
    entries, builtin = _capture_entries(profile.home, profile.config_sha256, executable)
    manifest = validate_restart_manifest({
        'schema': MANIFEST_SCHEMA,
        'codex': {'version': codex_version, 'executable_sha256': executable_sha256},
        'bindings': {
            'home_identity': profile.home_identity.to_json_dict(),
            'workspace_identity': profile.workspace_identity.to_json_dict(),
            'config_sha256': profile.config_sha256,
        },
        'bootstrap': {'receipt_sha256': bootstrap_receipt_sha256},
        'root_entries': entries,
        'builtin_tree': builtin,
        'dynamic_provider_files': {'content_read': False, 'exact_names_only': True},
    })
    digest = canonical_sha256(manifest)
    rel = f'codex-policy/{digest}/restart-manifest.json'
    payload = canonical_bytes(manifest)
    try:
        with open_artifact_root(policy_root) as root:
            root.write_new_or_same(rel, payload)
    except PrivateArtifactError as exc:
        raise CodexProfileManifestError('MANIFEST_WRITE_' + exc.code) from exc
    return CodexProfileInventoryRef(path=policy_root / rel, sha256=hashlib.sha256(payload).hexdigest())


def verify_restart_inventory(profile, inventory: CodexProfileInventoryRef, *,
                             executable: Path, executable_sha256: str) -> None:
    manifest = read_restart_manifest(inventory)
    if (manifest['codex']['executable_sha256'] != executable_sha256
            or _sha256_file(Path(executable), max_bytes=_MAX_EXECUTABLE) != executable_sha256):
        raise CodexProfileManifestError('MANIFEST_EXECUTABLE_MISMATCH')
    bindings = manifest['bindings']
    if (bindings['home_identity'] != profile.home_identity.to_json_dict()
            or bindings['workspace_identity'] != profile.workspace_identity.to_json_dict()
            or bindings['config_sha256'] != profile.config_sha256):
        raise CodexProfileManifestError('MANIFEST_BINDING_MISMATCH')
    expected = {row['path'].casefold(): row for row in manifest['root_entries']}
    actual = {name.casefold(): name for name in _dir_names(profile.home)}
    extra = set(actual) - set(expected)
    if set(expected) - set(actual) or extra - set(_OPTIONAL_META_FILES):
        raise CodexProfileManifestError('MANIFEST_ROOT_MISMATCH')
    for key in sorted(extra):
        _verify_entry(profile.home / actual[key], {'path': actual[key], 'kind': 'file',
            'policy': 'provider_metadata_only', 'max_bytes': _OPTIONAL_META_FILES[key]}, executable)
    if _sha256_file(profile.home / 'config.toml', max_bytes=_MAX_TEXT_META) != profile.config_sha256:
        raise CodexProfileManifestError('MANIFEST_CONFIG_DRIFT')
    for key, row in expected.items():
        _verify_entry(profile.home / actual[key], row, executable)
    _verify_builtin_tree(profile.home, manifest['builtin_tree'])


def verify_clean_profile_root(profile) -> None:
    actual = {name.casefold() for name in _dir_names(profile.home)}
    if actual != {'config.toml', 'runtime'}:
        raise CodexProfileManifestError('MANIFEST_ROOT_MISMATCH')
    if _sha256_file(profile.home / 'config.toml', max_bytes=_MAX_TEXT_META) != profile.config_sha256:
        raise CodexProfileManifestError('MANIFEST_CONFIG_DRIFT')
    _verify_runtime_tree(profile.home / 'runtime')


def validate_restart_manifest(value: object) -> dict[str, Any]:
    if type(value) is not dict or value.get('schema') != MANIFEST_SCHEMA:
        raise CodexProfileManifestError('MANIFEST_INVALID_SCHEMA')
    data = dict(value)
    codex, bindings = _dict(data.get('codex')), _dict(data.get('bindings'))
    if type(codex.get('version')) is not str or not codex['version'].strip():
        raise CodexProfileManifestError('MANIFEST_INVALID_CODEX')
    if not _hex(codex.get('executable_sha256')):
        raise CodexProfileManifestError('MANIFEST_INVALID_CODEX')
    if not _identity(bindings.get('home_identity')) or not _identity(bindings.get('workspace_identity')):
        raise CodexProfileManifestError('MANIFEST_INVALID_BINDING')
    if not _hex(bindings.get('config_sha256')):
        raise CodexProfileManifestError('MANIFEST_INVALID_BINDING')
    if not _hex(_dict(data.get('bootstrap')).get('receipt_sha256')):
        raise CodexProfileManifestError('MANIFEST_INVALID_BOOTSTRAP')
    roots = data.get('root_entries')
    if type(roots) is not list or not roots:
        raise CodexProfileManifestError('MANIFEST_INVALID_ROOTS')
    auth_files = _auth_files(data.get('auth_extension'))
    seen: set[str] = set()
    for row in roots:
        _validate_root_entry(row, seen, auth_files)
        if type(row) is dict and row.get('policy') == 'codex_arg0_temp_tree':
            _from_fs(fs.validate_codex_arg0_temp_tree, row.get('tree'), max_file_bytes=_MAX_TEXT_META)
    if not {'config.toml', 'runtime'}.issubset(seen):
        raise CodexProfileManifestError('MANIFEST_INVALID_ROOTS')
    _validate_builtin_tree(data.get('builtin_tree'))
    dynamic = _dict(data.get('dynamic_provider_files'))
    if dynamic.get('content_read') is not False or dynamic.get('exact_names_only') is not True:
        raise CodexProfileManifestError('MANIFEST_INVALID_DYNAMIC_POLICY')
    return data

def extend_manifest_after_explicit_login(*args, **kwargs) -> CodexProfileInventoryRef:
    from .codex_managed_profile_auth_extension import extend_manifest_after_explicit_login as _extend; return _extend(*args, **kwargs)

def _capture_entries(home: Path, config_hash: str, executable: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    builtin = {'root': 'skills/.system', 'files': [], 'dirs': []}
    for name in _dir_names(home):
        path = home / name
        if name == 'config.toml':
            info = _file_stat(path)
            entries.append({'path': name, 'kind': 'file', 'policy': 'exact_sha256',
                            'sha256': config_hash, 'size': info.st_size})
        elif name == 'runtime':
            _verify_runtime_tree(path)
            entries.append({'path': name, 'kind': 'dir', 'policy': 'harness_runtime_tree'})
        elif name == 'tmp':
            tree = _from_fs(fs.codex_arg0_temp_tree, path, max_file_bytes=_MAX_TEXT_META,
                            executable=executable)
            if tree is None:
                entries.append({'path': name, 'kind': 'dir', 'policy': 'empty_or_harness_owned_temp'})
            else:
                entries.append({'path': name, 'kind': 'dir',
                                'policy': 'codex_arg0_temp_tree', 'tree': tree})
        elif name == 'skills':
            entries.append({'path': name, 'kind': 'dir', 'policy': 'exact_builtin_tree'})
            builtin = _capture_builtin_tree(path / '.system')
        elif name in _META_FILES:
            limit = _OPTIONAL_META_FILES.get(name, _MAX_TEXT_META)
            if _file_stat(path).st_size > limit:
                raise CodexProfileManifestError('MANIFEST_UNKNOWN_GENERATED_ENTRY')
            entries.append({'path': name, 'kind': 'file', 'policy': 'provider_metadata_only', 'max_bytes': limit})
        elif name in _SQLITE_FILES:
            if _file_stat(path).st_size > _MAX_SQLITE:
                raise CodexProfileManifestError('MANIFEST_PROVIDER_DATA_TOO_LARGE')
            entries.append({'path': name, 'kind': 'file', 'policy': 'sqlite_metadata_only',
                            'max_bytes': _MAX_SQLITE})
        else:
            raise CodexProfileManifestError('MANIFEST_UNKNOWN_GENERATED_ENTRY')
    return entries, builtin


def _verify_entry(path: Path, row: Mapping[str, Any], executable: Path) -> None:
    policy, kind = row['policy'], row['kind']
    if kind == 'dir':
        if policy == 'harness_runtime_tree':
            _verify_runtime_tree(path)
        elif policy == 'empty_or_harness_owned_temp':
            _ensure_empty_dir(path)
        elif policy == 'codex_arg0_temp_tree':
            _from_fs(fs.codex_arg0_temp_tree, path, max_file_bytes=_MAX_TEXT_META,
                     executable=executable)
        elif policy == 'exact_builtin_tree' and _dir_names(path) != ['.system']:
            raise CodexProfileManifestError('MANIFEST_BUILTIN_MISMATCH')
        return
    info = _file_stat(path)
    if policy == 'exact_sha256':
        if _sha256_file(path, max_bytes=_MAX_TEXT_META) != row.get('sha256'):
            raise CodexProfileManifestError('MANIFEST_FILE_HASH_MISMATCH')
    elif policy in {'provider_metadata_only', 'sqlite_metadata_only', 'auth_metadata_only'}:
        if info.st_size > row.get('max_bytes', -1):
            raise CodexProfileManifestError('MANIFEST_PROVIDER_DATA_TOO_LARGE')


def _capture_builtin_tree(root: Path) -> dict[str, Any]:
    if _dir_names(root.parent) != ['.system']:
        raise CodexProfileManifestError('MANIFEST_BUILTIN_MISMATCH')
    tree = _hashed_tree(root, prefix='skills/.system', max_file_bytes=_MAX_BUILTIN)
    return {'root': 'skills/.system', 'files': tree.files, 'dirs': tree.dirs}


def _verify_builtin_tree(home: Path, tree: Mapping[str, Any]) -> None:
    if 'skills' not in _dir_names(home):
        if tree.get('files') or tree.get('dirs'):
            raise CodexProfileManifestError('MANIFEST_BUILTIN_MISMATCH')
        return
    if _capture_builtin_tree(home / 'skills' / '.system') != tree:
        raise CodexProfileManifestError('MANIFEST_BUILTIN_MISMATCH')


def _verify_runtime_tree(root: Path) -> None:
    if _dir_names(root) != ['Temp'] or _dir_names(root / 'Temp') != ['.flywheel-owned']:
        raise CodexProfileManifestError('MANIFEST_TREE_MISMATCH')
    if _file_stat(root / 'Temp' / '.flywheel-owned').st_size != 0:
        raise CodexProfileManifestError('MANIFEST_TREE_MISMATCH')


def _dict(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise CodexProfileManifestError('MANIFEST_INVALID_SCHEMA')
    return value
def _identity(value: object) -> bool:
    return (type(value) is dict and value.get('platform') in {'windows', 'posix'}
            and type(value.get('device')) is int and type(value.get('inode')) is int)
def _hex(value: object) -> bool:
    return type(value) is str and bool(_HEX64.fullmatch(value))
def _overlaps(policy_root: Path, home: Path) -> bool:
    policy_root, home = policy_root.resolve(), home.resolve()
    return policy_root == home or policy_root.is_relative_to(home)
def _from_fs(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except fs.ManifestFilesystemError as exc:
        raise CodexProfileManifestError(exc.code) from exc
def _read_policy_file(path: Path) -> bytes:
    return _from_fs(fs.read_policy_file, Path(path), max_bytes=_MAX_MANIFEST)
def _file_stat(path: Path):
    return _from_fs(fs.file_stat, path)
def _sha256_file(path: Path, *, max_bytes: int) -> str:
    return _from_fs(fs.sha256_file, path, max_bytes=max_bytes)
def _dir_names(path: Path) -> list[str]:
    return _from_fs(fs.dir_names, path)
def _ensure_empty_dir(path: Path) -> None:
    _from_fs(fs.ensure_empty_dir, path)
def _hashed_tree(path: Path, *, prefix: str, max_file_bytes: int):
    return _from_fs(fs.hashed_tree, path, prefix=prefix, max_file_bytes=max_file_bytes)
def _auth_files(extension: object) -> set[str]:
    if extension is None:
        return set()
    ext = _dict(extension)
    if (ext.get('schema') != AUTH_EXTENSION_SCHEMA or not _hex(ext.get('source_inventory_sha256'))
            or not _hex(ext.get('login_receipt_sha256')) or ext.get('content_read') is not False
            or ext.get('exact_paths_only') is not True or type(ext.get('auth_paths')) is not list):
        raise CodexProfileManifestError('MANIFEST_INVALID_AUTH_EXTENSION')
    paths = ext['auth_paths']
    if not paths or any(type(path) is not str for path in paths):
        raise CodexProfileManifestError('MANIFEST_INVALID_AUTH_EXTENSION')
    return set(paths)
def _validate_root_entry(row: object, seen: set[str], auth_files: set[str]) -> None:
    _from_fs(fs.validate_root_entry, row, seen, meta_files=_META_FILES,
             sqlite_files=_SQLITE_FILES, auth_files=auth_files, max_text=_MAX_TEXT_META,
             max_sqlite=_MAX_SQLITE, max_auth=_MAX_AUTH)
def _validate_builtin_tree(tree: object) -> None:
    _from_fs(fs.validate_builtin_tree, tree)
