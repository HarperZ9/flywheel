"""Crash diagnostics expose only bounded fields for the owned native process."""
import json
import pytest

from desktop.tool import native_crash_event as event


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(event.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(event.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now


def test_owned_crash_projection_omits_paths_and_bodies(monkeypatch):
    rows = [{'AppName': 'flywheel_desktop.exe', 'ProcessId': '0x29',
             'ModuleName': 'flutter_windows.dll', 'ExceptionCode': 'c0000005',
             'FaultingOffset': '0000000000012345', 'AppPath': 'private/path',
             'Message': 'private body'},
            {'AppName': 'unrelated.exe', 'ProcessId': '0x29', 'ModuleName': 'private.dll'},
            {'AppName': 'flywheel_desktop.exe', 'ProcessId': '0x30', 'ModuleName': 'other.dll'}]
    monkeypatch.setattr(event, '_run_powershell', lambda command, timeout: json.dumps(rows))
    result = event.crash_events(41)
    assert result == [{'module': 'flutter_windows.dll', 'exception_code': 'c0000005',
                       'fault_offset': '0000000000012345'}]
    assert 'private' not in json.dumps(result)


def test_invalid_or_unavailable_events_are_not_success_evidence(monkeypatch):
    monkeypatch.setattr(event, '_run_powershell', lambda command, timeout: 'unavailable')
    assert event.crash_events(41) == []
    monkeypatch.setattr(event, '_run_powershell', lambda command, timeout: json.dumps([{
        'AppName': 'flywheel_desktop.exe', 'ProcessId': 41, 'ModuleName': 'C:/private/module.dll',
        'ExceptionCode': 'private text', 'FaultingOffset': '0'}]))
    assert event.crash_events(41) == []


def test_late_owned_event_is_collected_and_poll_stops(monkeypatch, clock):
    calls = []
    def query(command, timeout):
        calls.append(timeout)
        if len(calls) < 3:
            return '[]'
        return json.dumps([{'AppName': 'flywheel_desktop.exe', 'ProcessId': 41,
            'ModuleName': 'app.dll', 'ExceptionCode': 'c0000005', 'FaultingOffset': '123'}])
    monkeypatch.setattr(event, '_run_powershell', query)
    assert event.crash_events(41)[0]['module'] == 'app.dll'
    assert len(calls) == 3 and clock[0] == 0.5


def test_missing_event_deadline_includes_each_query_time(monkeypatch, clock):
    calls = []
    def query(command, timeout):
        calls.append(timeout)
        clock[0] += timeout
        raise event.subprocess.TimeoutExpired('diagnostic query', timeout)
    monkeypatch.setattr(event, '_run_powershell', query)
    assert event.crash_events(41) == []
    assert clock[0] <= 8 and len(calls) >= 2 and max(calls) <= 2
