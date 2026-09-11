"""Wrapper selftests use an available runtime without hiding failed checks."""
import shutil
from types import SimpleNamespace

import pytest

from tests import installed_launch_acceptance_fixtures as fixtures
from tests import test_installed_launch_acceptance as original
from tests import test_installed_launch_acceptance_v3 as v3


@pytest.mark.parametrize(('available', 'expected'), [
    ({'powershell': 'windows-ps', 'pwsh': 'core-ps'}, 'windows-ps'),
    ({'pwsh': 'core-ps'}, 'core-ps'),
])
def test_selftest_runtime_discovery(monkeypatch, available, expected):
    monkeypatch.setattr(fixtures.shutil, 'which', available.get)
    assert fixtures.powershell_for_selftest() == expected


def test_missing_runtime_is_an_explicit_skip(monkeypatch):
    monkeypatch.setattr(fixtures.shutil, 'which', lambda _name: None)
    with pytest.raises(pytest.skip.Exception, match='PowerShell runtime unavailable'):
        fixtures.powershell_for_selftest()


@pytest.mark.parametrize(('module', 'name'), [
    (original, 'test_powershell_wrapper_selftest_rejects_bad_receipts'),
    (v3, 'test_wrapper_selftest_covers_json_valid_bad_rows_and_list_ids'),
])
def test_wrapper_failure_is_not_skipped_or_retried(monkeypatch, module, name):
    commands = []
    monkeypatch.setattr(module, 'powershell_for_selftest', lambda: 'selected-runtime')

    def fail(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=9, stdout='', stderr='synthetic bad receipt')

    monkeypatch.setattr(module.subprocess, 'run', fail)
    with pytest.raises(AssertionError, match='synthetic bad receipt'):
        getattr(module, name)()
    assert len(commands) == 1 and commands[0][0] == 'selected-runtime'


def test_both_selftests_execute_with_powershell_core(monkeypatch):
    core = shutil.which('pwsh')
    if core is None:
        pytest.skip('PowerShell Core unavailable for cross-platform selftest control')
    monkeypatch.setattr(fixtures.shutil, 'which', lambda name: core if name == 'pwsh' else None)
    original.test_powershell_wrapper_selftest_rejects_bad_receipts()
    v3.test_wrapper_selftest_covers_json_valid_bad_rows_and_list_ids()
