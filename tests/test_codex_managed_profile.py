"""Owned Codex profile boundaries, without provider or credential access."""
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import tomllib

import pytest

def module():
    name = 'harness.codex_managed_profile'
    assert importlib.util.find_spec(name), 'Managed profile missing'
    return importlib.import_module(name)

def prepare(tmp_path):
    state, workspace = tmp_path / 'state', tmp_path / 'workspace'
    state.mkdir()
    workspace.mkdir()
    return module().prepare_codex_profile(state, workspace=workspace, owner_ref='owner-1')

def prepare_named(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    return prepare(root)

def test_profile_is_stable_scoped_and_has_explicit_policy(tmp_path):
    profile = prepare(tmp_path)
    again = module().prepare_codex_profile(tmp_path / 'state',
        workspace=tmp_path / 'workspace', owner_ref='owner-1')
    assert profile == again
    config = tomllib.loads((profile.home / 'config.toml').read_text())
    assert config['projects'][str(profile.workspace).lower()]['trust_level'] == 'untrusted'
    assert config['approval_policy'] == 'on-request'
    assert config['approvals_reviewer'] == 'user'
    assert config['sandbox_mode'] == 'read-only'
    assert config['web_search'] == 'disabled'
    assert config['mcp_servers'] == {}
    assert config['notify'] == []
    assert config['cli_auth_credentials_store'] == 'file'
    assert config['features'] == {'hooks': False, 'apps': False, 'plugins': False}
    assert not (profile.home / 'auth.json').exists()
    assert profile.home.is_relative_to(tmp_path / 'state')

def test_existing_different_config_is_not_overwritten(tmp_path):
    profile = prepare(tmp_path)
    (profile.home / 'config.toml').write_text('model="changed"')
    with pytest.raises(module().CodexProfileError, match='PROFILE_CONFLICT'):
        module().prepare_codex_profile(tmp_path / 'state', workspace=profile.workspace,
                                       owner_ref='owner-1')
    assert (profile.home / 'config.toml').read_text() == 'model="changed"'

def test_different_owner_gets_separate_profile(tmp_path):
    first = prepare(tmp_path)
    second = module().prepare_codex_profile(tmp_path / 'state',
        workspace=first.workspace, owner_ref='owner-2')
    assert first.home != second.home

@pytest.mark.parametrize('in_workspace', [True, False])
def test_workspace_and_profile_state_must_not_overlap(tmp_path, in_workspace):
    child = tmp_path / 'child'
    child.mkdir()
    state, workspace = (child, tmp_path) if in_workspace else (tmp_path, child)
    with pytest.raises(module().CodexProfileError, match='PROFILE_PATH_OVERLAP'):
        module().prepare_codex_profile(state, workspace=workspace, owner_ref='owner-1')

def test_environment_does_not_inherit_credentials_or_provider_settings(tmp_path, monkeypatch):
    profile = prepare(tmp_path)
    for key in ('OPENAI_API_KEY', 'CODEX_HOME', 'ANTHROPIC_API_KEY', 'CODEX_CONFIG',
                'HTTP_PROXY', 'NODE_OPTIONS', 'RUST_LOG'):
        monkeypatch.setenv(key, 'do-not-inherit')
    env = module().codex_profile_environment(profile)
    assert env['CODEX_HOME'] == str(profile.home)
    assert 'do-not-inherit' not in env.values()
    assert Path(env['TEMP']).is_dir()
    assert Path(env['HOME']).is_relative_to(profile.home)

@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_lease_prevents_config_and_binary_mutation_and_releases(tmp_path):
    profile = prepare(tmp_path)
    executable = tmp_path / 'fake.exe'
    executable.write_bytes(b'synthetic executable, never run')
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    with module().lease_codex_profile(profile, executable=executable, executable_sha256=digest):
        for path in (profile.home / 'config.toml', executable):
            with pytest.raises(OSError):
                path.write_bytes(b'changed')
        with pytest.raises(OSError):
            profile.home.rename(tmp_path / 'moved-home')
    executable.write_bytes(b'lease released')
    assert executable.read_bytes() == b'lease released'

@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_changed_binary_refuses_lease(tmp_path):
    profile = prepare(tmp_path)
    executable = tmp_path / 'fake.exe'
    executable.write_bytes(b'changed')
    with pytest.raises(module().CodexProfileError, match='PROFILE_BINDING_DRIFT'):
        with module().lease_codex_profile(profile, executable=executable,
                                         executable_sha256='0' * 64):
            pytest.fail('drifted executable admitted')

@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
@pytest.mark.parametrize('entry', ['rules', 'future-exec-surface', 'unknown.toml'])
def test_added_execution_configuration_refuses_lease(tmp_path, entry):
    profile = prepare(tmp_path)
    if entry.endswith('.toml'):
        (profile.home / entry).write_text('unknown=true')
    else:
        (profile.home / entry).mkdir()
    executable = tmp_path / 'fake.exe'
    executable.write_bytes(b'fake')
    with pytest.raises(module().CodexProfileError, match='PROFILE_UNREVIEWED_SETTINGS'):
        with module().lease_codex_profile(profile, executable=executable,
                executable_sha256=hashlib.sha256(b'fake').hexdigest()):
            pytest.fail('unreviewed rule directory accepted')

@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_exception_inside_lease_is_preserved_and_locks_release(tmp_path):
    profile = prepare(tmp_path)
    exe = tmp_path / 'fake.exe'
    exe.write_bytes(b'fake')
    with pytest.raises(LookupError, match='operation failed'):
        with module().lease_codex_profile(profile, executable=exe,
                executable_sha256=hashlib.sha256(b'fake').hexdigest()):
            raise LookupError('operation failed')
    exe.write_bytes(b'closed')

@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_hardlinked_config_is_rejected(tmp_path):
    profile = prepare(tmp_path)
    os.link(profile.home / 'config.toml', tmp_path / 'config-alias.toml')
    exe = tmp_path / 'fake.exe'
    exe.write_bytes(b'fake')
    with pytest.raises(module().CodexProfileError, match='PROFILE_BINDING_DRIFT'):
        with module().lease_codex_profile(profile, executable=exe,
                executable_sha256=hashlib.sha256(b'fake').hexdigest()):
            pytest.fail('config alias accepted')

@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_lease_requires_runtime_root_for_clean_and_restart(tmp_path):
    executable, digest = _restart_executable(tmp_path)
    clean = prepare_named(tmp_path, 'clean')
    shutil.rmtree(clean.home / 'runtime')
    with pytest.raises(module().CodexProfileError, match='PROFILE_UNREVIEWED_SETTINGS'):
        with module().lease_codex_profile(clean, executable=executable, executable_sha256=digest):
            pytest.fail('clean profile without runtime accepted')
    restart = prepare_named(tmp_path, 'restart')
    _generated_restart_home(restart)
    inventory = _restart_inventory(tmp_path, restart, executable, digest)
    shutil.rmtree(restart.home / 'runtime')
    with pytest.raises(module().CodexProfileError, match='PROFILE_UNREVIEWED_SETTINGS'):
        with module().lease_codex_profile(restart, executable=executable,
                executable_sha256=digest, inventory=inventory):
            pytest.fail('restart profile without runtime accepted')

@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
@pytest.mark.parametrize('restart', [False, True])
def test_lease_yields_before_resume_recheck_for_root_insertions(tmp_path, restart):
    profile = prepare(tmp_path)
    executable, digest = _restart_executable(tmp_path)
    inventory = None
    if restart:
        _generated_restart_home(profile)
        inventory = _restart_inventory(tmp_path, profile, executable, digest)
    with module().lease_codex_profile(profile, executable=executable,
            executable_sha256=digest, inventory=inventory) as before_resume:
        assert callable(before_resume)
        (profile.home / 'future-root').mkdir()
        with pytest.raises(module().CodexProfileError, match='PROFILE_UNREVIEWED_SETTINGS'):
            before_resume()


def _manifest_module():
    return importlib.import_module('harness.codex_managed_profile_manifest')


def _restart_executable(tmp_path):
    executable = tmp_path / 'fake-codex.exe'
    executable.write_bytes(b'synthetic codex executable')
    return executable, hashlib.sha256(executable.read_bytes()).hexdigest()


def _generated_restart_home(profile):
    (profile.home / '.personality_migration').write_text('ok', encoding='utf-8')
    (profile.home / 'installation_id').write_text('00000000-0000-0000-0000-000000000000', encoding='utf-8')
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


def _restart_inventory(tmp_path, profile, executable, digest):
    policy = tmp_path / 'policy'
    policy.mkdir(exist_ok=True)
    return _manifest_module().capture_generated_profile_manifest(
        profile, executable=executable, executable_sha256=digest, codex_version='0.144.6',
        bootstrap_receipt_sha256='d' * 64, policy_root=policy)


@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_restart_inventory_admits_generated_home_but_clean_mode_stays_strict(tmp_path):
    profile = prepare(tmp_path)
    _generated_restart_home(profile)
    executable, digest = _restart_executable(tmp_path)
    with pytest.raises(module().CodexProfileError, match='PROFILE_UNREVIEWED_SETTINGS'):
        with module().lease_codex_profile(profile, executable=executable,
                executable_sha256=digest):
            pytest.fail('generated profile accepted without inventory')
    inventory = _restart_inventory(tmp_path, profile, executable, digest)
    with module().lease_codex_profile(profile, executable=executable,
            executable_sha256=digest, inventory=inventory):
        pass


@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_restart_inventory_rejects_new_roots_and_changed_builtins(tmp_path):
    profile = prepare(tmp_path)
    _generated_restart_home(profile)
    executable, digest = _restart_executable(tmp_path)
    inventory = _restart_inventory(tmp_path, profile, executable, digest)
    (profile.home / 'future-exec-surface').mkdir()
    with pytest.raises(module().CodexProfileError, match='PROFILE_UNREVIEWED_SETTINGS'):
        with module().lease_codex_profile(profile, executable=executable,
                executable_sha256=digest, inventory=inventory):
            pytest.fail('new generated root accepted')
    (profile.home / 'future-exec-surface').rmdir()
    (profile.home / 'skills' / '.system' / 'openai-docs' / 'SKILL.md').write_text(
        'changed builtin', encoding='utf-8')
    with pytest.raises(module().CodexProfileError, match='PROFILE_BINDING_DRIFT'):
        with module().lease_codex_profile(profile, executable=executable,
                executable_sha256=digest, inventory=inventory):
            pytest.fail('changed builtin accepted')


@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_restart_inventory_rejects_new_sqlite_name_and_tmp_content(tmp_path):
    profile = prepare(tmp_path)
    _generated_restart_home(profile)
    executable, digest = _restart_executable(tmp_path)
    inventory = _restart_inventory(tmp_path, profile, executable, digest)
    (profile.home / 'goals_2.sqlite-wal').write_bytes(b'unreviewed wal')
    with pytest.raises(module().CodexProfileError, match='PROFILE_UNREVIEWED_SETTINGS'):
        with module().lease_codex_profile(profile, executable=executable,
                executable_sha256=digest, inventory=inventory):
            pytest.fail('new sqlite filename accepted')
    (profile.home / 'goals_2.sqlite-wal').unlink()
    (profile.home / 'tmp' / 'arg0').write_text('codex', encoding='utf-8')
    with pytest.raises(module().CodexProfileError, match='PROFILE_BINDING_DRIFT'):
        with module().lease_codex_profile(profile, executable=executable,
                executable_sha256=digest, inventory=inventory):
            pytest.fail('provider tmp content accepted')


@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_restart_inventory_allows_sqlite_drift_without_reading_contents(tmp_path, monkeypatch):
    profile = prepare(tmp_path)
    _generated_restart_home(profile)
    executable, digest = _restart_executable(tmp_path)
    inventory = _restart_inventory(tmp_path, profile, executable, digest)
    (profile.home / 'state_5.sqlite-wal').write_bytes(b'mutable sqlite state')
    original = Path.open

    def guarded_open(path, *args, **kwargs):
        if 'sqlite' in Path(path).name:
            raise AssertionError('sqlite content was read')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    with module().lease_codex_profile(profile, executable=executable,
            executable_sha256=digest, inventory=inventory):
        pass


@pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')
def test_restart_inventory_is_bound_to_home_and_executable(tmp_path):
    profile = prepare(tmp_path)
    _generated_restart_home(profile)
    executable, digest = _restart_executable(tmp_path)
    inventory = _restart_inventory(tmp_path, profile, executable, digest)
    other = module().prepare_codex_profile(tmp_path / 'state', workspace=profile.workspace,
        owner_ref='owner-2')
    _generated_restart_home(other)
    with pytest.raises(module().CodexProfileError, match='PROFILE_BINDING_DRIFT'):
        with module().lease_codex_profile(other, executable=executable,
                executable_sha256=digest, inventory=inventory):
            pytest.fail('inventory replayed into another profile')
    changed = tmp_path / 'changed-codex.exe'
    changed.write_bytes(b'changed')
    with pytest.raises(module().CodexProfileError, match='PROFILE_BINDING_DRIFT'):
        with module().lease_codex_profile(profile, executable=changed,
                executable_sha256=digest, inventory=inventory):
            pytest.fail('inventory admitted different executable')
