"""Bind native MCP archives to the exact installer stage and frozen collection."""
from __future__ import annotations
import ast
import hashlib
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess

from desktop.tool.installed_payload_binding import _scan_files, sha256_file
from harness.path_identity import reserved_device_name

VERSION = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+')
FORBIDDEN = {'.git', '.env', 'private', 'protected', 'secrets', 'state', '__pycache__'}


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('unsafe payload name')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('unsafe payload name')
    if reserved_device_name(name, windows=True) or any(p.endswith((' ', '.')) for p in path.parts):
        raise ValueError('Windows device or aliased payload name')
    if any(p.casefold() in FORBIDDEN or p.casefold().startswith('.env') for p in path.parts):
        raise ValueError('private or credential payload name')
    if any(ord(ch) < 32 for ch in name) or path.suffix.casefold() in {
            '.pem', '.key', '.pfx', '.p12', '.sqlite', '.db', '.token', '.jks', '.keystore'}:
        raise ValueError('unsupported native payload name')
    return name


def source_identity(repo, version, *, dev=False):
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError('invalid version')
    def git(*args, check=True):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                text=True, check=check)
        return result.stdout.strip()
    head = git('rev-parse', 'HEAD')
    dirty = bool(git('status', '--porcelain', '--untracked-files=all'))
    if not dev:
        if dirty:
            raise ValueError('release source must be clean')
        tag = git('rev-parse', '--verify', f'refs/tags/v{version}^{{commit}}', check=False)
        if tag != head:
            raise ValueError('release source must be the exact version tag')
    return {'head': head, 'version': version, 'mode': 'development' if dev else 'release',
            'source_dirty': dirty}


def validate_executable(path):
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise ValueError('native payload is not Windows PE')
        offset = struct.unpack_from('<I', header, 60)[0]
        if offset > path.stat().st_size - 6:
            raise ValueError('invalid Windows executable')
        stream.seek(offset)
        if stream.read(6) != b'PE\0\0\x64\x86':
            raise ValueError('native payload must be Windows x64')


def bind_payload(engine, installer_engine, collect_toc):
    engine, installer_engine = Path(engine), Path(installer_engine)
    actual, installer = dict(_scan_files(engine)), dict(_scan_files(installer_engine))
    if set(actual) != set(installer):
        raise ValueError('installer engine file set differs')
    try:
        collection, = ast.literal_eval(Path(collect_toc).read_text(encoding='utf-8'))
    except (ValueError, SyntaxError, TypeError) as exc:
        raise ValueError('invalid frozen collection record') from exc
    expected = {}
    for row in collection:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError('invalid frozen collection row')
        name, source, kind = row
        # PyInstaller's trusted local TOC records Windows separators. Archive
        # paths remain strict POSIX names; normalize only this build input.
        if isinstance(name, str):
            name = name.replace('\\', '/')
        safe_name(name)
        if kind not in {'EXECUTABLE', 'BINARY', 'EXTENSION', 'DATA'}:
            raise ValueError('unsupported frozen collection kind')
        relative = name if kind == 'EXECUTABLE' else '_internal/' + name
        if kind == 'EXECUTABLE' and name != 'flywheel-gateway.exe':
            raise ValueError('unsupported top-level executable')
        safe_name(relative)
        if relative.casefold() in {key.casefold() for key in expected}:
            raise ValueError('duplicate frozen collection destination')
        expected[relative] = Path(source)
    if set(actual) != set(expected):
        raise ValueError('staged engine differs from frozen collection')
    if 'flywheel-gateway.exe' not in actual:
        raise ValueError('gateway executable missing')
    validate_executable(actual['flywheel-gateway.exe'])
    rows = []
    for name, path in sorted(actual.items()):
        safe_name(name)
        digest = sha256_file(path)
        if digest != sha256_file(installer[name]):
            raise ValueError('installer engine bytes differ: ' + name)
        if digest != sha256_file(expected[name]):
            raise ValueError('frozen collection source bytes differ: ' + name)
        rows.append({'path': name, 'sha256': digest, 'size': path.stat().st_size})
    return rows
