"""Managed Codex profile lease must allow runtime writes without loosening pins."""
import hashlib
import importlib
import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows file leases')


def module():
    return importlib.import_module('harness.codex_managed_profile')


def prepare(tmp_path):
    state, workspace = tmp_path / 'state', tmp_path / 'workspace'
    state.mkdir()
    workspace.mkdir()
    return module().prepare_codex_profile(state, workspace=workspace,
                                          owner_ref='owner-lease-runtime')


def executable(tmp_path):
    path = tmp_path / 'bin' / 'codex.exe'
    path.parent.mkdir()
    path.write_bytes(b'synthetic executable, never run')
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_replace(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(data)
    tmp.replace(path)


def test_profile_lease_allows_runtime_atomic_state_creation_and_replacement(tmp_path):
    profile = prepare(tmp_path)
    exe, digest = executable(tmp_path)
    runtime_state = profile.home / 'auth.json'

    with module().lease_codex_profile(profile, executable=exe,
                                      executable_sha256=digest):
        atomic_replace(runtime_state, b'{"state":"created"}\n')
        atomic_replace(runtime_state, b'{"state":"replaced"}\n')

    assert runtime_state.read_bytes() == b'{"state":"replaced"}\n'


def test_profile_lease_still_blocks_config_and_executable_mutation(tmp_path):
    profile = prepare(tmp_path)
    exe, digest = executable(tmp_path)

    with module().lease_codex_profile(profile, executable=exe,
                                      executable_sha256=digest):
        for path in (profile.home / 'config.toml', exe):
            with pytest.raises(OSError):
                path.write_bytes(b'changed')
            with pytest.raises(OSError):
                atomic_replace(path, b'changed')


@pytest.mark.parametrize('target_name', ['home', 'workspace', 'executable_parent'])
def test_profile_lease_still_blocks_root_and_ancestor_swaps(tmp_path, target_name):
    profile = prepare(tmp_path)
    exe, digest = executable(tmp_path)
    targets = {
        'home': profile.home,
        'workspace': profile.workspace,
        'executable_parent': exe.parent,
    }
    target = targets[target_name]

    with module().lease_codex_profile(profile, executable=exe,
                                      executable_sha256=digest):
        with pytest.raises(OSError):
            target.rename(tmp_path / f'moved-{target_name}')
