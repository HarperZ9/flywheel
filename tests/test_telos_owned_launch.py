"""No subprocesses: inspect the existing owned-launch boundary with fakes."""
from types import SimpleNamespace

import pytest

from harness import cross_harness_process as boundary


@pytest.mark.parametrize("hidden", [False, True])
def test_hidden_flag_preserves_job_assignment_and_default(tmp_path, monkeypatch, hidden):
    seen = {}
    proc = SimpleNamespace(_handle=17)
    def popen(argv, **kwargs): seen.update(kwargs); return proc
    monkeypatch.setattr(boundary.sys, "platform", "win32")
    monkeypatch.setattr(boundary.os, "name", "nt")
    monkeypatch.setattr(boundary.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(boundary.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(boundary.subprocess, "Popen", popen)
    monkeypatch.setattr(boundary, "_windows_job", lambda actual: ("api", "job") if actual is proc else None)
    monkeypatch.setattr(boundary, "OwnedProcess", lambda actual, job, data: (actual, job, data))
    result = boundary.start_owned_process(("node.exe", "fixture.mjs"), cwd=tmp_path,
        stdin_bytes=b"{}", env={}, **({"hide_window": True} if hidden else {}))
    assert result == (proc, ("api", "job"), b"{}")
    assert seen["creationflags"] == 0x204 | (0x08000000 if hidden else 0)
    assert seen["shell"] is False and seen["close_fds"] is True


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_content_free_overflow_reports_either_stream(stream):
    owned = object.__new__(boundary.OwnedProcess)
    owned._captured = {"stdout": (b"private stdout", False), "stderr": (b"private stderr", False)}
    assert owned.capture_overflow() is False
    owned._captured[stream] = (b"secret payload", True)
    assert owned.capture_overflow() is True


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_existing_capture_counts_bytes_and_signals_limit(stream):
    import io
    bucket = {}
    # Multibyte text is limited as bytes, not as Unicode character count.
    raw = ("\u00e9" * (boundary.MAX_CAPTURE_BYTES // 2 + 1)).encode("utf-8")
    boundary._capture(io.BytesIO(raw), bucket, stream)
    assert len(bucket[stream][0]) == boundary.MAX_CAPTURE_BYTES
    assert bucket[stream][1] is True
    owned = object.__new__(boundary.OwnedProcess)
    owned._captured = bucket
    assert owned.capture_overflow() is True
