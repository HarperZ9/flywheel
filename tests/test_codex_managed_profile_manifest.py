import hashlib
import importlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from harness.private_artifact_fs import open_artifact_root
from harness.codex_managed_profile import prepare_codex_profile, lease_codex_profile


def manifest_module():
    return importlib.import_module('harness.codex_managed_profile_manifest')


def _exe(tmp_path):
    path = tmp_path / 'codex.exe'
    path.write_bytes(b'fake codex executable')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _prepared(tmp_path):
    state = tmp_path / 'state'; workspace = tmp_path / 'workspace'; policy = tmp_path / 'policy'
    state.mkdir(); workspace.mkdir(); policy.mkdir()
    return prepare_codex_profile(state, workspace=workspace, owner_ref='owner-1'), policy


def _generated_home(profile):
    for name in ('.personality_migration', 'installation_id'):
        (profile.home / name).write_text('ok', encoding='utf-8')
    for name in ('goals_1.sqlite', 'goals_1.sqlite-shm', 'goals_1.sqlite-wal',
                 'logs_2.sqlite', 'logs_2.sqlite-shm', 'logs_2.sqlite-wal',
                 'memories_1.sqlite', 'memories_1.sqlite-shm', 'memories_1.sqlite-wal',
                 'state_5.sqlite', 'state_5.sqlite-shm', 'state_5.sqlite-wal'):
        (profile.home / name).write_bytes(b'sqlite bytes must not be read')
    (profile.home / 'skills' / '.system' / 'openai-docs').mkdir(parents=True)
    (profile.home / 'skills' / '.system' / '.codex-system-skills.marker').write_text('system', encoding='utf-8')
    (profile.home / 'skills' / '.system' / 'openai-docs' / 'SKILL.md').write_text('builtin skill', encoding='utf-8')
    (profile.home / 'tmp').mkdir()


def _apply_patch_shim(executable):
    return f'@echo off\n"{executable}" --codex-run-as-apply-patch %*\n'.encode('utf-8')


def _generated_arg0_tmp(profile, executable, dirname='codex-arg03K7TBX'):
    root = profile.home / 'tmp' / 'arg0' / dirname
    root.mkdir(parents=True)
    (root / '.lock').write_bytes(b'')
    for name in ('apply_patch.bat', 'applypatch.bat'):
        (root / name).write_bytes(_apply_patch_shim(executable))


def test_manifest_validation_rejects_malformed_policy_and_wildcards(tmp_path):
    mod = manifest_module()
    valid = {
        'schema': mod.MANIFEST_SCHEMA,
        'codex': {'version': '0.144.6', 'executable_sha256': 'a' * 64},
        'bindings': {
            'home_identity': {'platform': 'windows', 'device': 1, 'inode': 2},
            'workspace_identity': {'platform': 'windows', 'device': 3, 'inode': 4},
            'config_sha256': 'b' * 64,
        },
        'bootstrap': {'receipt_sha256': 'c' * 64},
        'root_entries': [
            {'path': 'config.toml', 'kind': 'file', 'policy': 'exact_sha256', 'sha256': 'b' * 64},
            {'path': 'runtime', 'kind': 'dir', 'policy': 'harness_runtime_tree'},
        ],
        'builtin_tree': {'root': 'skills/.system', 'files': [], 'dirs': []},
        'dynamic_provider_files': {'content_read': False, 'exact_names_only': True},
    }
    assert mod.manifest_root_names(valid) == {'config.toml', 'runtime'}
    for mutate in (
        lambda v: v.update(schema='bad'),
        lambda v: v['root_entries'].append({'path': '*.sqlite', 'kind': 'file', 'policy': 'sqlite_metadata_only'}),
        lambda v: v['root_entries'].append({'path': 'config.toml', 'kind': 'file', 'policy': 'exact_sha256', 'sha256': 'b' * 64}),
        lambda v: v['root_entries'][0].update(policy='wildcard_allow'),
        lambda v: v['codex'].pop('executable_sha256'),
        lambda v: v['root_entries'].pop(1),
    ):
        candidate = {**valid, 'codex': dict(valid['codex']), 'bindings': dict(valid['bindings']),
                     'bootstrap': dict(valid['bootstrap']),
                     'root_entries': [dict(row) for row in valid['root_entries']],
                     'builtin_tree': dict(valid['builtin_tree']),
                     'dynamic_provider_files': dict(valid['dynamic_provider_files'])}
        mutate(candidate)
        with pytest.raises(mod.CodexProfileManifestError):
            mod.validate_restart_manifest(candidate)


def test_manifest_schema_rejects_generic_root_tree_policy(tmp_path):
    mod = manifest_module()
    manifest = {
        'schema': mod.MANIFEST_SCHEMA,
        'codex': {'version': '0.144.6', 'executable_sha256': 'a' * 64},
        'bindings': {
            'home_identity': {'platform': 'windows', 'device': 1, 'inode': 2},
            'workspace_identity': {'platform': 'windows', 'device': 3, 'inode': 4},
            'config_sha256': 'b' * 64,
        },
        'bootstrap': {'receipt_sha256': 'c' * 64},
        'root_entries': [
            {'path': 'config.toml', 'kind': 'file', 'policy': 'exact_sha256', 'sha256': 'b' * 64},
            {'path': 'runtime', 'kind': 'dir', 'policy': 'harness_runtime_tree'},
            {'path': 'tmp', 'kind': 'dir', 'policy': 'exact_metadata_tree', 'tree': [
                {'path': 'provider-owned.bat', 'kind': 'file', 'max_bytes': 4096},
            ]},
        ],
        'builtin_tree': {'root': 'skills/.system', 'files': [], 'dirs': []},
        'dynamic_provider_files': {'content_read': False, 'exact_names_only': True},
    }
    with pytest.raises(mod.CodexProfileManifestError):
        mod.validate_restart_manifest(manifest)


def test_capture_manifest_hashes_builtins_and_only_records_sqlite_metadata(tmp_path, monkeypatch):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    original = Path.read_bytes
    read_paths = []

    def recording_read(path):
        read_paths.append(Path(path).name)
        if Path(path).suffix.startswith('.sqlite') or 'sqlite' in Path(path).name:
            raise AssertionError('sqlite content was read')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', recording_read)
    ref = mod.capture_generated_profile_manifest(
        profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
        bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    data = mod.read_restart_manifest(ref)

    assert ref.path.is_relative_to(policy)
    assert not ref.path.is_relative_to(profile.home)
    assert data['codex']['executable_sha256'] == exe_hash
    assert data['bindings']['config_sha256'] == profile.config_sha256
    assert mod.manifest_root_names(data) == {p.name.casefold() for p in profile.home.iterdir()}
    assert {row['path'] for row in data['builtin_tree']['files']} == {
        'skills/.system/.codex-system-skills.marker',
        'skills/.system/openai-docs/SKILL.md',
    }
    assert all('sqlite' not in name for name in read_paths)


def test_capture_admits_valid_codex_arg0_temp_tree_rotation(tmp_path):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    _generated_arg0_tmp(profile, exe)
    ref = mod.capture_generated_profile_manifest(
        profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
        bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    data = mod.read_restart_manifest(ref)
    row = next(item for item in data['root_entries'] if item['path'] == 'tmp')
    assert row['policy'] == 'codex_arg0_temp_tree'
    assert row['tree']['dirs'] == ['tmp/arg0', 'tmp/arg0/codex-arg03K7TBX']
    assert {item['path'] for item in row['tree']['files']} == {
        'tmp/arg0/codex-arg03K7TBX/.lock',
        'tmp/arg0/codex-arg03K7TBX/apply_patch.bat',
        'tmp/arg0/codex-arg03K7TBX/applypatch.bat',
    }
    shutil.rmtree(profile.home / 'tmp' / 'arg0' / 'codex-arg03K7TBX')
    _generated_arg0_tmp(profile, exe, 'codex-arg0ABC123')
    (profile.home / 'models_cache.json').write_text('{"data":[]}', encoding='utf-8')
    mod.verify_restart_inventory(profile, ref, executable=exe, executable_sha256=exe_hash)
    (profile.home / 'tmp' / 'arg0' / 'codex-arg0ABC123' / 'applypatch.bat').write_text(
        '@echo changed\r\n', encoding='utf-8')
    with pytest.raises(mod.CodexProfileManifestError):
        mod.verify_restart_inventory(profile, ref, executable=exe, executable_sha256=exe_hash)

def test_capture_rejects_arg0_temp_shims_not_bound_to_reviewed_executable(tmp_path):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    _generated_arg0_tmp(profile, exe)
    leaf = profile.home / 'tmp' / 'arg0' / 'codex-arg03K7TBX'
    (leaf / 'applypatch.bat').write_bytes(b'@echo off\nmalicious.exe %*\n')
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    (leaf / 'applypatch.bat').write_bytes(_apply_patch_shim(exe))
    other = tmp_path / 'other-codex.exe'
    other.write_bytes(b'different executable')
    (leaf / 'apply_patch.bat').write_bytes(_apply_patch_shim(other))
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)

def test_read_manifest_uses_pinned_policy_read(tmp_path, monkeypatch):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    ref = mod.capture_generated_profile_manifest(
        profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
        bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    original = Path.read_bytes

    def blocked_direct_read(path):
        if Path(path) == ref.path:
            raise AssertionError('manifest read bypassed private artifact custody')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', blocked_direct_read)
    assert mod.read_restart_manifest(ref)['schema'] == mod.MANIFEST_SCHEMA


def test_capture_refuses_unknown_generated_entry_and_executable_mismatch(tmp_path):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    (profile.home / 'future-config').mkdir()
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    (profile.home / 'future-config').rmdir()
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256='0' * 64, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)


def test_capture_requires_prepared_runtime_tree(tmp_path):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    shutil.rmtree(profile.home / 'runtime')
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)


def test_capture_refuses_unlisted_sqlite_names_and_provider_tmp_files(tmp_path):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    (profile.home / 'goals_2.sqlite-wal').write_bytes(b'unreviewed wal')
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    (profile.home / 'goals_2.sqlite-wal').unlink()
    (profile.home / 'tmp' / 'arg0').write_text('codex', encoding='utf-8')
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction probe')
def test_capture_rejects_builtin_junction_without_following(tmp_path):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('do not inventory through junction', encoding='utf-8')
    junction = profile.home / 'skills' / '.system' / 'openai-docs' / 'junction'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(outside)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(result.stderr or result.stdout)
    try:
        with pytest.raises(mod.CodexProfileManifestError):
            mod.capture_generated_profile_manifest(
                profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
                bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    finally:
        if junction.exists():
            junction.rmdir()


def test_conflicting_existing_manifest_is_not_overwritten(tmp_path):
    mod = manifest_module()
    profile, policy = _prepared(tmp_path)
    _generated_home(profile)
    exe, exe_hash = _exe(tmp_path)
    ref = mod.capture_generated_profile_manifest(
        profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
        bootstrap_receipt_sha256='d' * 64, policy_root=policy)
    ref.path.write_text('changed', encoding='utf-8')
    with pytest.raises(mod.CodexProfileManifestError):
        mod.capture_generated_profile_manifest(
            profile, executable=exe, executable_sha256=exe_hash, codex_version='0.144.6',
            bootstrap_receipt_sha256='d' * 64, policy_root=policy)
