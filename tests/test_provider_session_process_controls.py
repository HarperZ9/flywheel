import io
import subprocess
import threading

import pytest

from harness import provider_session_process as proc_owner


class FakeProc:
    def __init__(self, *, stderr=None):
        self._handle = 17
        self.pid = 2345
        self.stdin = CloseRecorder()
        self.stdout = CloseRecorder()
        self.stderr = CloseRecorder() if stderr is None else stderr
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class CloseRecorder(io.BytesIO):
    def __init__(self):
        super().__init__()
        self.closed_observed = False

    def close(self):
        self.closed_observed = True
        super().close()


class BlockingClose(CloseRecorder):
    def __init__(self, release):
        super().__init__()
        self.release = release

    def close(self):
        self.release.wait(2)
        super().close()


class FakeApi:
    def __init__(self, *, close_result=True):
        self.close_result = close_result
        self.calls = []

    def CloseHandle(self, handle):
        self.calls.append(handle)
        return self.close_result


def test_concurrent_close_has_one_cleanup_owner(monkeypatch):
    fake = FakeProc()
    api = FakeApi()
    owned = proc_owner.ProviderSessionProcess(
        fake, (api, "job-handle"), stderr_limit=64)
    entered = threading.Event()
    release = threading.Event()
    wait_calls = []

    def wait_once(_proc, _timeout):
        wait_calls.append(1)
        entered.set()
        release.wait(2)
        fake.returncode = 0
        return True

    monkeypatch.setattr(proc_owner, "_wait_or_kill", wait_once)
    results = []
    threads = [threading.Thread(
        target=lambda: results.append(owned.close(timeout_s=1)))
        for _ in range(2)]

    for thread in threads:
        thread.start()
    assert entered.wait(1)
    release.set()
    for thread in threads:
        thread.join(2)

    assert len(results) == 2
    assert results[0] is results[1]
    assert results[0].job_closed is True
    assert len(wait_calls) == 1
    assert api.calls == ["job-handle"]


def test_close_handle_false_is_reported_without_dropping_custody():
    fake = FakeProc()
    api = FakeApi(close_result=False)
    owned = proc_owner.ProviderSessionProcess(
        fake, (api, "job-handle"), stderr_limit=64)

    cleanup = owned.close(timeout_s=0.01)

    assert cleanup.job_closed is False
    assert owned._job == (api, "job-handle")
    assert api.calls == ["job-handle"]

    api.close_result = True
    retried = owned.close(timeout_s=0.01)

    assert retried.job_closed is True
    assert owned._job is None
    assert api.calls == ["job-handle", "job-handle"]


def test_close_reaches_wait_before_blocking_pipe_close(monkeypatch):
    release = threading.Event()
    fake = FakeProc()
    fake.stdin = BlockingClose(release)
    fake.stdout = BlockingClose(release)
    owned = proc_owner.ProviderSessionProcess(
        fake, (FakeApi(), "job-handle"), stderr_limit=64)
    waited = threading.Event()

    def wait_first(_proc, _timeout):
        waited.set()
        fake.returncode = 0
        return True

    monkeypatch.setattr(proc_owner, "_wait_or_kill", wait_first)
    thread = threading.Thread(target=lambda: owned.close(timeout_s=1))
    thread.start()

    try:
        assert waited.wait(0.5)
    finally:
        release.set()
        thread.join(2)


def test_successful_job_close_fact_survives_retry_after_incomplete_drain():
    fake = FakeProc()
    api = FakeApi()
    owned = proc_owner.ProviderSessionProcess(
        fake, (api, "job-handle"), stderr_limit=64)
    release = threading.Event()
    owned._stderr_thread = threading.Thread(target=lambda: release.wait(2),
                                            daemon=True)
    owned._stderr_thread.start()

    try:
        first = owned.close(timeout_s=0.01)
        second = owned.close(timeout_s=0.01)
    finally:
        release.set()
        owned._stderr_thread.join(1)

    assert first.job_closed is True
    assert second.job_closed is True
    assert api.calls == ["job-handle"]


def test_unexpected_close_failure_notifies_waiters_and_allows_retry(monkeypatch):
    fake = FakeProc()
    api = FakeApi()
    owned = proc_owner.ProviderSessionProcess(
        fake, (api, "job-handle"), stderr_limit=64)
    entered = threading.Event()
    release = threading.Event()

    def fail_wait(_proc, _timeout):
        entered.set()
        release.wait(2)
        raise RuntimeError("raw provider failure should not escape")

    monkeypatch.setattr(proc_owner, "_wait_or_kill", fail_wait)
    results, errors = [], []

    def call_close():
        try:
            results.append(owned.close(timeout_s=1))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=call_close, daemon=True)
               for _ in range(2)]
    threads[0].start()
    assert entered.wait(1)
    threads[1].start()
    release.set()
    for thread in threads:
        thread.join(1)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    assert results[0] is results[1]
    assert results[0].job_closed is True
    assert results[0].exited is False
    assert results[0].stderr_raw is None
    assert api.calls == ["job-handle"]

    monkeypatch.setattr(proc_owner, "_wait_or_kill",
                        lambda _proc, _timeout: True)
    fake.returncode = 0
    retried = owned.close(timeout_s=1)

    assert retried.job_closed is True
    assert retried.exited is True
    assert api.calls == ["job-handle"]


def test_constructor_failure_after_job_assignment_cleans_process_and_pipes(
        tmp_path, monkeypatch):
    fake = FakeProc(stderr=None)
    fake.stderr = None
    api = FakeApi()
    terminated = []
    monkeypatch.setattr(proc_owner.os, "name", "nt", raising=False)
    monkeypatch.setattr(proc_owner.sys, "platform", "win32", raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "CREATE_NO_WINDOW", 0x08000000,
                        raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "CREATE_NEW_PROCESS_GROUP",
                        0x200, raising=False)
    monkeypatch.setattr(proc_owner.subprocess, "Popen",
                        lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(proc_owner.boundary, "_windows_job",
                        lambda _proc: (api, "job-handle"))
    monkeypatch.setattr(proc_owner.boundary, "_terminate_unowned",
                        lambda proc: terminated.append(proc))

    with pytest.raises(proc_owner.ProviderSessionProcessError) as exc:
        proc_owner.start_provider_session_process(
            ["provider.exe"], cwd=tmp_path, env={})

    assert "provider.exe" not in str(exc.value)
    assert api.calls == ["job-handle"]
    assert terminated == [fake]
    assert fake.stdin.closed_observed is True
    assert fake.stdout.closed_observed is True
    assert fake.stderr is None
    assert subprocess.PIPE is not None
