import hashlib
import os
from pathlib import Path
import shutil

import pytest

from harness.evidence_json import canonical_bytes
from harness.codex_managed_profile import prepare_codex_profile
from harness import codex_managed_profile_manifest as manifest


def _exe(tmp_path):
    path = tmp_path / 'codex.exe'
    path.write_bytes(b'fake codex executable')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _profile(tmp_path):
    state, workspace, policy = tmp_path / 'state', tmp_path / 'workspace', tmp_path / 'policy'
    state.mkdir(); workspace.mkdir(); policy.mkdir()
    return prepare_codex_profile(state, workspace=workspace, owner_ref='owner-1'), policy


def _generated_home(profile):
    for name in ('.personality_migration', 'installation_id'):
        (profile.home / name).write_text('ok', encoding='utf-8')
    for name in ('goals_1.sqlite', 'goals_1.sqlite-shm', 'goals_1.sqlite-wal',
                 'logs_2.sqlite', 'logs_2.sqlite-shm', 'logs_2.sqlite-wal',
                 'memories_1.sqlite', 'memories_1.sqlite-shm', 'memories_1.sqlite-wal',
                 'state_5.sqlite', 'state_5.sqlite-shm', 'state_5.sqlite-wal'):
        (profile.home / name).write_bytes(b'')
    (profile.home / 'tmp').mkdir()
    system = profile.home / 'skills' / '.system' / 'openai-docs'
    system.mkdir(parents=True)
    (profile.home / 'skills' / '.system' / '.codex-system-skills.marker').write_text('system', encoding='utf-8')
    (system / 'SKILL.md').write_text('builtin skill', encoding='utf-8')


def _write_arg0_tree(profile, executable, suffix):
    tmp = profile.home / 'tmp'
    if tmp.exists():
        shutil.rmtree(tmp)
    leaf = tmp / 'arg0' / f'codex-arg0{suffix}'
    leaf.mkdir(parents=True)
    shim = f'@echo off\n"{executable}" --codex-run-as-apply-patch %*\n'
    (leaf / '.lock').write_bytes(b'')
    (leaf / 'apply_patch.bat').write_bytes(shim.encode('utf-8'))
    (leaf / 'applypatch.bat').write_bytes(shim.encode('utf-8'))


def _base_inventory(tmp_path, profile, policy, executable, digest):
    return manifest.capture_generated_profile_manifest(
        profile, executable=executable, executable_sha256=digest, codex_version='0.144.6',
        bootstrap_receipt_sha256='d' * 64, policy_root=policy)


def _login_receipt(tmp_path, profile, inventory, digest, *, paths=('auth.json',),
                   executable_sha256=None, success=True, cleanup=True,
                   source_sha=None, mode='browser', login_id='login-1',
                   login_hash=None):
    data = {
        'schema': manifest.LOGIN_RECEIPT_SCHEMA,
        'source_inventory_sha256': source_sha or inventory.sha256,
        'codex': {'version': '0.144.6', 'executable_sha256': executable_sha256 or digest},
        'bindings': {
            'home_identity': profile.home_identity.to_json_dict(),
            'workspace_identity': profile.workspace_identity.to_json_dict(),
        },
        'login': {'mode': mode,
                  'login_id_sha256': login_hash or hashlib.sha256(login_id.encode()).hexdigest()},
        'completion': {'success': success},
        'cleanup': {'exited': cleanup, 'job_closed': cleanup, 'stderr_drain_complete': cleanup},
        'auth_entries': [{'path': path, 'kind': 'file', 'max_bytes': 4096} for path in paths],
    }
    raw = canonical_bytes(data)
    path = tmp_path / ('login-receipt-' + hashlib.sha256(raw).hexdigest()[:8] + '.json')
    path.write_bytes(raw)
    return manifest.CodexProfileLoginReceiptRef(path=path,
        sha256=hashlib.sha256(raw).hexdigest())


def test_auth_extension_uses_receipt_paths_without_reading_auth_contents(tmp_path, monkeypatch):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    (profile.home / 'auth.json').write_text('secret-token-material', encoding='utf-8')
    receipt = _login_receipt(tmp_path, profile, inventory, digest)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if Path(path).name == 'auth.json':
            raise AssertionError('auth content was read')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    extended = manifest.extend_manifest_after_explicit_login(
        profile, inventory, executable=executable, executable_sha256=digest,
        codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
        expected_login_id='login-1', expected_mode='browser')
    data = manifest.read_restart_manifest(extended)
    row = next(item for item in data['root_entries'] if item['path'] == 'auth.json')
    assert row['policy'] == 'auth_metadata_only'
    assert data['auth_extension']['login_receipt_sha256'] == receipt.sha256
    manifest.verify_restart_inventory(profile, extended,
        executable=executable, executable_sha256=digest)


def test_auth_extension_refreshes_valid_harness_tmp_tree_after_login(tmp_path):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    _write_arg0_tree(profile, executable, 'ABC123')
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    _write_arg0_tree(profile, executable, 'XYZ789')
    (profile.home / 'auth.json').write_text('secret', encoding='utf-8')
    receipt = _login_receipt(tmp_path, profile, inventory, digest)

    extended = manifest.extend_manifest_after_explicit_login(
        profile, inventory, executable=executable, executable_sha256=digest,
        codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
        expected_login_id='login-1', expected_mode='browser')

    data = manifest.read_restart_manifest(extended)
    tmp_row = next(item for item in data['root_entries'] if item['path'] == 'tmp')
    assert tmp_row['tree']['dirs'] == ['tmp/arg0', 'tmp/arg0/codex-arg0XYZ789']
    manifest.verify_restart_inventory(profile, extended,
        executable=executable, executable_sha256=digest)


def test_auth_extension_still_rejects_unowned_tmp_tree_after_login(tmp_path):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    _write_arg0_tree(profile, executable, 'ABC123')
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    shutil.rmtree(profile.home / 'tmp')
    (profile.home / 'tmp').mkdir()
    (profile.home / 'tmp' / 'unknown.txt').write_text('not harness owned',
                                                      encoding='utf-8')
    (profile.home / 'auth.json').write_text('secret', encoding='utf-8')
    receipt = _login_receipt(tmp_path, profile, inventory, digest)

    with pytest.raises(manifest.CodexProfileManifestError,
                       match='MANIFEST_TREE_MISMATCH'):
        manifest.extend_manifest_after_explicit_login(
            profile, inventory, executable=executable, executable_sha256=digest,
            codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
            expected_login_id='login-1', expected_mode='browser')


def test_auth_extension_rejects_unlisted_paths_and_bad_receipt_bindings(tmp_path):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    (profile.home / 'auth.json').write_text('secret', encoding='utf-8')
    (profile.home / 'auth2.json').write_text('unlisted', encoding='utf-8')
    receipt = _login_receipt(tmp_path, profile, inventory, digest)
    with pytest.raises(manifest.CodexProfileManifestError):
        manifest.extend_manifest_after_explicit_login(
            profile, inventory, executable=executable, executable_sha256=digest,
            codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
            expected_login_id='login-1', expected_mode='browser')
    (profile.home / 'auth2.json').unlink()
    for bad in (
        manifest.CodexProfileLoginReceiptRef(path=receipt.path, sha256='0' * 64),
        _login_receipt(tmp_path, profile, inventory, digest, executable_sha256='0' * 64),
        _login_receipt(tmp_path, profile, inventory, digest, source_sha='1' * 64),
        _login_receipt(tmp_path, profile, inventory, digest, success=False),
        _login_receipt(tmp_path, profile, inventory, digest, cleanup=False),
    ):
        with pytest.raises(manifest.CodexProfileManifestError):
            manifest.extend_manifest_after_explicit_login(
                profile, inventory, executable=executable, executable_sha256=digest,
                codex_version='0.144.6', login_receipt=bad, policy_root=policy,
                expected_login_id='login-1', expected_mode='browser')


def test_auth_extension_rejects_receipt_not_bound_to_completed_login_context(tmp_path):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    (profile.home / 'auth.json').write_text('secret', encoding='utf-8')
    for receipt in (
        _login_receipt(tmp_path, profile, inventory, digest, mode='device_code'),
        _login_receipt(tmp_path, profile, inventory, digest, login_id='other-login'),
        _login_receipt(tmp_path, profile, inventory, digest, login_hash='0' * 64),
    ):
        with pytest.raises(manifest.CodexProfileManifestError):
            manifest.extend_manifest_after_explicit_login(
                profile, inventory, executable=executable, executable_sha256=digest,
                codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
                expected_login_id='login-1', expected_mode='browser')


def test_auth_extension_rejects_changed_bootstrap_state_config_and_profile(tmp_path):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    receipt = _login_receipt(tmp_path, profile, inventory, digest)
    (profile.home / 'auth.json').write_text('secret', encoding='utf-8')
    other = tmp_path / 'other'
    other.mkdir()
    other_profile, _ = _profile(other)
    with pytest.raises(manifest.CodexProfileManifestError):
        manifest.extend_manifest_after_explicit_login(
            other_profile, inventory, executable=executable, executable_sha256=digest,
            codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
            expected_login_id='login-1', expected_mode='browser')
    config = profile.home / 'config.toml'
    original_config = config.read_text(encoding='utf-8')
    config.write_text(original_config + '\n# drift\n', encoding='utf-8')
    with pytest.raises(manifest.CodexProfileManifestError):
        manifest.extend_manifest_after_explicit_login(
            profile, inventory, executable=executable, executable_sha256=digest,
            codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
            expected_login_id='login-1', expected_mode='browser')
    config.write_text(original_config, encoding='utf-8')
    builtin = profile.home / 'skills' / '.system' / 'openai-docs' / 'SKILL.md'
    builtin.write_text('changed', encoding='utf-8')
    with pytest.raises(manifest.CodexProfileManifestError):
        manifest.extend_manifest_after_explicit_login(
            profile, inventory, executable=executable, executable_sha256=digest,
            codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
            expected_login_id='login-1', expected_mode='browser')


def test_auth_extension_rejects_oversize_hardlinked_and_reparse_auth_files(tmp_path):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    (profile.home / 'auth.json').write_text('x' * 4097, encoding='utf-8')
    receipt = _login_receipt(tmp_path, profile, inventory, digest)
    with pytest.raises(manifest.CodexProfileManifestError):
        manifest.extend_manifest_after_explicit_login(
            profile, inventory, executable=executable, executable_sha256=digest,
            codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
            expected_login_id='login-1', expected_mode='browser')
    (profile.home / 'auth.json').write_text('secret', encoding='utf-8')
    try:
        os.link(profile.home / 'auth.json', tmp_path / 'auth-hardlink')
    except OSError:
        pass
    else:
        with pytest.raises(manifest.CodexProfileManifestError):
            manifest.extend_manifest_after_explicit_login(
                profile, inventory, executable=executable, executable_sha256=digest,
                codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
                expected_login_id='login-1', expected_mode='browser')
        (tmp_path / 'auth-hardlink').unlink()
    (profile.home / 'auth.json').unlink()
    target = tmp_path / 'auth-target'
    target.write_text('secret', encoding='utf-8')
    try:
        (profile.home / 'auth.json').symlink_to(target)
    except OSError:
        return
    with pytest.raises(manifest.CodexProfileManifestError):
        manifest.extend_manifest_after_explicit_login(
            profile, inventory, executable=executable, executable_sha256=digest,
            codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
            expected_login_id='login-1', expected_mode='browser')


def test_auth_extension_replay_rejects_new_roots_after_success(tmp_path):
    profile, policy = _profile(tmp_path)
    _generated_home(profile)
    executable, digest = _exe(tmp_path)
    inventory = _base_inventory(tmp_path, profile, policy, executable, digest)
    receipt = _login_receipt(tmp_path, profile, inventory, digest)
    (profile.home / 'auth.json').write_text('secret', encoding='utf-8')
    extended = manifest.extend_manifest_after_explicit_login(
        profile, inventory, executable=executable, executable_sha256=digest,
        codex_version='0.144.6', login_receipt=receipt, policy_root=policy,
        expected_login_id='login-1', expected_mode='browser')
    (profile.home / 'auth2.json').write_text('unlisted', encoding='utf-8')
    with pytest.raises(manifest.CodexProfileManifestError):
        manifest.verify_restart_inventory(profile, extended,
            executable=executable, executable_sha256=digest)
