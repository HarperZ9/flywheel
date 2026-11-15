"""Build a source plugin or self-contained Windows client from pinned inputs."""
import argparse
import hashlib
from pathlib import Path
import zipfile

from client_manifests import encoded, manifests
from client_package_inputs import VENDORED, entries, hashes, inputs, qualify as qualify_root, unchanged

ROOT = Path(__file__).resolve().parents[1]


def qualify(mode):
    return qualify_root(ROOT, mode)


def vendored_files(root=ROOT):
    """The server source the plugin folder carries, keyed by path under server/src.

    The same files the source ZIP places under server/src: every .py file in
    src/canon. Bytes use LF line endings so a CRLF checkout compares equal.
    """
    return {'canon/' + name: data.replace(b'\r\n', b'\n')
            for name, data in entries(Path(root) / 'src/canon', {'.py'}).items()}


def committed_vendored(root=ROOT):
    folder = Path(root) / VENDORED
    if not folder.is_dir():
        return {}
    return {path.relative_to(folder).as_posix(): path.read_bytes().replace(b'\r\n', b'\n')
            for path in sorted(folder.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}


def sync_vendored(root=ROOT):
    """Rewrite client-plugin/server/src from src/canon, removing stale files."""
    folder = Path(root) / VENDORED
    wanted = vendored_files(root)
    for name in set(committed_vendored(root)) - set(wanted):
        (folder / name).unlink()
    for name, data in wanted.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes().replace(b'\r\n', b'\n') != data:
            target.write_bytes(data)
    for path in sorted(folder.rglob('*'), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    return sorted(wanted)


def archive(files, target):
    files = dict(files)
    files['PAYLOAD-SHA256SUMS'] = ''.join(f'{digest}  {name}\n'
        for name, digest in sorted(hashes(files).items())).encode()
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as output:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)


def write_sums(target, paths):
    """Write sha256sum lines for paths to target with LF endings on every OS.

    Path.write_text turns each newline into CRLF on Windows. GNU sha256sum 8.32
    and Perl shasum then read the file name with a trailing carriage return and
    fail to open it, so the bytes are written directly.
    """
    lines = ''.join(f'{hashlib.sha256(Path(p).read_bytes()).hexdigest()}  {Path(p).name}\n' for p in paths)
    Path(target).write_bytes(lines.encode('utf-8'))


def build(output, native=False, mode='dev'):
    version, head = qualify(mode)
    output = Path(output).absolute()
    if output.exists():
        raise FileExistsError('output must be a new directory')
    original = inputs(ROOT, mode)
    files = {name.removeprefix('client-plugin/'): data for name, data in original.items()
             if name.startswith('client-plugin/')}
    files.update(manifests(version, native))
    files['LICENSE'] = original['LICENSE']
    receipt = {'status': 'DEVELOPMENT_CANDIDATE' if mode == 'dev' else 'RELEASE_CANDIDATE',
        'version': version, 'head': head, 'source_sha256': hashes(original),
        'does_not_prove': ['installed client acceptance', 'marketplace admission', 'clean OS compatibility']}
    output.mkdir(parents=True)
    if native:
        from native_client_build import freeze
        payload, details = freeze(ROOT, output, version, head)
        files.pop('server/serve.py')
        files.update(payload)
        receipt.update(details)
    else:
        files.update({'server/' + name: data for name, data in original.items() if name.startswith('src/canon/')})
    unchanged(ROOT, original, mode, head)
    files['QUALIFICATION.json'] = encoded(receipt)
    label = '-dev' if mode == 'dev' else ''
    name = f'canon-{version}{label}-' + ('win-x64' if native else 'source-plugin')
    artifacts = [output / (name + suffix) for suffix in (('.zip', '.mcpb') if native else ('.zip',))]
    for target in artifacts:
        archive(files, target)
    write_sums(output / 'SHA256SUMS', artifacts)
    (output / 'build-receipt.json').write_bytes(encoded(receipt))
    return artifacts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?')
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--mode', choices=('dev', 'release'), default='dev')
    parser.add_argument('--sync-vendored', action='store_true',
                        help='rewrite client-plugin/server/src from src/canon and exit')
    args = parser.parse_args()
    if args.sync_vendored:
        print(f'{len(sync_vendored())} files in {VENDORED}')
        raise SystemExit(0)
    if not args.output:
        parser.error('output is required unless --sync-vendored is given')
    for item in build(args.output, args.native, args.mode):
        print(item)
