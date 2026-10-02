"""Validate and extract the native companion before executing its fixed profile."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from desktop.tool.installed_payload_binding import _normalize_relative_path
from scripts.build_native_mcp_bundle import manifest, frozen_identity
from scripts.check_frozen_articulate import _json
from scripts.check_frozen_tool_mcp import check
from scripts.native_mcp_payload import safe_name, VERSION

ROOT_FILES = {'manifest.json', 'payload-binding.json', 'LICENSE', 'README.md', 'PYINSTALLER-LICENSE.txt'}


def extract_checked(archive, output, version, *, dev=False):
    output = Path(output)
    if output.exists():
        raise FileExistsError('extraction destination must not exist')
    if not VERSION.fullmatch(version):
        raise ValueError('invalid version')
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries) > 10000 or sum(e.file_size for e in entries) > 1_000_000_000:
            raise ValueError('archive exceeds native payload limits')
        names = []
        for entry in entries:
            safe_name(entry.filename)
            _normalize_relative_path(entry.filename, 'native_archive')
            if entry.is_dir() or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG):
                raise ValueError('archive links and special entries are not allowed')
            if entry.file_size > 256_000_000:
                raise ValueError('archive member exceeds native payload limits')
            names.append(entry.filename)
        if len(set(name.casefold() for name in names)) != len(names):
            raise ValueError('duplicate archive destination')
        if not ROOT_FILES <= set(names):
            raise ValueError('native metadata missing')
        if any(z.getinfo(name).file_size > 5_000_000 for name in ROOT_FILES):
            raise ValueError('native metadata exceeds limits')
        config = _json(z.read('manifest.json').decode('utf-8'))
        if config != manifest(version, dev=dev):
            raise ValueError('native manifest launch or permission boundary differs')
        binding = _json(z.read('payload-binding.json').decode('utf-8'))
        if (binding.get('schema') != 'flywheel.native-mcp-bundle/v1'
                or binding.get('version') != version or binding.get('same_installer_engine') is not True
                or binding.get('mode') != ('development' if dev else 'release')):
            raise ValueError('native payload binding identity differs')
        expected = {}
        for row in binding.get('payload', []):
            if not isinstance(row, dict) or set(row) != {'path', 'size', 'sha256'}:
                raise ValueError('invalid native payload row')
            name = 'engine/' + safe_name(row['path'])
            if name in expected:
                raise ValueError('duplicate native payload row')
            expected[name] = row
        if set(names) != ROOT_FILES | set(expected):
            raise ValueError('archive differs from bound payload')
        output.mkdir(parents=True)
        for entry in entries:
            target = output / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with z.open(entry) as source, target.open('xb') as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    size += len(chunk)
                    if size > entry.file_size:
                        raise ValueError('archive expanded beyond its declared size')
                    digest.update(chunk)
                    destination.write(chunk)
            if entry.filename in expected:
                row = expected[entry.filename]
                if type(row['size']) is not int or size != row['size'] or digest.hexdigest() != row['sha256']:
                    raise ValueError('extracted engine bytes differ from binding')
    frozen_identity(output / 'engine', binding)
    return output / 'engine/flywheel-gateway.exe'


def qualify(archive, version, *, dev=False, work_root=None):
    with tempfile.TemporaryDirectory(prefix='flywheel-native-mcp-', dir=work_root) as folder:
        executable = extract_checked(archive, Path(folder) / 'payload', version, dev=dev)
        result = check(executable, version)
    return {'schema': 'flywheel.native-mcp-qualification/v1', 'status': 'PASS',
            'archive_sha256': hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
            'version': version, 'profile_check': result,
            'does_not_prove': ['client installation', 'marketplace approval', 'external build attestation']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--work-root')
    args = parser.parse_args()
    result = qualify(args.archive, args.expected_version, dev=args.dev, work_root=args.work_root)
    Path(args.receipt).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
