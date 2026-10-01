"""Bind source packaging inputs to immutable Git blobs, not index status flags."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.source_tool_payload import REVIEW, TEMPLATE, TEMPLATE_FILES, read_public

CODE_INPUTS = ('scripts/build_source_tool_plugin.py', 'scripts/source_tool_payload.py',
    'scripts/source_tool_manifests.py', 'scripts/source_tool_provenance.py',
    'scripts/native_mcp_payload.py', 'desktop/tool/installed_payload_binding.py')


def input_paths(repo):
    paths = {*json.loads(REVIEW.read_text(encoding='utf-8')), 'pyproject.toml', 'LICENSE',
             'scripts/source_tool_closure.json', *CODE_INPUTS,
             *(TEMPLATE + '/' + name for name in TEMPLATE_FILES)}
    for name in ('scripts/__init__.py', 'desktop/__init__.py', 'desktop/tool/__init__.py'):
        if (Path(repo) / name).exists():
            paths.add(name)
    return sorted(paths)


def _git(repo, *args, input=None):
    return subprocess.run(['git', '--no-replace-objects', '-C', str(repo), *args],
                          input=input, capture_output=True, check=True).stdout


def check_inputs(repo, head, paths, *, release, snapshots=None):
    inputs = {name: read_public(repo, name) for name in sorted(paths)}
    if snapshots is not None:
        snapshots.update(inputs)
    tree = _git(repo, 'ls-tree', '-rz', head, '--', *inputs)
    entries = {}
    for row in tree.split(b'\0'):
        if row:
            metadata, name = row.split(b'\t', 1)
            mode, kind, oid = metadata.decode('ascii').split()
            entries[name.decode('utf-8')] = (mode, kind, oid)
    oids = sorted({oid for mode, kind, oid in entries.values()
                   if mode in ('100644', '100755') and kind == 'blob'})
    output = _git(repo, 'cat-file', '--batch', input=('\n'.join(oids) + '\n').encode()) if oids else b''
    blobs, offset = {}, 0
    for oid in oids:
        stop = output.index(b'\n', offset)
        actual, kind, size = output[offset:stop].decode('ascii').split()
        if actual != oid or kind != 'blob':
            raise ValueError('unexpected Git object in source inputs')
        start, end = stop + 1, stop + 1 + int(size)
        data = output[start:end]
        if output[end:end + 1] != b'\n':
            raise ValueError('truncated Git source object')
        blobs[oid] = data.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
        offset = end + 1
    rows = {}
    for name, data in inputs.items():
        entry = entries.get(name)
        original = blobs.get(entry[2]) if entry and entry[:2] in (('100644', 'blob'), ('100755', 'blob')) else None
        rows[name] = {'source_sha256': hashlib.sha256(data).hexdigest(),
                      'git_sha256': hashlib.sha256(original).hexdigest() if original is not None else None,
                      'matches_git': original == data}
    if release and any(not row['matches_git'] for row in rows.values()):
        raise ValueError('release packaging inputs must match tracked Git commit bytes')
    return rows


def packaging_identity(repo, identity):
    # A repo override is useful for tests, but it cannot misattribute the code
    # executing this build to a different generator committed in that repo.
    running = Path(__file__).resolve().parents[1]
    for name in (*CODE_INPUTS, 'scripts/source_tool_closure.json'):
        if read_public(repo, name) != read_public(running, name):
            raise ValueError('repository differs from the executing packaging code')
    snapshots = {}
    rows = check_inputs(repo, identity['head'], input_paths(repo), release=identity['mode'] == 'release',
                        snapshots=snapshots)
    return {**identity, 'source_dirty': identity['source_dirty'] or any(
        not row['matches_git'] for row in rows.values()), 'input_provenance': rows}, snapshots
