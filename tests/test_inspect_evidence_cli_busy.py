"""A held file is BUSY, never a digest verdict, and a short hold is ridden out.

The METR packet's changed-byte control expects SOURCE_DIGEST_MISMATCH. On a
Windows workstation it once got INSPECT_INPUT_REJECTED: the artifact reader
opens the file and each directory above it with read-only sharing, so another
process holding any of them open for writing (a scanner or indexer touching a
just-written file) made the read fail before the digest was compared. These
tests pin the fix: a transient holder is retried, a lasting one reports
INSPECT_INPUT_BUSY with the reason, and the tamper is still refused.
"""
import hashlib
import json
import sys
import threading

import pytest

from harness import inspect_evidence_cli as cli
from harness.private_artifact_fs import CONFLICT, UNSAFE_PATH, PrivateArtifactError


def _log_bytes():
    return json.dumps({'version': 2, 'status': 'success',
                       'eval': {'task': 'review', 'model': 'mockllm/model'},
                       'results': {'total_samples': 1, 'completed_samples': 1},
                       'samples': [{'id': 'one', 'epoch': 1,
                                    'scores': {'match': {'value': 'C'}}}]}).encode()


def _flaky_root(real, failures, code=CONFLICT):
    calls = {'n': 0}

    def opener(*args, **kwargs):
        calls['n'] += 1
        if calls['n'] <= failures:
            raise PrivateArtifactError(code)
        return real(*args, **kwargs)
    return opener, calls


def test_transient_sharing_refusal_is_retried_then_digest_compared(tmp_path, capsys, monkeypatch):
    source = tmp_path / 'run.json'
    source.write_bytes(_log_bytes())
    opener, calls = _flaky_root(cli.open_artifact_root, failures=2)
    monkeypatch.setattr(cli, 'open_artifact_root', opener)
    monkeypatch.setattr(cli.time, 'sleep', lambda s: None)
    assert cli.main([str(source), '--expected-sha256', '0' * 64]) == 2
    assert json.loads(capsys.readouterr().out)['error'] == 'SOURCE_DIGEST_MISMATCH'
    assert calls['n'] == 3


def test_lasting_holder_reports_busy_not_a_digest_verdict(tmp_path, capsys, monkeypatch):
    source = tmp_path / 'run.json'
    source.write_bytes(_log_bytes())
    opener, calls = _flaky_root(cli.open_artifact_root, failures=99)
    monkeypatch.setattr(cli, 'open_artifact_root', opener)
    monkeypatch.setattr(cli.time, 'sleep', lambda s: None)
    digest = hashlib.sha256(_log_bytes()).hexdigest()
    assert cli.main([str(source), '--expected-sha256', digest]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out == {'schema': 'flywheel.inspect-import-error/v1',
                   'error': 'INSPECT_INPUT_BUSY', 'detail': CONFLICT}
    assert calls['n'] == len(cli._RETRY_DELAYS) + 1


def test_unsafe_path_is_not_retried_and_names_its_reason(tmp_path, capsys, monkeypatch):
    source = tmp_path / 'run.json'
    source.write_bytes(_log_bytes())
    opener, calls = _flaky_root(cli.open_artifact_root, failures=99, code=UNSAFE_PATH)
    monkeypatch.setattr(cli, 'open_artifact_root', opener)
    assert cli.main([str(source)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert (out['error'], out['detail'], calls['n']) == ('INSPECT_INPUT_REJECTED', UNSAFE_PATH, 1)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows share modes')
def test_real_writer_handle_released_mid_retry_still_refuses_tamper(tmp_path, capsys):
    """The failure as it happened: another handle has the file open for writing."""
    source = tmp_path / 'run.json'
    source.write_bytes(_log_bytes())
    holder = open(source, 'r+b')
    timer = threading.Timer(0.12, holder.close)
    timer.start()
    try:
        assert cli.main([str(source), '--expected-sha256', '0' * 64]) == 2
    finally:
        timer.join()
        holder.close()
    assert json.loads(capsys.readouterr().out)['error'] == 'SOURCE_DIGEST_MISMATCH'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows share modes')
def test_real_writer_handle_that_stays_reports_busy(tmp_path, capsys, monkeypatch):
    source = tmp_path / 'run.json'
    source.write_bytes(_log_bytes())
    monkeypatch.setattr(cli.time, 'sleep', lambda s: None)
    with open(source, 'r+b'):
        assert cli.main([str(source), '--expected-sha256', '0' * 64]) == 2
    assert json.loads(capsys.readouterr().out)['error'] == 'INSPECT_INPUT_BUSY'
