"""Run the native verification gate against extracted source and reject false success."""
import json
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


@pytest.mark.skipif((ROOT / 'PKG-INFO').is_file() and not (ROOT / '.git').exists(),
                   reason='an extracted sdist has no Git identity for client release construction')
def test_packaged_source_passes_restart_and_refusal_workflow(tmp_path):
    from build_client_package import build, qualify
    from check_native_client import check
    archive = build(tmp_path / 'built')[0]
    with zipfile.ZipFile(archive) as source:
        source.extractall(tmp_path / 'extracted')
    result = check(tmp_path / 'extracted/server/serve.py', qualify('dev')[0])
    assert result['status'] == result['workflow']['status'] == result['mcpb_setup']['status'] == 'PASS'


def test_workflow_rejects_protocol_success_without_persistence(tmp_path, monkeypatch):
    import check_native_workflow as workflow
    claimed = {'status': 'stored', 'source_hash': 'synthetic', 'event_record_id': 'claimed'}
    monkeypatch.setattr(workflow, 'call', lambda *a, **k:
        {'content': [{'type': 'text', 'text': json.dumps(claimed)}], 'isError': False})
    with pytest.raises(ValueError, match='did not persist'):
        workflow.check_workflow(tmp_path / 'fake.exe', tmp_path)
