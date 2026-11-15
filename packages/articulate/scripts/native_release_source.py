"""Qualify source before native outputs; development mode must be explicit."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_release_ruleset import check
from claude_plugin_rules import bundled_version

BASELINE = Path(__file__).with_name('release_ruleset_baseline.json')


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('release source Git qualification failed')
    return result.stdout.strip()


def qualify(root, version=None, *, mode='release', ref=None):
    root = Path(root).resolve()
    if mode not in ('dev', 'release'):
        raise ValueError('mode must be dev or release')
    module_version = bundled_version(root)
    project = (root / 'pyproject.toml').read_text(encoding='utf-8')
    match = re.search(r'(?ms)^\[project\]\s*$(.*?)(?=^\[|\Z)', project)
    declared = re.findall(r'''(?m)^version\s*=\s*["']([^"']+)["']\s*$''', match[1] if match else '')
    if not module_version or declared != [module_version] or version not in (None, module_version):
        raise ValueError('package, requested and module version must match')
    version = module_version
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('version must be numeric major.minor.patch')
    for name in ('plugin.json', '.claude-plugin/plugin.json', '.codex-plugin/plugin.json'):
        manifest = json.loads((root / 'claude-plugin' / name).read_text(encoding='utf-8'))
        if manifest.get('version') != version:
            raise ValueError(f'plugin version mismatch: {name}')
    retained = check(root, BASELINE)
    if retained['status'] != 'PASS':
        raise ValueError('release ruleset retention failed: ' + '; '.join(retained['failures']))
    head = git(root, 'rev-parse', 'HEAD')
    tag = 'v' + version
    if mode == 'release':
        if git(root, 'status', '--porcelain', '--untracked-files=all'):
            raise ValueError('release source must be clean')
        if git(root, 'rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}') != head:
            raise ValueError('HEAD must exactly equal the version tag')
        ref = ref if ref is not None else os.environ.get('GITHUB_REF')
        if ref is not None and ref != 'refs/tags/' + tag:
            raise ValueError('release ref must equal the version tag')
    return {'mode': mode, 'version': version, 'commit': head,
            'tag': tag if mode == 'release' else None, 'ruleset': retained['observed_fingerprint']}
