"""Build source plugin or self-contained Windows client candidates."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOL = 'relay'
DESCRIPTION = ('Run a local coding agent in a project folder you choose, using a model server on your computer '
               'or a hosted model API you configure.')


def entries(root, extensions=frozenset({'.py', '.md', '.json'})):
    root = Path(root).absolute()
    for ancestor in [root, *root.parents]:
        if ancestor.is_symlink() or (ancestor.exists() and getattr(ancestor.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('linked input path')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('linked input entry')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            if path.name.lower().startswith('.env') or path.suffix.lower() not in extensions:
                raise ValueError('unsupported package input; state and credentials must stay outside package roots')
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


VENDORED = f'server/src/{TOOL}'


def plugin_entries():
    """The authored plugin files. The vendored server copy is left out: the
    build adds it from src/ so a stale copy can never reach a package."""
    files = entries(ROOT / 'client-plugin', extensions={'.py', '.md', '.json', '.png'})
    return {name: data for name, data in files.items() if not name.startswith(VENDORED + '/')}


def vendored_expected():
    """{relative name: bytes} the plugin folder must carry under server/src/<tool>:
    only the modules the client entry point can load (see client_closure)."""
    from client_closure import closure
    keep = closure(ROOT / 'src', TOOL, ROOT / 'client-plugin/server/serve.py')
    return {name: data for name, data in entries(ROOT / 'src' / TOOL).items() if name in keep}


def sync_vendored():
    """Rewrite client-plugin/server/src/<tool> from src/, deleting stale files."""
    target = ROOT / 'client-plugin' / VENDORED
    if target.exists():
        shutil.rmtree(target)
    for name, data in vendored_expected().items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.replace(b'\r\n', b'\n'))
    return target


def qualify(mode):
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
    version = project['version']
    import ast
    module = ast.parse((ROOT / 'src' / TOOL / '__init__.py').read_text(encoding='utf-8-sig'))
    declared = [node.value.value for node in module.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)
                and isinstance(node.value, ast.Constant)]
    if declared != [version]:
        raise ValueError('source and package versions differ')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if mode == 'release':
        heading = next((line for line in (ROOT / 'CHANGELOG.md').read_text().splitlines() if line.startswith('## ')), '')
        if version not in heading or 'unreleased' in heading.lower():
            raise ValueError('release notes must identify the final version without an unreleased marker')
        if not re.fullmatch(r'\d+\.\d+\.0', version):
            raise ValueError('mature releases must end in .0')
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
            raise ValueError('release source must be clean')
        tag = subprocess.check_output(['git', 'rev-parse', f'v{version}^{{commit}}'], cwd=ROOT, text=True).strip()
        if tag != head:
            raise ValueError('release tag must identify this HEAD')
    return version, head


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


SITE = 'https://harperz9.github.io'
REPOSITORY = 'https://github.com/HarperZ9/relay'
GRANTS = {'write': ('Allow file changes', 'Let approved model runs request file changes inside the selected folder.'),
          'exec': ('Allow command execution', 'Also enables file changes. Commands can reach paths outside the selected folder '
                   'with your operating-system permissions.')}
HOSTED = {'api_provider': ('Hosted model provider (optional)', 'Leave empty to use only the model servers on this '
                           'computer. To let calls that ask for online tiers use one hosted API, enter codex (OpenAI), '
                           'claude (Anthropic), gemini, deepseek or glm.'),
          'api_key': ('Hosted model API key (optional)', 'Key for the hosted provider above. Relay sends it only to that '
                      "provider's API, or to the gateway URL below when one is set."),
          'api_base_url': ('OpenAI-compatible gateway URL (optional)', 'Send hosted calls to this URL instead of the '
                           "provider's own API, for example a model gateway you run."),
          'api_model': ('Hosted model name (optional)', "Leave empty for Relay's default model for that provider.")}
HOSTED_ARGS = ['--api-provider=${user_config.api_provider}', '--api-base-url=${user_config.api_base_url}',
               '--api-model=${user_config.api_model}']


def settings(root_title, root_text):
    """Launch settings shared by the MCPB and the Claude plugin: the root, two
    default-off grants and the optional hosted model."""
    out = {'local_path': {'type': 'directory', 'title': root_title, 'description': root_text, 'required': True}}
    out.update({key: {'type': 'boolean', 'title': title, 'description': text, 'default': False, 'required': False}
                for key, (title, text) in GRANTS.items()})
    out.update({key: {'type': 'string', 'title': title, 'description': text, 'default': '', 'required': False,
                      **({'sensitive': True} if key == 'api_key' else {})}
                for key, (title, text) in HOSTED.items()})
    return out


def listing(plugin):
    """Claude manifest: the shared plugin fields plus the directory listing fields."""
    claude = settings('Project folder', 'The folder Relay works in. Runs and file tools stay inside it.')
    return {**plugin, 'displayName': 'Relay',
            'keywords': ['coding-agent', 'local-models', 'ollama', 'agentic', 'permissions', 'verification', 'mcp'],
            'homepage': SITE + '/plugins/relay/support.html', 'repository': REPOSITORY,
            'documentationUrl': REPOSITORY + '/blob/main/client-plugin/README.md',
            'supportUrl': SITE + '/plugins/relay/support.html',
            'privacyPolicyUrl': SITE + '/plugins/relay/privacy.html',
            'termsOfServiceUrl': SITE + '/plugins/relay/terms.html',
            'icon': './.claude-plugin/icon.png',
            'userConfig': {('project_folder' if key == 'local_path' else key): {k: v for k, v in spec.items()
                           if not (k == 'required' and v is False)} for key, spec in claude.items()}}


def manifests(version, native):
    executable = f'server/{TOOL}-local.exe'
    command = '${PLUGIN_ROOT}/' + executable if native else 'python3'
    args = [] if native else ['-I', '-S', '-B', '${PLUGIN_ROOT}/server/serve.py']
    binding = {'mneme': 'MNEME_STATE', 'relay': 'RELAY_MCP_ROOT'}.get(TOOL)
    env = {binding: '${' + binding + '}'} if binding else {}
    config = {'mcpServers': {TOOL: {'command': command, 'args': args, 'env': env, 'type': 'stdio'}}}
    plugin = {'name': TOOL + '-local', 'version': version,
              'description': DESCRIPTION,
              'author': {'name': 'Zain Dana Harper'}, 'license': 'FSL-1.1-MIT'}
    grant_args = ['--write=${user_config.write}', '--exec=${user_config.exec}']
    claude_args = ([a.replace('${PLUGIN_ROOT}', '${CLAUDE_PLUGIN_ROOT}') for a in args] + grant_args + HOSTED_ARGS
                   + ['--no-cli-tiers'])
    claude_env = {'RELAY_MCP_ROOT': '${user_config.project_folder}', 'RELAY_API_KEY': '${user_config.api_key}'}
    claude_config = {'mcpServers': {TOOL: {'command': command.replace('${PLUGIN_ROOT}', '${CLAUDE_PLUGIN_ROOT}'),
                                           'args': claude_args, 'env': claude_env, 'type': 'stdio'}}}
    files = {'plugin.json': encoded(plugin), '.claude-plugin/plugin.json': encoded(listing(plugin)),
             '.codex-plugin/plugin.json': encoded({**plugin, 'skills': './skills/', 'mcpServers': './mcp.json'}),
             'mcp.json': encoded(config), '.mcp.json': encoded(claude_config)}
    if native:
        mcp = {'command': '${__dirname}/' + executable, 'args': grant_args + HOSTED_ARGS,
               'env': {binding: '${user_config.local_path}', 'RELAY_API_KEY': '${user_config.api_key}'}}
        manifest = {'manifest_version': '0.3', **plugin, 'display_name': TOOL.title() + ' Local',
                    'server': {'type': 'binary', 'entry_point': executable, 'mcp_config': mcp},
                    'compatibility': {'platforms': ['win32']},
                    'user_config': settings('Launch root', f'Explicit absolute local path for {binding}.')}
        files['manifest.json'] = encoded(manifest)
    return files


def archive(files, target):
    files = dict(files)
    files['PAYLOAD-SHA256SUMS'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in sorted(files.items())).encode()
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


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
    files = plugin_entries()
    source = entries(ROOT / 'src' / TOOL)
    inputs = {f'src/{TOOL}/{name}': data for name, data in source.items()}
    inputs.update({f'client-plugin/{name}': data for name, data in files.items()})
    inputs.update({f'scripts/{name}': data for name, data in entries(ROOT / 'scripts', extensions={'.py', '.ps1', '.sh'}).items()})
    inputs['pyproject.toml'] = (ROOT / 'pyproject.toml').read_bytes()
    inputs['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    if mode == 'release':
        tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines())
        if set(inputs) - tracked:
            raise ValueError('release inputs must all be tracked authored files')
    source_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()}
    files.update(manifests(version, native))
    files['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    output.mkdir(parents=True)
    receipt = {'status': 'DEVELOPMENT_CANDIDATE' if mode == 'dev' else 'RELEASE_CANDIDATE',
               'version': version, 'head': head, 'source_sha256': source_hashes,
               'does_not_prove': ['installed client acceptance', 'marketplace admission', 'clean OS compatibility']}
    if native:
        if sys.platform != 'win32':
            raise ValueError('native build requires Windows x64')
        stage = output / 'stage'
        command = [sys.executable, '-m', 'PyInstaller', '--onefile', '--console', '--clean',
                   '--name', TOOL + '-local', '--paths', str(ROOT / 'src'),
                   '--hidden-import', TOOL + ('.local_mcp' if TOOL == 'relay' else '.mcp'),
                   '--distpath', str(stage), '--workpath', str(output / 'work'),
                   '--specpath', str(output / 'spec'), str(ROOT / 'client-plugin/server/serve.py')]
        for excluded in ('harness', 'cryptography', 'cffi', *({'mneme', 'relay', 'plexus'} - {TOOL})):
            command.extend(['--exclude-module', excluded])
        env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'SYSTEMDRIVE'}}
        epoch = subprocess.check_output(['git', 'show', '-s', '--format=%ct', head], cwd=ROOT, text=True).strip()
        if not epoch.isdigit():
            raise ValueError('source commit timestamp is invalid')
        env.update(SOURCE_DATE_EPOCH=epoch, PYTHONHASHSEED='0')
        receipt['native_build_environment'] = {'SOURCE_DATE_EPOCH': epoch, 'PYTHONHASHSEED': '0'}
        env['PATH'] = os.pathsep.join([sys.base_prefix, str(Path(env.get('SYSTEMROOT', 'C:/Windows')) / 'System32')])
        home = output / 'home'; home.mkdir()
        env.update({k: str(home) for k in ('HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')})
        with (output / 'freeze.log').open('w') as log:
            subprocess.run(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        from native_build_provenance import dependencies
        receipt.update(python=sys.version, pyinstaller=importlib.metadata.version('pyinstaller'),
                       native_dependencies=dependencies(output / f'work/{TOOL}-local/Analysis-00.toc', sys.base_prefix))
        from check_native_client import check
        receipt['native_smoke'] = check(stage / f'{TOOL}-local.exe', version)
        files.pop('server/serve.py')
        files[f'server/{TOOL}-local.exe'] = (stage / f'{TOOL}-local.exe').read_bytes()
        files['PYTHON-LICENSE.txt'] = (Path(sys.base_prefix) / 'LICENSE.txt').read_bytes()
        dist = importlib.metadata.distribution('pyinstaller')
        copying = [dist.locate_file(p) for p in dist.files if str(p).endswith('/licenses/COPYING.txt')]
        if len(copying) != 1:
            raise ValueError('missing PyInstaller license')
        files['PYINSTALLER-LICENSE.txt'] = copying[0].read_bytes()
    else:
        files.update({f'server/src/{TOOL}/{name}': data for name, data in vendored_expected().items()})
    if any((ROOT / name).read_bytes() != data for name, data in inputs.items()):
        raise ValueError('source changed during build')
    files['QUALIFICATION.json'] = encoded(receipt)
    label = '-dev' if mode == 'dev' else ''
    name = f'{TOOL}-{version}{label}-' + ('win-x64' if native else 'source-plugin')
    artifacts = [output / (name + suffix) for suffix in (('.zip', '.mcpb') if native else ('.zip',))]
    for target in artifacts:
        archive(files, target)
    write_sums(output / 'SHA256SUMS', artifacts)
    (output / 'build-receipt.json').write_bytes(encoded(receipt))
    return artifacts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?')
    parser.add_argument('--sync-vendored', action='store_true',
                        help='rewrite client-plugin/server/src from src/ and exit')
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--mode', choices=('dev', 'release'), default='dev')
    args = parser.parse_args()
    if args.sync_vendored:
        print(sync_vendored())
        raise SystemExit(0)
    if not args.output:
        parser.error('output is required unless --sync-vendored is given')
    for item in build(args.output, args.native, args.mode):
        print(item)
