"""Native packages reject ambiguous payloads and never need a user runtime."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import zipfile

import pytest

from claude_plugin_helpers import load, ROOT

VERSION = load('claude_plugin_rules').bundled_version(ROOT)


@pytest.fixture(autouse=True)
def isolated_native_validator(monkeypatch):
    # Archive fixtures contain PE headers, not runnable programs. Real protocol
    # acceptance is covered by check_native_articulate and binary qualification.
    def checked(exe, version):
        return {'status': 'PASS', 'version': version,
                'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
    monkeypatch.setattr(load('archive_native_articulate'), 'check_native', checked)


def payload(tmp_path):
    stage = tmp_path / 'stage'
    stage.mkdir()
    pe = bytearray(256)
    pe[:2] = b'MZ'
    struct.pack_into('<I', pe, 60, 128)
    pe[128:132] = b'PE\0\0'
    struct.pack_into('<H', pe, 132, 0x8664)
    (stage / 'articulate-local.exe').write_bytes(pe)
    (stage / 'LICENSE').write_text('source license')
    (stage / 'PYTHON-LICENSE.txt').write_text('runtime license')
    (stage / 'PYINSTALLER-LICENSE.txt').write_text('bootloader license')
    return stage


def test_native_archives_have_binary_manifest_and_identical_payload(tmp_path):
    mod = load('archive_native_articulate')
    stage = payload(tmp_path)
    first = mod.archive(stage, tmp_path / 'one', VERSION, mode='dev')
    second = mod.archive(stage, tmp_path / 'two', VERSION, mode='dev')
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]
    for path in first:
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read('manifest.json'))
            assert m['server']['type'] == 'binary'
            assert m['compatibility'] == {'platforms': ['win32']}
            assert 'user_config' not in m
            assert m['server']['mcp_config']['args'] == []
            assert z.read('server/articulate-local.exe') == (stage / 'articulate-local.exe').read_bytes()
            assert 'development' in z.read('README.md').decode().lower()


@pytest.mark.parametrize('name', ['.env', 'evil.py', 'other.exe', 'subdir', '.git'])
def test_unexpected_payload_is_rejected(tmp_path, name):
    stage = payload(tmp_path)
    (stage / name).write_text('not allowed')
    with pytest.raises(ValueError, match='unsupported'):
        load('archive_native_articulate').archive(stage, tmp_path / 'out', VERSION, mode='dev')


@pytest.mark.parametrize('change', ['missing', 'linux', 'arm'])
def test_wrong_or_missing_executable_is_rejected(tmp_path, change):
    stage = payload(tmp_path)
    exe = stage / 'articulate-local.exe'
    if change == 'missing':
        exe.unlink()
    elif change == 'linux':
        exe.write_bytes(b'\x7fELF')
    else:
        data = bytearray(exe.read_bytes())
        struct.pack_into('<H', data, 132, 0xaa64)
        exe.write_bytes(data)
    with pytest.raises(ValueError):
        load('archive_native_articulate').archive(stage, tmp_path / 'out', VERSION, mode='dev')


@pytest.mark.parametrize('version', ['../escape', '1/0', '1\\0', 'C:bad', '0.5.2\n'])
def test_archive_names_cannot_escape(tmp_path, version):
    with pytest.raises(ValueError, match='version'):
        load('archive_native_articulate').archive(payload(tmp_path), tmp_path / 'out', version, mode='dev')


def test_nested_output_and_overwrite_are_rejected(tmp_path):
    mod = load('archive_native_articulate')
    stage = payload(tmp_path)
    with pytest.raises(ValueError, match='outside'):
        mod.archive(stage, stage / 'out', VERSION, mode='dev')
    mod.archive(stage, tmp_path / 'out', VERSION, mode='dev')
    with pytest.raises(FileExistsError):
        mod.archive(stage, tmp_path / 'out', VERSION, mode='dev')


def test_link_payload_is_rejected(tmp_path):
    stage = payload(tmp_path)
    external = tmp_path / 'external'
    external.mkdir()
    try:
        (stage / 'linked').symlink_to(external, target_is_directory=True)
    except OSError:
        if sys.platform != 'win32':
            pytest.skip('symlinks unavailable')
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(stage / 'linked'), str(external)], check=True, capture_output=True)
    with pytest.raises(ValueError, match='reparse|link'):
        load('archive_native_articulate').archive(stage, tmp_path / 'out', VERSION, mode='dev')


def test_native_entry_rejects_arguments_before_import():
    result = subprocess.run([sys.executable, '-I', '-S', str(ROOT / 'scripts/native_articulate_entry.py'), '--backend=openai'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'accepts no arguments' in result.stderr
    assert not result.stdout
