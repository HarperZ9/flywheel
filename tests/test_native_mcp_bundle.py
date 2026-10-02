"""The native companion binds the same payload the installer ships."""
import hashlib
import json
from pathlib import Path
import struct
import zipfile

import pytest


def fixture(tmp_path):
    from shutil import copytree
    engine = tmp_path / 'engine'
    engine.mkdir()
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, 0x8664)
    (engine / 'flywheel-gateway.exe').write_bytes(data)
    internal = engine / '_internal'
    internal.mkdir()
    (internal / 'runtime.dll').write_bytes(b'runtime')
    installer = tmp_path / 'installer-engine'
    copytree(engine, installer)
    toc = tmp_path / 'COLLECT-00.toc'
    toc.write_text(repr(([
        ('flywheel-gateway.exe', str(engine / 'flywheel-gateway.exe'), 'EXECUTABLE'),
        ('runtime.dll', str(internal / 'runtime.dll'), 'BINARY')],)))
    return engine, installer, toc


def test_payload_binding_requires_exact_collection_and_installer_bytes(tmp_path):
    from scripts.native_mcp_payload import bind_payload
    engine, installer, toc = fixture(tmp_path)
    files = bind_payload(engine, installer, toc)
    assert len(files) == 2
    (installer / '_internal/runtime.dll').write_bytes(b'changed')
    with pytest.raises(ValueError, match='installer'):
        bind_payload(engine, installer, toc)


@pytest.mark.parametrize('path', ['.env', '_internal/private/secret.txt', '_internal/state/local.json',
                                 '../escape', 'site/session.token', 'site/server.jks', 'site/client.keystore',
                                 'engine/NUL', 'site/file.', 'site/file '])
def test_private_or_unsafe_collection_names_refuse(tmp_path, path):
    from scripts.native_mcp_payload import safe_name
    with pytest.raises(ValueError):
        safe_name(path)


def test_extra_staged_file_refuses_even_when_installer_matches(tmp_path):
    from scripts.native_mcp_payload import bind_payload
    engine, installer, toc = fixture(tmp_path)
    for folder in (engine, installer):
        (folder / '_internal/extra.json').write_text('{}')
    with pytest.raises(ValueError, match='collection'):
        bind_payload(engine, installer, toc)


def test_windows_collection_separators_are_canonicalized(tmp_path):
    from scripts.native_mcp_payload import bind_payload
    engine, installer, toc = fixture(tmp_path)
    for root in (engine, installer):
        (root / '_internal/data').mkdir()
        (root / '_internal/data/public.txt').write_bytes(b'public')
    import ast
    rows, = ast.literal_eval(toc.read_text())
    rows.append(('data\\public.txt', str(engine / '_internal/data/public.txt'), 'DATA'))
    toc.write_text(repr((rows,)))
    assert 'data/public.txt' in str(bind_payload(engine, installer, toc))


def test_manifest_requires_two_user_roots_without_model_or_grants():
    from scripts.build_native_mcp_bundle import manifest
    result = manifest('1.2.0', dev=True)
    assert result['server']['type'] == 'binary'
    assert set(result['user_config']) == {'workspace', 'state'}
    assert all(item['required'] is True and item['type'] == 'directory' for item in result['user_config'].values())
    launch = result['server']['mcp_config']
    assert launch['args'] == ['--tool-mcp', '--root', '${user_config.workspace}', '--run-root', '${user_config.state}']
    assert not launch.get('env')
    assert 'development' in result['long_description'].lower()


def test_release_checksums_bind_archive_and_reject_other_files(tmp_path):
    from scripts.build_native_mcp_bundle import verify
    target = tmp_path / 'flywheel-tools-1.2.0-win-x64.mcpb'
    target.write_bytes(b'archive')
    sums = tmp_path / 'native-MCPB-SHA256SUMS.txt'
    sums.write_text(hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + target.name + '\n')
    digest = hashlib.sha256(sums.read_bytes()).hexdigest()
    assert verify(sums, digest, '1.2.0') == target
    target.write_bytes(b'changed')
    with pytest.raises(ValueError):
        verify(sums, digest, '1.2.0')


def test_source_release_gate_fails_dirty_or_untagged_checkout(tmp_path):
    import subprocess
    from scripts.native_mcp_payload import source_identity
    for args in (['init', '-q'], ['config', 'user.name', 'Fixture'], ['config', 'user.email', 'fixture@example.invalid']):
        subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True)
    (tmp_path / 'test.txt').write_text('public fixture')
    subprocess.run(['git', '-C', str(tmp_path), 'add', 'test.txt'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(tmp_path), 'commit', '-qm', 'fixture'], check=True, capture_output=True)
    with pytest.raises(ValueError, match='tag'):
        source_identity(tmp_path, '1.2.0', dev=False)
    subprocess.run(['git', '-C', str(tmp_path), 'tag', 'v1.2.0'], check=True, capture_output=True)
    assert source_identity(tmp_path, '1.2.0', dev=False)['mode'] == 'release'
    (tmp_path / 'test.txt').write_text('dirty')
    with pytest.raises(ValueError, match='clean'):
        source_identity(tmp_path, '1.2.0', dev=False)
    assert source_identity(tmp_path, '1.2.0', dev=True)['mode'] == 'development'


@pytest.mark.parametrize('name', ['../escape', 'engine/../../escape', 'C:/escape', 'engine\\escape', 'engine/NUL'])
def test_archive_extraction_rejects_unsafe_names_before_writes(tmp_path, name):
    from scripts.check_native_mcp_bundle import extract_checked
    archive = tmp_path / 'bad.mcpb'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(name, b'bad')
    with pytest.raises(ValueError):
        extract_checked(archive, tmp_path / 'out', '1.2.0', dev=True)
    assert not (tmp_path / 'out').exists()


def test_frozen_source_identity_cannot_relabel_stale_binary(tmp_path):
    from scripts.build_native_mcp_bundle import frozen_identity
    folder = tmp_path / '_internal/flywheel-metadata'; folder.mkdir(parents=True)
    (folder / 'flywheel-frozen-source.json').write_text(json.dumps({
        'schema': 'flywheel.frozen-source/v1', 'head': 'a' * 40, 'version': '1.2.0', 'source_dirty': False}))
    with pytest.raises(ValueError, match='source identity'):
        frozen_identity(tmp_path, {'head': 'b' * 40, 'version': '1.2.0', 'mode': 'release'})


def test_native_companion_release_wiring_is_gated_before_publish():
    candidate = Path('.github/workflows/desktop-release.yml').read_text()
    publish = Path('.github/workflows/windows-publish.yml').read_text()
    assert 'scripts/check_native_mcp_bundle.py --archive' in candidate
    assert 'scripts/build_native_mcp_bundle.py --engine' in candidate
    assert '--collect-toc build/flywheel-gateway/COLLECT-00.toc' in candidate
    assert 'native_mcp_sha256:' in publish
    assert publish.index('scripts/build_native_mcp_bundle.py --verify') < publish.index('gh release create')
    assert '@nativeMcp $nativeSums' in publish
    assert '--dev' not in candidate


def test_freeze_rejects_ignored_site_credentials_before_collect(tmp_path):
    from scripts.frozen_tool_metadata import validate_public_data
    site = tmp_path / 'site'; site.mkdir()
    (site / 'session.token').write_text('synthetic credential fixture')
    with pytest.raises(ValueError):
        validate_public_data(tmp_path)
