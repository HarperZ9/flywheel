"""Read authored inputs and enforce release identity before packaging."""
import ast
import hashlib
from pathlib import Path
import re
import stat
import subprocess
import tomllib


VENDORED = 'client-plugin/server/src/'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def entries(root, extensions=frozenset({'.py', '.md', '.json'})):
    root = Path(root).absolute()
    for ancestor in [root, *root.parents]:
        if linked(ancestor):
            raise ValueError('linked input path')
    result = {}
    for path in sorted(root.rglob('*')):
        if linked(path):
            raise ValueError('linked input entry')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            if path.name.lower().startswith('.env') or path.suffix.lower() not in extensions:
                raise ValueError('unsupported package input; state and credentials stay outside package roots')
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def linked(path):
    return path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0)
                                 & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024))


def qualify(root, mode):
    if mode not in {'dev', 'release'}:
        raise ValueError('invalid build mode')
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    module = ast.parse((root / 'src/canon/_version.py').read_text(encoding='utf-8-sig'))
    declared = [node.value.value for node in module.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)
        and isinstance(node.value, ast.Constant)]
    if declared != [version]:
        raise ValueError('source and package versions differ')
    head = git(root, 'rev-parse', 'HEAD')
    if mode == 'release':
        heading = next((s for s in (root / 'CHANGELOG.md').read_text().splitlines() if s.startswith('## ')), '')
        if version not in heading or 'unreleased' in heading.lower():
            raise ValueError('release notes must identify final version without an unreleased marker')
        if not re.fullmatch(r'\d+\.\d+\.0', version):
            raise ValueError('mature releases must end in .0')
        if git(root, 'status', '--porcelain'):
            raise ValueError('release source must be clean')
        if git(root, 'rev-parse', f'v{version}^{{commit}}') != head:
            raise ValueError('release tag must identify this HEAD')
    return version, head


def inputs(root, mode):
    files = {}
    for directory, extensions in (('src/canon', {'.py'}), ('client-plugin', {'.py', '.md', '.json', '.png'}),
                                   ('scripts', {'.py', '.ps1', '.sh'})):
        files.update({f'{directory}/{name}': data for name, data in entries(root / directory, extensions).items()})
    # The vendored server copy is derived from src/canon; the build reads src/canon itself.
    files = {name: data for name, data in files.items() if not name.startswith(VENDORED)}
    for name in ('pyproject.toml', 'LICENSE', 'CHANGELOG.md'):
        files[name] = (root / name).read_bytes()
    for name in ('.claude-plugin/plugin.json', '.mcp.json'):
        if (root / name).exists():
            files[name] = (root / name).read_bytes()
    if mode == 'release' and set(files) - set(git(root, 'ls-files').splitlines()):
        raise ValueError('release inputs must all be tracked authored files')
    if mode == 'release':
        verify_head_inputs(root, files)
    return files


def verify_head_inputs(root, files):
    flagged = git(root, 'ls-files', '-v').splitlines()
    if any(row[2:] in files and (row[0].islower() or row[0] == 'S') for row in flagged):
        raise ValueError('release inputs cannot use assume-unchanged or skip-worktree')
    blobs = {}
    for row in git(root, 'ls-tree', '-r', 'HEAD').splitlines():
        metadata, name = row.split('\t', 1)
        blobs[name] = metadata.split()[2]
    names = sorted(files)
    for start in range(0, len(names), 100):
        batch = names[start:start + 100]
        # Git applies each path's clean filters, including configured CRLF handling.
        actual = git(root, 'hash-object', '--', *batch).splitlines()
        if len(actual) != len(batch) or any(blobs.get(name) != digest for name, digest in zip(batch, actual)):
            raise ValueError('release input bytes differ from HEAD')


def unchanged(root, original, mode, head):
    if inputs(root, mode) != original or git(root, 'rev-parse', 'HEAD') != head:
        raise ValueError('source changed during build')
    if mode == 'release':
        qualify(root, mode)


def hashes(files):
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
