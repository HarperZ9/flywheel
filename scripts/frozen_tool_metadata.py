"""Freeze source identity beside the engine, without private checkout paths."""
import json
from pathlib import Path
import tomllib

from scripts.native_mcp_payload import source_identity, safe_name
from desktop.tool.installed_payload_binding import _scan_files


def validate_public_data(repo):
    for name, _path in _scan_files(Path(repo) / 'site'):
        safe_name('site/' + name)


def identity_data(repo, work):
    repo, work = Path(repo), Path(work)
    validate_public_data(repo)
    version = tomllib.loads((repo / 'pyproject.toml').read_text())['project']['version']
    identity = source_identity(repo, version, dev=True)
    identity.pop('mode')
    identity['schema'] = 'flywheel.frozen-source/v1'
    target = work / 'flywheel-frozen-source.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(identity, sort_keys=True) + '\n', encoding='utf-8')
    return [(str(target), 'flywheel-metadata')]
