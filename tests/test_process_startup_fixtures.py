from types import SimpleNamespace

import pytest

from tests.process_startup_fixtures import ReadyOwnedProcess


def test_ready_process_preserves_wait_budget_and_real_outcome(tmp_path, text_once_written):
    marker, events = tmp_path / 'pid', []
    marker.write_text('123')
    outcome = object()
    owned = SimpleNamespace(resume=lambda: events.append('resume') or True,
        wait=lambda timeout: events.append(('wait', timeout)) or outcome)
    wrapped = ReadyOwnedProcess(owned, marker, text_once_written,
        lambda pid: events.append(('alive', pid)) or True)
    assert wrapped.resume() is True
    assert wrapped.pid == 123 and wrapped.ready_at is not None
    assert events == ['resume', ('alive', 123)]
    assert wrapped.wait(2) is outcome
    assert events[-1] == ('wait', 2)


@pytest.mark.parametrize(('contents', 'alive', 'error'), [
    (None, True, AssertionError), ('', True, AssertionError),
    ('bad-pid', True, ValueError), ('123', False, AssertionError),
])
def test_missing_or_invalid_startup_never_becomes_cleanup_evidence(
        tmp_path, text_once_written, contents, alive, error):
    marker = tmp_path / 'pid'
    if contents is not None:
        marker.write_text(contents)
    wrapped = ReadyOwnedProcess(SimpleNamespace(resume=lambda: True), marker,
        text_once_written, lambda _pid: alive, startup_timeout=.01)
    with pytest.raises(error):
        wrapped.resume()
    assert wrapped.pid is wrapped.ready_at is None


def test_failed_resume_does_not_claim_readiness(tmp_path):
    wrapped = ReadyOwnedProcess(SimpleNamespace(resume=lambda: False), tmp_path / 'pid',
        lambda *a, **k: pytest.fail('read after failed resume'),
        lambda _pid: pytest.fail('query after failed resume'))
    assert wrapped.resume() is False
    assert wrapped.pid is wrapped.ready_at is None
