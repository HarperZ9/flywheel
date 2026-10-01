"""Qualify the source companion with the existing proof and refusal checker."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_source_tool_plugin import package_files
from scripts.native_mcp_payload import safe_name, source_identity
from scripts.source_tool_payload import verify_payload
from scripts.check_frozen_tool_mcp import (DENIED, call, req, validate, snapshot,
    list_resources, parse_replies, prepare_receipt_smoke_fixture, MISSING_LEAF)
from scripts.frozen_mcp_process import run_mcp_process


def extract_checked(archive, out, version, *, dev=False):
    out = Path(out)
    if out.exists():
        raise FileExistsError('qualification output must not exist')
    expected, _ = package_files(ROOT, source_identity(ROOT, version, dev=dev))
    files = {}
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 512 or sum(entry.file_size for entry in entries) >= 50 * 1024 * 1024:
            raise ValueError('source archive exceeds limits')
        for entry in entries:
            if entry.orig_filename != entry.filename:
                raise ValueError('archive path was normalized')
            safe_name(entry.filename)
            mode = entry.external_attr >> 16
            if (entry.filename in files or entry.is_dir() or entry.file_size >= 256 * 1024
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ValueError('invalid source archive member')
            files[entry.filename] = source.read(entry)
    verify_payload(files)
    if files != expected:
        raise ValueError('archive payload differs from reviewed source and metadata')
    out.mkdir(parents=True)
    for name, data in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return out


def qualify_directory(plugin, base, version, python):
    """Only adapt the launch boundary; proof checks remain shared with native MCP."""
    plugin, base = Path(plugin), Path(base)
    home, workspace, state = (base / name for name in ('home', 'workspace', 'state'))
    for folder in (home, workspace, state):
        folder.mkdir(parents=True, exist_ok=False)
    leaf = prepare_receipt_smoke_fixture(state)
    selected = state / 'runs'
    before = snapshot(selected)
    windows = os.environ.get('SYSTEMROOT', 'C:/Windows')
    env = {'SYSTEMROOT': windows, 'WINDIR': windows, 'PATH': str(Path(windows) / 'System32')}
    env.update({key: str(home) for key in ('HOME', 'USERPROFILE', 'FLYWHEEL_HOME',
                                          'TMP', 'TEMP', 'APPDATA', 'LOCALAPPDATA')})
    env.update({'FLYWHEEL_LOCAL_AGENT_ALLOW_' + key: '1' for key in ('WRITE', 'EXEC', 'ONLINE')})
    requests = [req(1, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}}),
        req(2, 'tools/list', {}), req(3, 'resources/list', {}), call(4, 'flywheel.tool_status', {}),
        *[call(rid, 'receipt.verify_inclusion', {'leaf': value})
          for rid, value in enumerate((leaf, MISSING_LEAF, 'bad'), 5)]]
    requests += [req(rid, 'resources/read', {'uri': row['uri']})
                 for rid, row in enumerate(list_resources()['resources'], 8)]
    requests += [call(rid, name, {'online': True, 'allow_exec': True, 'allow_write': True})
                 for rid, name in enumerate(DENIED, 10)]
    wire = ''.join(json.dumps(request) + '\n' for request in requests)
    args = ['-I', '-S', '-B', str(plugin / 'server/serve.py'),
            '--root', str(workspace), '--run-root', str(selected)]
    output = run_mcp_process(Path(python).resolve(strict=True), args, home, env, wire)
    validate(parse_replies(output, set(range(1, 10 + len(DENIED)))), version, leaf)
    if snapshot(selected) != before or list(workspace.iterdir()):
        raise ValueError('source companion wrote selected roots')
    return {'status': 'PASS', 'version': version, 'public_resources': 2,
            'refused_tools': list(DENIED), 'receipt_fixture_verified': True,
            'selected_roots_unchanged': True, 'requires_python': '>=3.11',
            'python_sha256': hashlib.sha256(Path(python).read_bytes()).hexdigest(),
            'does_not_prove': ['global OS sandbox', 'clean OS installation',
                              'installed client compatibility', 'marketplace approval']}


def check(archive, out, version, *, python=sys.executable, dev=False):
    out = Path(out)
    if out.exists():
        raise FileExistsError('source qualification directory must not exist')
    plugin = extract_checked(archive, out / 'plugin', version, dev=dev)
    result = qualify_directory(plugin, out / 'protocol', version, python)
    result.update(schema='flywheel.source-tool-plugin-acceptance/v1',
                  source_archive_sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
                  mode='development' if dev else 'release')
    (out / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--dev', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(args.archive, args.out, args.expected_version, python=args.python, dev=args.dev)))
