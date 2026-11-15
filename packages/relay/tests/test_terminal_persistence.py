"""A published terminal state must not trigger another Windows replace/read race."""
import threading
import pytest
from relay.async_runs import RunRegistry, RUNNING, DONE, ERROR


@pytest.mark.parametrize('fails', [False, True])
def test_terminal_result_is_not_replaced_after_publication(tmp_path, fails):
    finished = threading.Event()
    writes_after_terminal = []

    class TrackedRegistry(RunRegistry):
        def _persist(self, run, **kwargs):
            if run.state != RUNNING:
                writes_after_terminal.append(run.state)
            return super()._persist(run, **kwargs)

        def _execute(self, run, work):
            try:
                super()._execute(run, work)
            finally:
                finished.set()

    binding = {'allow_exec': False, 'allow_write': True, 'root': str(tmp_path)}
    registry = TrackedRegistry(run_root=str(tmp_path), id_source=lambda: 'fixture')

    def work(ledger):
        ledger.append('assistant', 'synthetic fixture')
        if fails:
            raise RuntimeError('synthetic failure')
        return {'final': 'synthetic fixture'}

    run_id = registry.start(work, request_binding=binding)
    assert finished.wait(5)
    assert writes_after_terminal == []
    live = registry.result(run_id)
    reloaded = RunRegistry(run_root=str(tmp_path)).result(run_id)
    assert live['state'] == reloaded['state'] == (ERROR if fails else DONE)
    assert live['request_binding'] == reloaded['request_binding'] == binding


def test_failed_done_write_persists_error_before_publication(tmp_path):
    finished = threading.Event()

    class FailedDoneRegistry(RunRegistry):
        def _persist(self, run, **kwargs):
            if kwargs.get('state') == DONE:
                return False
            return super()._persist(run, **kwargs)

        def _execute(self, run, work):
            try:
                super()._execute(run, work)
            finally:
                finished.set()

    binding = {'allow_write': False, 'allow_exec': False}
    registry = FailedDoneRegistry(run_root=str(tmp_path), id_source=lambda: 'fixture')
    run_id = registry.start(lambda ledger: {'final': 'synthetic'}, request_binding=binding)
    assert finished.wait(5)
    live = registry.result(run_id)
    reloaded = RunRegistry(run_root=str(tmp_path)).result(run_id)
    assert live['state'] == reloaded['state'] == ERROR
    assert live['request_binding'] == reloaded['request_binding'] == binding
    assert reloaded['error'] == 'final result persistence failed'
