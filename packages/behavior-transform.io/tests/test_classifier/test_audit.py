import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))

import json
import pytest
from classifier import _audit


def test_audit_path_is_path_object():
    assert isinstance(_audit._AUDIT_PATH, Path)


def test_audit_write_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(_audit, '_AUDIT_PATH', tmp_path / 'audit.jsonl')
    _audit._audit_write('test', {'detail': 'hello'})
    assert (tmp_path / 'audit.jsonl').exists()
    entry = json.loads((tmp_path / 'audit.jsonl').read_text(encoding='utf-8').strip())
    assert entry['event'] == 'test'


def test_audit_write_appends(tmp_path, monkeypatch):
    monkeypatch.setattr(_audit, '_AUDIT_PATH', tmp_path / 'audit.jsonl')
    _audit._audit_write('event1', {'n': 1})
    _audit._audit_write('event2', {'n': 2})
    lines = (tmp_path / 'audit.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])['n'] == 2


def test_audit_log_cmd_returns_list(tmp_path, monkeypatch):
    monkeypatch.setattr(_audit, '_AUDIT_PATH', tmp_path / 'audit.jsonl')
    result = _audit.audit_log_cmd()
    assert isinstance(result, list)


def test_audit_log_cmd_with_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(_audit, '_AUDIT_PATH', tmp_path / 'audit.jsonl')
    for i in range(10):
        _audit._audit_write(f'event{i}', {'n': i})
    result = _audit.audit_log_cmd(limit=5)
    assert len(result) <= 5
