"""Frozen identity accepts installed wheel metadata without loosening binding."""
import json
from pathlib import Path

import pytest

from scripts.build_native_mcp_bundle import frozen_identity

IDENTITY = {'head': 'a' * 40, 'version': '1.2.0', 'mode': 'release'}


def fixture(root, folder='flywheel_verify.egg-info', filename='PKG-INFO'):
    internal = root / '_internal'
    source = internal / 'flywheel-metadata'
    source.mkdir(parents=True, exist_ok=True)
    (source / 'flywheel-frozen-source.json').write_text(json.dumps({
        'schema': 'flywheel.frozen-source/v1', 'head': IDENTITY['head'],
        'version': IDENTITY['version'], 'source_dirty': False}))
    package = internal / folder
    package.mkdir(exist_ok=True)
    result = package / filename
    result.write_text('Name: flywheel-verify\nVersion: 1.2.0\n')
    return result


@pytest.mark.parametrize('folder,filename', [
    ('flywheel_verify.egg-info', 'PKG-INFO'),
    ('flywheel_verify-1.2.0.dist-info', 'METADATA'),
    ('flywheel_verify-1.2.0-py3.13.egg-info', 'PKG-INFO'),
])
def test_standard_metadata_forms(tmp_path, folder, filename):
    fixture(tmp_path, folder, filename)
    frozen_identity(tmp_path, IDENTITY)


@pytest.mark.parametrize('change', ['duplicate_directory', 'duplicate_file',
    'wrong_version', 'wrong_name', 'duplicate_header', 'wrong_folder_version'])
def test_ambiguous_or_mismatched_metadata_refused(tmp_path, change):
    metadata = fixture(tmp_path)
    if change == 'duplicate_directory':
        fixture(tmp_path, 'flywheel_verify-1.2.0.dist-info', 'METADATA')
    elif change == 'duplicate_file':
        (metadata.parent / 'METADATA').write_text(metadata.read_text())
    elif change == 'wrong_version':
        metadata.write_text('Name: flywheel-verify\nVersion: 1.3.0\n')
    elif change == 'wrong_name':
        metadata.write_text('Name: another-product\nVersion: 1.2.0\n')
    elif change == 'duplicate_header':
        metadata.write_text(metadata.read_text() + 'Version: 1.2.0\n')
    else:
        metadata.parent.rename(metadata.parent.with_name('flywheel_verify-1.3.0.dist-info'))
    with pytest.raises(ValueError):
        frozen_identity(tmp_path, IDENTITY)


@pytest.mark.parametrize('linked', ['file', 'directory', 'source'])
def test_metadata_link_refused(tmp_path, monkeypatch, linked):
    metadata = fixture(tmp_path)
    target = {'file': metadata, 'directory': metadata.parent,
              'source': tmp_path / '_internal/flywheel-metadata/flywheel-frozen-source.json'}[linked]
    # Emulate the shared scanner's link readout without requiring symlink privilege on Windows.
    from desktop.tool import installed_payload_binding as paths
    original = paths._is_link
    monkeypatch.setattr(paths, '_is_link', lambda path: path == target or original(path))
    with pytest.raises(ValueError, match='link'):
        frozen_identity(tmp_path, IDENTITY)
