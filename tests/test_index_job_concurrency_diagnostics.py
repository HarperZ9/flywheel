"""Subprocess test failures retain sanitized evidence without hiding failures."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tests.test_projects_index_job_concurrency import _finish, _repo_path


def _child(tmp_path, stdout, stderr, returncode=0):
    return SimpleNamespace(args=[sys.executable, '-c', 'synthetic',
        str(tmp_path / 'a'), str(tmp_path / 'run')], returncode=returncode,
        communicate=lambda timeout: (stdout, stderr))


def test_busy_result_keeps_complete_sanitized_streams(tmp_path):
    output = {'error_type': 'INDEX_REGISTRY_BUSY', 'root': str(tmp_path / 'a')}
    stdout = 'synthetic preamble\n' + json.dumps(output) + '\n'
    stderr = f'root={tmp_path}\nrepo={_repo_path()}\npython={Path(sys.executable).parent}\n'
    result = _finish(_child(tmp_path, stdout, stderr))
    assert result['error_type'] == 'INDEX_REGISTRY_BUSY'
    evidence = result['_process']
    assert evidence['returncode'] == 0
    assert evidence['stdout'].startswith('synthetic preamble\n')
    assert 'INDEX_REGISTRY_BUSY' in evidence['stdout']
    assert evidence['stderr'] == 'root=<synthetic>\nrepo=<repo>\npython=<python>\n'
    assert str(tmp_path) not in json.dumps(evidence)
    assert json.dumps(str(tmp_path))[1:-1] not in evidence['stdout']


@pytest.mark.parametrize(('stdout', 'returncode'), [('not-json', 0), ('{}', 9), ('[]', 0)])
def test_invalid_or_failed_subprocess_still_fails_with_both_streams(
        tmp_path, stdout, returncode):
    with pytest.raises(AssertionError) as raised:
        _finish(_child(tmp_path, stdout, 'synthetic stderr', returncode))
    assert stdout in str(raised.value)
    assert 'synthetic stderr' in str(raised.value)
    assert str(Path(sys.executable).parent) not in str(raised.value)
