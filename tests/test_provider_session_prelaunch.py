"""A refused last-moment policy check must never resume the owned child."""
import os
import sys

import pytest

from harness import provider_session_process as process
from test_provider_session_process import FakeProc
from test_provider_session_process_controls import FakeApi

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows process custody')


def arrange(monkeypatch, *, closes=True):
    events = []
    child, api = FakeProc(), FakeApi(close_result=closes)
    monkeypatch.setattr(process.subprocess, 'Popen',
        lambda *a, **kw: events.append('spawn-suspended') or child)
    monkeypatch.setattr(process.boundary, '_windows_job',
        lambda p: events.append('job') or (api, 'job-handle'))
    monkeypatch.setattr(process.boundary, '_resume_windows',
        lambda p: events.append('resume') or True)
    return child, api, events


def test_policy_recheck_runs_after_containment_before_resume(tmp_path, monkeypatch):
    child, _, events = arrange(monkeypatch)
    owned = process.start_provider_session_process(['provider.exe'], cwd=tmp_path,
        env={}, before_resume=lambda: events.append('policy'))
    try:
        assert events == ['spawn-suspended', 'job', 'policy', 'resume']
    finally:
        assert owned.close().exited


@pytest.mark.parametrize('failure', ['raise', 'false'])
def test_refused_check_closes_without_resume_or_raw_error(tmp_path, monkeypatch, failure):
    child, api, events = arrange(monkeypatch)

    def refuse():
        if failure == 'raise':
            raise ValueError('secret-untrusted-path')
        return False

    with pytest.raises(process.ProviderSessionProcessError) as caught:
        process.start_provider_session_process(['provider.exe'], cwd=tmp_path,
            env={}, before_resume=refuse)
    assert 'resume' not in events
    assert api.calls == ['job-handle']
    assert child.poll() is not None
    assert child.stdin.closed and child.stdout.closed
    assert 'secret' not in str(caught.value)


def test_refused_check_retains_uncertain_cleanup_for_caller(tmp_path, monkeypatch):
    _, api, events = arrange(monkeypatch, closes=False)
    with pytest.raises(process.ProviderSessionProcessError) as caught:
        process.start_provider_session_process(['provider.exe'], cwd=tmp_path,
            env={}, before_resume=lambda: False)
    assert 'resume' not in events
    held = caught.value.owned_process
    assert held is not None and held._job is not None
    api.close_result = True
    assert held.close().job_closed


def test_invalid_callback_never_spawns(tmp_path, monkeypatch):
    _, _, events = arrange(monkeypatch)
    with pytest.raises(process.ProviderSessionProcessError):
        process.start_provider_session_process(['provider.exe'], cwd=tmp_path,
            env={}, before_resume='not-a-callable')
    assert not events


def test_real_suspended_child_cannot_write_after_refused_check(tmp_path):
    from test_provider_session_process import _child_env
    marker = tmp_path / 'must-not-exist.txt'
    script = 'from pathlib import Path; Path("must-not-exist.txt").write_text("ran")'
    with pytest.raises(process.ProviderSessionProcessError) as caught:
        process.start_provider_session_process([sys.executable, '-c', script],
            cwd=tmp_path, env=_child_env(), before_resume=lambda: False)
    assert not marker.exists()
    cleanup = caught.value.owned_process.close()
    assert cleanup.exited and cleanup.job_closed and cleanup.stderr_drain_complete
