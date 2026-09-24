"""Launcher startup and cleanup controls; fake protocol, no provider access."""
from contextlib import contextmanager
import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def module():
    name = 'harness.codex_managed_session'
    assert importlib.util.find_spec(name), 'Managed launcher missing'
    return importlib.import_module(name)


def setup(monkeypatch, *, initialize_error=False, policy_error=False, cleanup_ok=True):
    mod = module()
    events = []
    profile = SimpleNamespace(home=Path('/owned/home'), workspace=Path('/workspace'))

    @contextmanager
    def lease(*args, **kwargs):
        events.append('lease')
        try:
            yield lambda: events.append('policy-rechecked')
        finally:
            events.append('release')

    class Process:
        stdin, stdout = object(), object()
        pid = 101
        def close(self):
            events.append('process-close')
            return SimpleNamespace(exited=cleanup_ok, job_closed=cleanup_ok,
                                   stderr_drain_complete=cleanup_ok)

    class Transport:
        def __init__(self, *args, **kwargs): pass
        def close(self, **kwargs):
            events.append('transport-close')
            return True

    class Client:
        def __init__(self, transport): self.transport = transport
        def initialize(self, **kwargs):
            events.append('initialize')
            if initialize_error: raise ValueError('secret should not escape')

    class Guard:
        config_digest = 'a' * 64
        def __init__(self, client, **kwargs):
            if policy_error: raise ValueError('secret config')

    def spawn(argv, **kwargs):
        events.append(('spawn', argv, kwargs))
        callback = kwargs.get('before_resume')
        if callback is not None:
            callback()
        return Process()

    monkeypatch.setattr(mod, 'lease_codex_profile', lease)
    monkeypatch.setattr(mod, 'codex_profile_environment', lambda p: {'CODEX_HOME': str(p.home)})
    monkeypatch.setattr(mod, 'start_provider_session_process', spawn)
    monkeypatch.setattr(mod, 'CodexSessionTransport', Transport)
    monkeypatch.setattr(mod, 'CodexSessionClient', Client)
    monkeypatch.setattr(mod, 'ManagedCodexClient', Guard)
    monkeypatch.setattr(mod, '_cleanup_holds', [])
    return mod, profile, events


def launch(mod, profile, model='explicit-model'):
    return mod.start_managed_codex_session(profile, executable=Path('/bin/codex.exe'),
                                          executable_sha256='a' * 64, model=model)


def test_startup_has_owned_policy_then_protocol_then_guard(monkeypatch):
    mod, profile, events = setup(monkeypatch)
    session = launch(mod, profile)
    spawn = events[1]
    assert events[0] == 'lease' and spawn[0] == 'spawn'
    assert spawn[1][1:3] == ['app-server', '--stdio']
    assert 'model="explicit-model"' in spawn[1]
    assert spawn[2]['cwd'] == profile.workspace
    assert session.config_digest == 'a' * 64
    assert session.admitted is False
    assert session.close() is True
    assert events[-3:] == ['process-close', 'transport-close', 'release']
    count = len(events)
    assert session.close() is True and len(events) == count


@pytest.mark.parametrize('which', ['initialize_error', 'policy_error'])
def test_failed_startup_cleans_before_releasing_lease(monkeypatch, which):
    mod, profile, events = setup(monkeypatch, **{which: True})
    with pytest.raises(Exception, match='AGENT_NATIVE_RUNTIME_DISABLED') as caught:
        launch(mod, profile)
    assert 'secret' not in str(caught.value)
    assert events[-3:] == ['process-close', 'transport-close', 'release']


def test_missing_model_does_not_start_process(monkeypatch):
    mod, profile, events = setup(monkeypatch)
    with pytest.raises(Exception, match='MODEL_SELECTION_REQUIRED'):
        launch(mod, profile, '')
    assert not events


def test_cleanup_failure_keeps_policy_lease_and_blocks_new_launch(monkeypatch):
    mod, profile, events = setup(monkeypatch, cleanup_ok=False)
    session = launch(mod, profile)
    assert session.close() is False
    assert 'release' not in events
    with pytest.raises(Exception, match='AGENT_NATIVE_CLEANUP_REQUIRED'):
        launch(mod, profile)


def test_restart_inventory_reaches_lease_before_process(monkeypatch):
    mod, profile, events = setup(monkeypatch)
    inventory = object()
    observed = []

    @contextmanager
    def lease(*args, **kwargs):
        observed.append(kwargs.get('inventory'))
        assert not events
        yield lambda: None

    monkeypatch.setattr(mod, 'lease_codex_profile', lease)
    session = mod.start_managed_codex_session(profile,
        executable=Path('/bin/codex.exe'), executable_sha256='a' * 64,
        model='explicit-model', inventory=inventory)
    assert observed == [inventory]
    assert session.close()


def test_rejected_restart_inventory_never_spawns(monkeypatch):
    mod, profile, events = setup(monkeypatch)

    @contextmanager
    def rejected(*args, **kwargs):
        raise ValueError('private manifest location must not escape')
        yield

    monkeypatch.setattr(mod, 'lease_codex_profile', rejected)
    with pytest.raises(Exception, match='AGENT_NATIVE_RUNTIME_DISABLED') as caught:
        mod.start_managed_codex_session(profile,
            executable=Path('/bin/codex.exe'), executable_sha256='a' * 64,
            model='explicit-model', inventory=object())
    assert not events
    assert 'private manifest' not in str(caught.value)


def test_launcher_passes_lease_recheck_before_initialize(monkeypatch):
    mod, profile, events = setup(monkeypatch)
    session = launch(mod, profile)
    try:
        assert events.index('policy-rechecked') < events.index('initialize')
        assert callable(events[1][2]['before_resume'])
    finally:
        assert session.close()


def test_prelaunch_cleanup_uncertainty_retains_policy_lease(monkeypatch):
    mod, profile, events = setup(monkeypatch)
    from harness.provider_session_process import ProviderSessionProcessError

    class HeldProcess:
        def close(self):
            events.append('held-close')
            return SimpleNamespace(exited=True, job_closed=False,
                                   stderr_drain_complete=True)

    def refuse(*args, **kwargs):
        error = ProviderSessionProcessError('provider launch refused')
        error.owned_process = HeldProcess()
        raise error

    monkeypatch.setattr(mod, 'start_provider_session_process', refuse)
    with pytest.raises(Exception, match='AGENT_NATIVE_CLEANUP_REQUIRED'):
        launch(mod, profile)
    assert 'held-close' in events and 'release' not in events
    assert len(mod._cleanup_holds) == 1
