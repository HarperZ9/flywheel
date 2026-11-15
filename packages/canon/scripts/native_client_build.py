"""Freeze only the selected Python runtime under an isolated build home."""
import importlib.metadata
import os
from pathlib import Path
import struct
import subprocess
import sys

from client_package_inputs import git


def build_environment(output, root, head):
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE'}}
    epoch = git(root, 'show', '-s', '--format=%ct', head)
    if not epoch.isdigit():
        raise ValueError('source commit timestamp is invalid')
    env.update(SOURCE_DATE_EPOCH=epoch, PYTHONHASHSEED='0')
    env['PATH'] = os.pathsep.join([sys.base_prefix, str(Path(env.get('SYSTEMROOT', 'C:/Windows')) / 'System32')])
    home = output / 'home'
    home.mkdir()
    temp = output / 'temp'
    temp.mkdir()
    # Resolve explicit long paths before PyInstaller; ambient TEMP may be an 8.3 alias.
    env.update({key: str(home.resolve()) for key in ('HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')})
    env.update({key: str(temp.resolve()) for key in ('TEMP', 'TMP')})
    return env


def runtime_licenses():
    dist = importlib.metadata.distribution('pyinstaller')
    copying = [dist.locate_file(p) for p in dist.files if str(p).endswith('/licenses/COPYING.txt')]
    if len(copying) != 1:
        raise ValueError('missing PyInstaller license')
    return {'PYTHON-LICENSE.txt': (Path(sys.base_prefix) / 'LICENSE.txt').read_bytes(),
            'PYINSTALLER-LICENSE.txt': copying[0].read_bytes()}


def freeze(root, output, version, head):
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise ValueError('native build requires Windows x64')
    stage = output / 'stage'
    command = [sys.executable, '-m', 'PyInstaller', '--onefile', '--console', '--clean',
        '--name', 'canon-local', '--paths', str(root / 'src'), '--hidden-import', 'canon.client_mcp',
        '--distpath', str(stage), '--workpath', str(output / 'work'),
        '--specpath', str(output / 'spec'), str(root / 'client-plugin/server/serve.py')]
    for excluded in ('harness', 'cryptography', 'cffi', 'mneme', 'relay', 'plexus'):
        command.extend(['--exclude-module', excluded])
    env = build_environment(output, root, head)
    with (output / 'freeze.log').open('w') as log:
        subprocess.run(command, env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
    from native_build_provenance import dependencies
    from check_native_client import check
    receipt = {'python': sys.version, 'pyinstaller': importlib.metadata.version('pyinstaller'),
        'native_dependencies': dependencies(output / 'work/canon-local/Analysis-00.toc', sys.base_prefix),
        'native_build_environment': {key: env[key] for key in ('SOURCE_DATE_EPOCH', 'PYTHONHASHSEED')},
        'native_smoke': check(stage / 'canon-local.exe', version)}
    payload = runtime_licenses()
    payload['server/canon-local.exe'] = (stage / 'canon-local.exe').read_bytes()
    return payload, receipt
