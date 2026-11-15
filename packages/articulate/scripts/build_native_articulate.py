"""Freeze the candidate as Windows x64 local tools; run with a PyInstaller venv."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from archive_native_articulate import archive
from claude_plugin_rules import bundled_version
from native_build_provenance import dependencies
from native_release_source import qualify

ROOT = Path(__file__).resolve().parent.parent


def build(output, *, mode='release', root=ROOT, release_ref=None):
    root = Path(root).resolve()
    qualified = qualify(root, mode=mode, ref=release_ref)
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('build requires a Windows x64 Python runtime')
    output = Path(output).absolute()
    if output.exists():
        raise FileExistsError('build output must be a new directory')
    version = qualified['version']
    source = sorted((root / 'src/articulate').glob('*.py'))
    # Package data the server reads at start-up, such as the house voice spec.
    source += sorted((root / 'src/articulate/data').glob('*.json'))
    source += [Path(__file__), root / 'scripts/native_articulate_entry.py',
               root / 'scripts/archive_native_articulate.py', root / 'scripts/native_build_provenance.py',
               root / 'scripts/native_release_source.py', root / 'scripts/check_release_ruleset.py',
               root / 'scripts/release_ruleset_baseline.json', root / 'scripts/check_native_articulate.py',
               root / 'scripts/native_windows_process.py', root / 'scripts/claude_plugin_rules.py']
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source}
    output.mkdir(parents=True)
    cmd = [sys.executable, '-m', 'PyInstaller', '--onefile', '--console', '--clean',
           '--name', 'articulate-local', '--paths', str(root / 'src'),
           '--add-data', str(root / 'src/articulate/data') + os.pathsep + 'articulate/data',
           '--exclude-module', 'fastmcp', '--exclude-module', 'articulate.hosted_mcp',
           '--exclude-module', 'articulate.hosted_boundary',
           '--distpath', str(output / 'stage'), '--workpath', str(output / 'work'),
           '--specpath', str(output / 'spec'), str(root / 'scripts/native_articulate_entry.py')]
    # Do not collect unrelated DLLs from the operator's PATH or package paths.
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'SYSTEMDRIVE'}}
    env['PATH'] = os.pathsep.join([sys.base_prefix, str(Path(env.get('SYSTEMROOT', 'C:/Windows')) / 'System32')])
    home = output / 'build-home'
    home.mkdir()
    env.update({k: str(home) for k in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA')})
    with (output / 'freeze.log').open('w', encoding='utf-8') as log:
        subprocess.run(cmd, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    if hashes != {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in source}:
        raise RuntimeError('source changed during native build')
    native = dependencies(output / 'work/articulate-local/Analysis-00.toc', sys.base_prefix)
    shutil.copyfile(root / 'LICENSE', output / 'stage/LICENSE')
    shutil.copyfile(Path(sys.base_prefix) / 'LICENSE.txt', output / 'stage/PYTHON-LICENSE.txt')
    dist = importlib.metadata.distribution('pyinstaller')
    copying = [dist.locate_file(p) for p in dist.files if str(p).endswith('/licenses/COPYING.txt')]
    if len(copying) != 1:
        raise RuntimeError('PyInstaller license not found uniquely')
    shutil.copyfile(copying[0], output / 'stage/PYINSTALLER-LICENSE.txt')
    targets = archive(output / 'stage', output / 'artifacts', version, mode=mode,
                      root=root, release_ref=release_ref)
    receipt = {'status': 'BUILT_RELEASE_CANDIDATE' if mode == 'release' else 'BUILT_DEVELOPMENT_CANDIDATE',
               'version': version, 'source_qualification': qualified,
               'python': sys.version, 'freeze_tools': {name: importlib.metadata.version(name)
                   for name in ('pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'packaging', 'pefile', 'pywin32-ctypes')},
               'source_sha256': hashes, 'command': cmd,
               'native_dependencies': native,
               'artifacts': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in targets},
               'scope': 'Records the source hashes, the freeze tools and the hash of each '
                        'built artifact.'}
    (output / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return targets


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    parser.add_argument('--mode', choices=('dev', 'release'), default='release')
    args = parser.parse_args()
    for target in build(args.output, mode=args.mode):
        print(target)
