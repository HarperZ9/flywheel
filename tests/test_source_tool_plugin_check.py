"""Archive qualification refuses drift before importing an extracted payload."""
import hashlib
import json
from pathlib import Path
import zipfile
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']


def test_modified_payload_is_rejected_before_extraction(tmp_path):
    from scripts.build_source_tool_plugin import bundle
    from scripts.check_source_tool_plugin import extract_checked
    archive = bundle(tmp_path / 'build', dev=True)
    changed = tmp_path / 'changed.zip'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(changed, 'w') as target:
        for entry in source.infolist():
            data = source.read(entry)
            if entry.filename == 'server/harness/tool_mcp.py':
                data += b'\n# mutation\n'
            target.writestr(entry, data)
    with pytest.raises(ValueError, match='payload|source'):
        extract_checked(changed, tmp_path / 'extract', VERSION, dev=True)
    assert not (tmp_path / 'extract').exists()


@pytest.mark.parametrize('name', ['a//b', 'a/./b', '../outside', 'NUL.txt', '.env', 'a\\b'])
def test_archive_paths_are_checked_before_extraction(tmp_path, name):
    from scripts.check_source_tool_plugin import extract_checked
    archive = tmp_path / 'bad.zip'
    entry = zipfile.ZipInfo(name)
    entry.filename = name
    with zipfile.ZipFile(archive, 'w') as target:
        target.writestr(entry, b'bad')
    with pytest.raises(ValueError):
        extract_checked(archive, tmp_path / 'out', VERSION, dev=True)
    assert not (tmp_path / 'out').exists()


def test_source_checker_exercises_real_receipt_proof_and_denials(tmp_path):
    from scripts.build_source_tool_plugin import bundle
    from scripts.check_source_tool_plugin import check
    import os
    import sys
    if os.name != 'nt':
        pytest.skip('existing bounded MCP process runner is Windows-specific')
    archive = bundle(tmp_path / 'build', dev=True)
    receipt = check(archive, tmp_path / 'acceptance', VERSION, python=sys.executable, dev=True)
    assert receipt['status'] == 'PASS'
    assert receipt['receipt_fixture_verified'] is True
    assert receipt['public_resources'] == 2 and receipt['selected_roots_unchanged'] is True
    assert receipt['source_archive_sha256'] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert 'marketplace approval' in receipt['does_not_prove']
