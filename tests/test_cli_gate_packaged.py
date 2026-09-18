"""The installed disproof gate must not depend on a source checkout."""
import json

import pytest

from harness import cli_entry


def no_checkout():
    raise FileNotFoundError('no checkout')


def test_gate_without_checkout_writes_checkable_receipt_in_cwd(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_entry, 'find_repo_root', no_checkout)
    assert cli_entry.main(['gate']) == 0
    report = json.loads((tmp_path/'artifacts/gate/gate_report.json').read_text())
    assert report['rewitness'] == 'MATCH'
    assert 'verdict=PASS rewitness=MATCH' in capsys.readouterr().out


def test_gate_keeps_checkout_default_and_explicit_output(monkeypatch, tmp_path):
    checkout = tmp_path/'checkout'
    monkeypatch.setattr(cli_entry, 'find_repo_root', lambda: checkout)
    assert cli_entry.main(['gate']) == 0
    assert (checkout/'artifacts/gate/gate_report.json').is_file()
    monkeypatch.setattr(cli_entry, 'find_repo_root', no_checkout)
    explicit = tmp_path/'chosen-output'
    assert cli_entry.main(['gate', str(explicit)]) == 0
    assert (explicit/'gate_report.json').is_file()


def test_gate_does_not_mask_unexpected_root_resolution_failure(monkeypatch):
    def denied():
        raise PermissionError('denied')
    monkeypatch.setattr(cli_entry, 'find_repo_root', denied)
    with pytest.raises(PermissionError):
        cli_entry.main(['gate'])
