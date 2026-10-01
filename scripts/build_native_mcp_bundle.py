"""Build the native Flywheel companion from exact installer engine bytes."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.native_mcp_payload import bind_payload, source_identity, VERSION
from desktop.tool.installed_payload_binding import _scan_files


def frozen_metadata_paths(engine, version):
    """Resolve the unique product metadata through the shared link-rejecting scanner."""
    internal = Path(engine) / '_internal'
    source_files = dict(_scan_files(internal / 'flywheel-metadata'))
    source = source_files.get('flywheel-frozen-source.json')
    if source is None:
        raise ValueError('frozen source identity missing')
    product = re.compile(r'flywheel[-_.]verify(?:-.*)?\.(?:egg|dist)-info', re.I)
    packages = [path for path in internal.iterdir() if product.fullmatch(path.name)]
    if len(packages) != 1:
        raise ValueError('frozen package version metadata missing or ambiguous')
    package = packages[0]
    escaped = re.escape(version)
    standard = rf'flywheel[-_.]verify(?:\.egg-info|-{escaped}(?:-py[0-9]+\.[0-9]+)?\.egg-info|-{escaped}\.dist-info)'
    if not re.fullmatch(standard, package.name, re.I):
        raise ValueError('frozen package metadata directory version mismatch')
    files = dict(_scan_files(package))
    candidates = [files[name] for name in ('PKG-INFO', 'METADATA') if name in files]
    expected = 'METADATA' if package.name.lower().endswith('.dist-info') else 'PKG-INFO'
    if len(candidates) != 1 or expected not in files:
        raise ValueError('frozen package version metadata missing or ambiguous')
    return source, candidates[0]


def frozen_identity(engine, identity):
    source = dict(_scan_files(Path(engine) / '_internal/flywheel-metadata')).get('flywheel-frozen-source.json')
    if source is None:
        raise ValueError('frozen source identity missing')
    frozen = json.loads(source.read_text(encoding='utf-8'))
    if (frozen.get('schema') != 'flywheel.frozen-source/v1' or frozen.get('head') != identity['head']
            or frozen.get('version') != identity['version']
            or (identity['mode'] == 'release' and frozen.get('source_dirty') is not False)):
        raise ValueError('frozen source identity does not match release source')
    source, metadata = frozen_metadata_paths(engine, identity['version'])
    # Recheck the source after link-safe resolution; retain the early mismatch diagnostic.
    if json.loads(source.read_text(encoding='utf-8')) != frozen:
        raise ValueError('frozen source identity changed during validation')
    from email.parser import Parser
    fields = Parser().parsestr(metadata.read_text(encoding='utf-8'))
    if fields.get_all('Name') != ['flywheel-verify'] or fields.get_all('Version') != [identity['version']]:
        raise ValueError('frozen package version does not match source')


def bootloader_license():
    distribution = importlib.metadata.distribution('pyinstaller')
    files = [distribution.locate_file(p) for p in distribution.files
             if str(p).endswith('/licenses/COPYING.txt')]
    if len(files) != 1:
        raise ValueError('PyInstaller bootloader license missing')
    return files[0].read_bytes()


def manifest(version, *, dev=False):
    return {'manifest_version': '0.3', 'name': 'flywheel-tools', 'version': version,
        'display_name': 'Flywheel Local Evidence',
        'description': 'Public evidence-task resources and local receipt membership checks.',
        'long_description': ('Unpublished development candidate. ' if dev else '') +
            'A restricted companion to the full Flywheel client. Includes its runtime. '
            'No model, network, subprocess or write grants. Receipt membership does not prove meaning.',
        'author': {'name': 'Zain Dana Harper'},
        'server': {'type': 'binary', 'entry_point': 'engine/flywheel-gateway.exe',
                   'mcp_config': {'command': '${__dirname}/engine/flywheel-gateway.exe',
                    'args': ['--tool-mcp', '--root', '${user_config.workspace}',
                             '--run-root', '${user_config.state}']}},
        'compatibility': {'platforms': ['win32']},
        'user_config': {
            'workspace': {'type': 'directory', 'title': 'Workspace folder', 'required': True,
                'description': 'Select an existing local project folder, separate from receipt state.'},
            'state': {'type': 'directory', 'title': 'Receipt state folder', 'required': True,
                'description': 'Select existing local state with an envelopes folder; read-only access.'}}}


def bundle(engine, installer_engine, collect_toc, out, *, dev=False):
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    identity = source_identity(ROOT, version, dev=dev)
    engine, out = Path(engine).absolute(), Path(out).absolute()
    for source in (engine, Path(installer_engine).absolute()):
        if out.resolve() == source.resolve() or source.resolve() in out.resolve().parents:
            raise ValueError('output must be outside the engine payload')
    if out.exists():
        raise FileExistsError('native output directory must not exist')
    rows = bind_payload(engine, installer_engine, collect_toc)
    frozen_identity(engine, identity)
    label = '-dev' if dev else ''
    filename = f'flywheel-tools-{version}{label}-win-x64.mcpb'
    receipt = {'schema': 'flywheel.native-mcp-bundle/v1', **identity,
        'payload': rows, 'same_installer_engine': True,
        'does_not_prove': ['marketplace acceptance', 'clean OS installation', 'full client interoperability']}
    files = {'manifest.json': (json.dumps(manifest(version, dev=dev), indent=2) + '\n').encode(),
             'payload-binding.json': (json.dumps(receipt, indent=2) + '\n').encode(),
             'LICENSE': (ROOT / 'LICENSE').read_bytes(),
             'PYINSTALLER-LICENSE.txt': bootloader_license(),
             'README.md': (ROOT / 'docs/native-tool-package.md').read_bytes()}
    out.mkdir(parents=True)
    archive = out / filename
    with zipfile.ZipFile(archive, 'x') as z:
        for name, data in sorted(files.items()):
            z.writestr(info(name), data)
        for row in rows:
            with (engine / row['path']).open('rb') as source, z.open(info('engine/' + row['path']), 'w') as target:
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
                    target.write(chunk)
            if digest.hexdigest() != row['sha256']:
                raise ValueError('engine changed during archive creation')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / 'native-MCPB-SHA256SUMS.txt').write_bytes(f'{digest}  {filename}\n'.encode('utf-8'))
    return archive


def info(name):
    record = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    record.create_system = 3
    record.external_attr = 0o100644 << 16
    record.compress_type = zipfile.ZIP_DEFLATED
    return record


def verify(checksums, accepted_sha256, version):
    checksums = Path(checksums)
    data = checksums.read_bytes()
    if not VERSION.fullmatch(version) or hashlib.sha256(data).hexdigest() != accepted_sha256:
        raise ValueError('accepted native checksum receipt mismatch')
    match = re.fullmatch(r'([a-f0-9]{64})  (flywheel-tools-' + re.escape(version) + r'-win-x64\.mcpb)\r?\n',
                         data.decode('utf-8'))
    if not match:
        raise ValueError('native receipt must identify the exact release version')
    digest, name = match.groups()
    target = checksums.parent / name
    if target.is_symlink() or {p.name for p in checksums.parent.glob('*.mcpb')} != {name}:
        raise ValueError('unexpected native artifact set')
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError('native artifact hash mismatch')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path)
    parser.add_argument('--installer-engine', type=Path)
    parser.add_argument('--collect-toc', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--accepted-sha256')
    parser.add_argument('--version')
    args = parser.parse_args()
    if args.verify:
        if not args.accepted_sha256 or not args.version:
            parser.error('verification requires accepted checksum and version')
        print(verify(args.verify, args.accepted_sha256, args.version))
    else:
        if not all((args.engine, args.installer_engine, args.collect_toc, args.out)):
            parser.error('building requires engine, installer-engine, collect-toc and out')
        print(bundle(args.engine, args.installer_engine, args.collect_toc, args.out, dev=args.dev))
