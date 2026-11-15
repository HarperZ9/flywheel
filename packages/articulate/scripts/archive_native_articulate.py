"""Package a fixed Windows x64 local executable as development MCPB and ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_plugin_rules import contained_entries
from native_release_source import qualify
from check_native_articulate import check as check_native

ROOT = Path(__file__).resolve().parents[1]

FILES = {'articulate-local.exe', 'LICENSE', 'PYTHON-LICENSE.txt', 'PYINSTALLER-LICENSE.txt'}
README = '''# Articulate local tools for Windows x64

This development candidate includes its Python runtime. Extract the complete
ZIP and configure a local MCP client to run server/articulate-local.exe with no
arguments, or open the MCPB in a client supporting binary desktop extensions.
No Python, Node, model, API key or hosting account needs to be installed for
this tool. The connected model reads your submitted text and supplies rewrites.
Its account, model costs and permissions belong to you and your chosen client.

Articulate checks text and prepares and verifies host edits. This executable
forces local-only mode, rejects launch arguments and refuses external editing
backends. It does not install client settings or expose a network listener.
Guard acceptance is not proof that a rewrite preserves every aspect of meaning.

These are unpublished development bytes, even when the embedded version equals
an existing release. Windows x64 only; other systems and marketplace acceptance
are unverified. The portable ZIP and MCPB contain identical executable bytes.
See LICENSE, PYTHON-LICENSE.txt and PYINSTALLER-LICENSE.txt for source, bundled
runtime and bootloader terms.
'''


def validate_pe(data):
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('executable must be a Windows x64 PE binary')
    offset = struct.unpack_from('<I', data, 60)[0]
    if offset > len(data) - 6 or data[offset:offset + 4] != b'PE\0\0':
        raise ValueError('invalid Windows PE signature')
    if struct.unpack_from('<H', data, offset + 4)[0] != 0x8664:
        raise ValueError('executable architecture must be Windows x64')


def manifest(version, mode='dev'):
    return {
        'manifest_version': '0.3', 'name': 'articulate-writing-local',
        'version': version, 'display_name': 'Articulate Writing Local',
        'description': 'Local prose checks and guarded edits by your connected model.',
        'long_description': ('Development candidate' if mode == 'dev' else 'Local tools') +
                            ' for Windows x64. Includes its runtime; '
                            'no model, API key or hosting account is required.',
        'author': {'name': 'Zain Dana Harper'}, 'license': 'FSL-1.1-MIT',
        'server': {'type': 'binary', 'entry_point': 'server/articulate-local.exe',
                   'mcp_config': {'command': '${__dirname}/server/articulate-local.exe',
                                  'args': [], 'env': {}}},
        'compatibility': {'platforms': ['win32']},
    }


def write_sums(target, paths):
    """Write sha256sum lines for paths to target with LF endings on every OS.

    Path.write_text turns each newline into CRLF on Windows. GNU sha256sum 8.32
    and Perl shasum then read the file name with a trailing carriage return and
    fail to open it, so the bytes are written directly.
    """
    lines = ''.join(f'{hashlib.sha256(Path(p).read_bytes()).hexdigest()}  {Path(p).name}\n' for p in paths)
    Path(target).write_bytes(lines.encode('utf-8'))


def archive(stage_dir, out_dir, version, *, mode='release', root=ROOT, release_ref=None):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', version):
        raise ValueError('invalid version')
    qualified = qualify(root, version, mode=mode, ref=release_ref)
    stage, out = Path(stage_dir).absolute(), Path(out_dir).absolute()
    if out.resolve() == stage.resolve() or stage.resolve() in out.resolve().parents:
        raise ValueError('archive output must be outside the payload')
    # Reuse the link/reparse boundary check, then reject even .git (which the
    # source-plugin walker deliberately omits). This payload has no subfolders.
    contained_entries(stage)
    names = {p.name for p in stage.iterdir()}
    if names != FILES or any(not p.is_file() for p in stage.iterdir()):
        raise ValueError('missing or unsupported native payload files')
    data = {p.name: p.read_bytes() for p in stage.iterdir()}
    validate_pe(data['articulate-local.exe'])
    validation = check_native(stage / 'articulate-local.exe', version)
    if (validation.get('status') != 'PASS' or validation.get('version') != version or
            validation.get('executable_sha256') != hashlib.sha256(data['articulate-local.exe']).hexdigest()):
        raise ValueError('native validation failed or executable/version changed')
    data['server/articulate-local.exe'] = data.pop('articulate-local.exe')
    data['manifest.json'] = (json.dumps(manifest(version, mode), indent=2) + '\n').encode()
    readme = README if mode == 'dev' else README.replace('This development candidate', 'This package').replace(
        'These are unpublished development bytes, even when the embedded version equals\nan existing release. ', '')
    data['README.md'] = readme.encode()
    data['QUALIFICATION.json'] = (json.dumps({'source': qualified, 'native': validation}, indent=2) + '\n').encode()
    data['PAYLOAD-SHA256SUMS'] = ''.join(
        f'{hashlib.sha256(value).hexdigest()}  {name}\n'
        for name, value in sorted(data.items())).encode()
    label = '-dev' if mode == 'dev' else ''
    targets = [out / f'articulate-writing-{version}{label}-win-x64.{suffix}'
               for suffix in ('mcpb', 'zip')]
    if any(p.exists() for p in [*targets, out / 'SHA256SUMS']):
        raise FileExistsError('refusing to replace native archives or checksums')
    out.mkdir(parents=True, exist_ok=True)
    for target in targets:
        with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as z:
            for name, value in sorted(data.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                z.writestr(info, value)
    write_sums(out / 'SHA256SUMS', targets)
    return targets


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage')
    parser.add_argument('out')
    parser.add_argument('--version', required=True)
    parser.add_argument('--mode', choices=('dev', 'release'), default='release')
    args = parser.parse_args()
    for path in archive(args.stage, args.out, args.version, mode=args.mode):
        print(path)
