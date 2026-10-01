"""Crash diagnostics expose only bounded fields for the owned native process."""
import json

from desktop.tool import native_crash_event as event


def test_owned_crash_projection_omits_paths_and_bodies(monkeypatch):
    rows = [{'AppName': 'flywheel_desktop.exe', 'ProcessId': '0x29',
             'ModuleName': 'flutter_windows.dll', 'ExceptionCode': 'c0000005',
             'FaultingOffset': '0000000000012345', 'AppPath': 'private/path',
             'Message': 'private body'},
            {'AppName': 'unrelated.exe', 'ProcessId': '0x29', 'ModuleName': 'private.dll'},
            {'AppName': 'flywheel_desktop.exe', 'ProcessId': '0x30', 'ModuleName': 'other.dll'}]
    monkeypatch.setattr(event, '_run_powershell', lambda command: json.dumps(rows))
    result = event.crash_events(41)
    assert result == [{'module': 'flutter_windows.dll', 'exception_code': 'c0000005',
                       'fault_offset': '0000000000012345'}]
    assert 'private' not in json.dumps(result)


def test_invalid_or_unavailable_events_are_not_success_evidence(monkeypatch):
    monkeypatch.setattr(event, '_run_powershell', lambda command: 'unavailable')
    assert event.crash_events(41) == []
    monkeypatch.setattr(event, '_run_powershell', lambda command: json.dumps([{
        'AppName': 'flywheel_desktop.exe', 'ProcessId': 41, 'ModuleName': 'C:/private/module.dll',
        'ExceptionCode': 'private text', 'FaultingOffset': '0'}]))
    assert event.crash_events(41) == []
