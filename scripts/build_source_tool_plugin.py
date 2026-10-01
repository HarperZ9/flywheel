"""Package the reviewed, stdlib-only Flywheel tools source companion."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.native_mcp_payload import source_identity, VERSION
from scripts.source_tool_payload import reviewed_payload, verify_payload
from scripts.source_tool_manifests import encoded, manifests
from scripts.source_tool_provenance import packaging_identity


def package_files(repo, identity):
    identity, snapshots = packaging_identity(repo, identity)
    version, dev = identity['version'], identity['mode'] == 'development'
    if tomllib.loads(snapshots['pyproject.toml'].decode('utf-8'))['project']['version'] != version:
        raise ValueError('source version changed during packaging')
    files = reviewed_payload(repo, snapshots)
    files.update(manifests(version, dev=dev))
    if dev:
        files['README.md'] = b'Unpublished development candidate. Do not publish these bytes.\n\n' + files['README.md']
    receipt = {'schema': 'flywheel.source-tool-plugin/v1', **identity,
        'tag': None if dev else 'v' + version,
        'profile': 'local-evidence', 'python_requirement': '>=3.11',
        'entrypoint': 'harness.tool_mcp.main', 'reviewed_python_modules': 78,
        'text_encoding': 'UTF-8 with LF newlines',
        'closure_review_sha256': hashlib.sha256(snapshots['scripts/source_tool_closure.json']).hexdigest(),
        'payload_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        'does_not_prove': ['full harness availability', 'global OS sandbox',
                          'installed client compatibility', 'marketplace approval', 'semantic truth']}
    files['SOURCE.json'] = encoded(receipt)
    verify_payload(files)
    return files, receipt


def bundle(out, *, dev=False, repo=ROOT):
    repo, out = Path(repo).resolve(strict=True), Path(out).absolute()
    if out.exists():
        raise FileExistsError('source output directory must not exist')
    if out.resolve() == repo or repo in out.resolve().parents:
        raise ValueError('source output must be outside the source checkout')
    version = tomllib.loads((repo / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    identity = source_identity(repo, version, dev=dev)
    files, receipt = package_files(repo, identity)
    label = '-dev' if dev else ''
    name = f'flywheel-tools-{version}{label}-source-plugin.zip'
    out.mkdir(parents=True)
    archive = out / name
    with zipfile.ZipFile(archive, 'x') as target:
        for relative, data in sorted(files.items()):
            entry = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(entry, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / 'source-plugin-SHA256SUMS.txt').write_bytes(f'{digest}  {name}\n'.encode('utf-8'))
    (out / 'source-plugin-build-receipt.json').write_bytes(encoded({**receipt,
        'archive': name, 'archive_sha256': digest, 'files': len(files)}))
    return archive


def verify(checksums, accepted_sha256, version, *, dev=False):
    checksums = Path(checksums)
    data = checksums.read_bytes()
    if not VERSION.fullmatch(version) or hashlib.sha256(data).hexdigest() != accepted_sha256:
        raise ValueError('accepted source checksum receipt mismatch')
    label = '-dev' if dev else ''
    name = f'flywheel-tools-{version}{label}-source-plugin.zip'
    match = re.fullmatch(r'([a-f0-9]{64})  ' + re.escape(name) + r'\r?\n', data.decode('utf-8'))
    if not match:
        raise ValueError('source receipt must identify the exact release version')
    archive = checksums.parent / name
    if archive.is_symlink() or {p.name for p in checksums.parent.glob('*.zip')} != {name}:
        raise ValueError('unexpected source archive set')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != match[1]:
        raise ValueError('source archive hash mismatch')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--out', type=Path)
    modes.add_argument('--verify', type=Path)
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--accepted-sha256')
    parser.add_argument('--version')
    args = parser.parse_args()
    if args.verify:
        if not args.accepted_sha256 or not args.version:
            parser.error('verification requires accepted checksum and version')
        print(verify(args.verify, args.accepted_sha256, args.version, dev=args.dev))
    else:
        print(bundle(args.out, dev=args.dev))
