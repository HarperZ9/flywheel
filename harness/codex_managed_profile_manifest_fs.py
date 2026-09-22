"""Filesystem helpers for Codex profile restart manifests."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import stat
from typing import Any

from .private_artifact_fs import PrivateArtifactError, open_artifact_root

_REPARSE_ATTRIBUTE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
_HEX64 = re.compile(r'[0-9a-f]{64}')
_FILE_POLICIES = {'exact_sha256', 'provider_metadata_only', 'sqlite_metadata_only', 'auth_metadata_only'}
_DIR_POLICIES = {
    'harness_runtime_tree', 'empty_or_harness_owned_temp',
    'codex_arg0_temp_tree', 'exact_builtin_tree',
}
_ARG0_DIR = re.compile(r'codex-arg0[0-9A-Za-z]{6}')
_ARG0_FILES = {'.lock', 'apply_patch.bat', 'applypatch.bat'}


class ManifestFilesystemError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TreeSnapshot:
    dirs: list[str]
    files: list[dict[str, Any]]


def read_policy_file(path: Path, *, max_bytes: int) -> bytes:
    path = Path(path)
    if not path.is_absolute() or path.name in {'', '.', '..'}:
        raise ManifestFilesystemError('MANIFEST_INVALID_REF')
    try:
        with open_artifact_root(path.parent, writable=False) as root:
            return root.read_bytes(path.name, max_bytes=max_bytes)
    except PrivateArtifactError as exc:
        raise ManifestFilesystemError('MANIFEST_POLICY_READ_' + exc.code) from exc


def file_stat(path: Path) -> os.stat_result:
    try:
        info = Path(path).lstat()
    except OSError as exc:
        raise ManifestFilesystemError('MANIFEST_FILE_UNSAFE') from exc
    if (not stat.S_ISREG(info.st_mode) or is_reparse(info)
            or getattr(info, 'st_nlink', 1) != 1):
        raise ManifestFilesystemError('MANIFEST_FILE_UNSAFE')
    return info


def sha256_file(path: Path, *, max_bytes: int) -> str:
    info = file_stat(path)
    if info.st_size > max_bytes:
        raise ManifestFilesystemError('MANIFEST_FILE_TOO_LARGE')
    try:
        with Path(path).open('rb') as source:
            return hashlib.file_digest(source, 'sha256').hexdigest()
    except OSError as exc:
        raise ManifestFilesystemError('MANIFEST_FILE_UNSAFE') from exc


def dir_names(path: Path, *, max_entries: int = 1000) -> list[str]:
    ensure_dir(path)
    try:
        with os.scandir(path) as entries:
            names = sorted((entry.name for entry in entries), key=str.casefold)
    except OSError as exc:
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH') from exc
    if len(names) > max_entries:
        raise ManifestFilesystemError('MANIFEST_TREE_TOO_LARGE')
    return names


def ensure_dir(path: Path) -> None:
    try:
        info = Path(path).lstat()
    except OSError as exc:
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH') from exc
    if not stat.S_ISDIR(info.st_mode) or is_reparse(info):
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')


def ensure_empty_dir(path: Path) -> None:
    if dir_names(path, max_entries=1):
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')


def hashed_tree(root: Path, *, prefix: str, max_file_bytes: int) -> TreeSnapshot:
    ensure_dir(root)
    dirs: list[str] = []
    files: list[dict[str, Any]] = []
    _walk(root, prefix, dirs, files, max_file_bytes)
    return TreeSnapshot(dirs=dirs, files=files)


def metadata_tree(root: Path, *, prefix: str) -> TreeSnapshot:
    ensure_dir(root)
    dirs: list[str] = []
    files: list[dict[str, Any]] = []
    _walk(root, prefix, dirs, files, None)
    return TreeSnapshot(dirs=dirs, files=files)


def codex_arg0_temp_tree(root: Path, *, max_file_bytes: int,
                         executable: Path) -> dict[str, Any] | None:
    names = dir_names(root)
    if not names:
        return None
    if names != ['arg0']:
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')
    arg0 = root / 'arg0'
    arg0_names = dir_names(arg0)
    if len(arg0_names) != 1 or not _ARG0_DIR.fullmatch(arg0_names[0]):
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')
    leaf = arg0 / arg0_names[0]
    if set(dir_names(leaf)) != _ARG0_FILES:
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')
    _validate_arg0_files(leaf, executable, max_file_bytes)
    tree = hashed_tree(root, prefix='tmp', max_file_bytes=max_file_bytes)
    expected_dirs = ['tmp/arg0', f'tmp/arg0/{arg0_names[0]}']
    if tree.dirs != expected_dirs:
        raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')
    return {'dirs': tree.dirs, 'files': tree.files}
def validate_codex_arg0_temp_tree(tree: object, *, max_file_bytes: int) -> None:
    tree = _dict(tree)
    dirs, files = tree.get('dirs'), tree.get('files')
    if type(dirs) is not list or type(files) is not list or len(dirs) != 2:
        raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
    if dirs[0] != 'tmp/arg0' or not dirs[1].startswith('tmp/arg0/'):
        raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
    leaf = dirs[1].removeprefix('tmp/arg0/')
    if '/' in leaf or not _ARG0_DIR.fullmatch(leaf):
        raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
    expected = {f'tmp/arg0/{leaf}/{name}' for name in _ARG0_FILES}
    seen: set[str] = set()
    for row in files:
        row = _dict(row)
        path = row.get('path')
        if path not in expected or path in seen:
            raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
        seen.add(path)
        if (type(row.get('size')) is not int or row['size'] < 0
                or row['size'] > max_file_bytes or not _hex(row.get('sha256'))):
            raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
    if seen != expected:
        raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
def _validate_arg0_files(leaf: Path, executable: Path, max_file_bytes: int) -> None:
    shim = _apply_patch_shim(executable)
    for name, expected in {'.lock': b'', 'apply_patch.bat': shim, 'applypatch.bat': shim}.items():
        info = file_stat(leaf / name)
        if info.st_size > max_file_bytes or info.st_size != len(expected):
            raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')
        try:
            actual = (leaf / name).read_bytes()
        except OSError as exc:
            raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH') from exc
        if actual != expected:
            raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')
def _apply_patch_shim(executable: Path) -> bytes:
    executable = Path(executable)
    if not executable.is_absolute():
        raise ManifestFilesystemError('MANIFEST_INVALID_REF')
    return f'@echo off\n"{executable}" --codex-run-as-apply-patch %*\n'.encode('utf-8')
def _walk(root: Path, prefix: str, dirs: list[str], files: list[dict[str, Any]],
          max_file_bytes: int | None) -> None:
    for name in dir_names(root):
        child = root / name
        rel = prefix + '/' + name
        try:
            info = child.lstat()
        except OSError as exc:
            raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH') from exc
        if is_reparse(info):
            raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')
        if stat.S_ISDIR(info.st_mode):
            dirs.append(rel)
            _walk(child, rel, dirs, files, max_file_bytes)
        elif stat.S_ISREG(info.st_mode):
            if getattr(info, 'st_nlink', 1) != 1:
                raise ManifestFilesystemError('MANIFEST_FILE_UNSAFE')
            files.append(_file_row(child, rel, info, max_file_bytes))
        else:
            raise ManifestFilesystemError('MANIFEST_TREE_MISMATCH')


def _file_row(path: Path, rel: str, info: os.stat_result,
              max_file_bytes: int | None) -> dict[str, Any]:
    if max_file_bytes is None:
        return {'path': rel, 'kind': 'file', 'max_bytes': max(info.st_size, 4096)}
    if info.st_size > max_file_bytes:
        raise ManifestFilesystemError('MANIFEST_BUILTIN_TOO_LARGE')
    return {'path': rel, 'size': info.st_size,
            'sha256': sha256_file(path, max_bytes=max_file_bytes)}


def is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, 'st_file_attributes', 0) & _REPARSE_ATTRIBUTE)


def validate_root_entry(row: object, seen: set[str], *, meta_files: set[str],
                        sqlite_files: set[str], auth_files: set[str],
                        max_text: int, max_sqlite: int, max_auth: int) -> None:
    row = _dict(row)
    path, kind, policy = row.get('path'), row.get('kind'), row.get('policy')
    if not _safe_rel(path) or '/' in path or '\\' in path or path.casefold() in seen:
        raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
    seen.add(path.casefold())
    if kind == 'file' and policy in _FILE_POLICIES:
        _validate_file_policy(row, path, policy, meta_files, sqlite_files, auth_files,
                              max_text, max_sqlite, max_auth)
    elif kind == 'dir' and policy in _DIR_POLICIES:
        _validate_dir_policy(path, policy)
    else:
        raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')


def validate_builtin_tree(tree: object) -> None:
    tree = _dict(tree)
    if tree.get('root') != 'skills/.system' or type(tree.get('files')) is not list or type(tree.get('dirs')) is not list:
        raise ManifestFilesystemError('MANIFEST_INVALID_BUILTINS')
    seen: set[str] = set()
    for item in tree['dirs']:
        if not _safe_tree_path(item, seen):
            raise ManifestFilesystemError('MANIFEST_INVALID_BUILTINS')
    for row in tree['files']:
        row = _dict(row)
        if (not _safe_tree_path(row.get('path'), seen) or type(row.get('size')) is not int
                or row['size'] < 0 or not _hex(row.get('sha256'))):
            raise ManifestFilesystemError('MANIFEST_INVALID_BUILTINS')
def _validate_file_policy(row: dict[str, Any], path: str, policy: str, meta_files: set[str],
                          sqlite_files: set[str], auth_files: set[str], max_text: int,
                          max_sqlite: int, max_auth: int) -> None:
    if path == 'config.toml' and policy == 'exact_sha256' and _hex(row.get('sha256')):
        return
    limit = 1024 * 1024 if path == 'models_cache.json' else max_text
    if path in meta_files and policy == 'provider_metadata_only' and _valid_max(row, limit):
        return
    if path in sqlite_files and policy == 'sqlite_metadata_only' and _valid_max(row, max_sqlite):
        return
    if path in auth_files and policy == 'auth_metadata_only' and _valid_max(row, max_auth):
        return
    raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
def _validate_dir_policy(path: str, policy: str) -> None:
    allowed = {'runtime': {'harness_runtime_tree'},
               'tmp': {'empty_or_harness_owned_temp', 'codex_arg0_temp_tree'},
               'skills': 'exact_builtin_tree'}
    expected = allowed.get(path)
    if expected is None:
        raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
    if isinstance(expected, set):
        if policy in expected:
            return
    elif expected == policy:
        return
    raise ManifestFilesystemError('MANIFEST_INVALID_ROOTS')
def _safe_tree_path(value: object, seen: set[str]) -> bool:
    if not _safe_rel(value) or not value.startswith('skills/.system/'):
        return False
    key = value.casefold()
    if key in seen:
        return False
    seen.add(key)
    return True
def _safe_rel(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    windows = PureWindowsPath(value)
    parts = value.replace('\\', '/').split('/')
    return not (Path(value).is_absolute() or windows.is_absolute() or windows.drive or windows.root
                or any(part in {'', '.', '..'} for part in parts)
                or any(char in value for char in '*?[]:'))
def _valid_max(row: dict[str, Any], limit: int) -> bool:
    value = row.get('max_bytes')
    return type(value) is int and not isinstance(value, bool) and 0 <= value <= limit
def _dict(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ManifestFilesystemError('MANIFEST_INVALID_SCHEMA')
    return value
def _hex(value: object) -> bool:
    return type(value) is str and bool(_HEX64.fullmatch(value))
