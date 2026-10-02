"""Project owned CI app crash events without paths, messages or profile data."""
from __future__ import annotations
import json
import re
import subprocess
import time

from desktop.tool.native_close_acceptance import POWERSHELL


def _run_powershell(command, timeout):
    result = subprocess.run([POWERSHELL, '-NoProfile', '-Command', command],
        capture_output=True, text=True, timeout=timeout,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return result.stdout if result.returncode == 0 else '[]'


def crash_events(pid):
    if type(pid) is not int or pid <= 0:
        return []
    command = """
$ErrorActionPreference = 'Stop'
$rows = @(Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=(Get-Date).AddMinutes(-3)} -MaxEvents 30 -ErrorAction SilentlyContinue)
$out = @()
foreach ($row in $rows) {
  $xml = [xml]$row.ToXml()
  $fields = @{}
  foreach ($field in $xml.Event.EventData.Data) { $fields[$field.Name] = $field.InnerText }
  if ($fields['AppName'] -ine 'flywheel_desktop.exe') { continue }
  try { $eventPid = [uint32]$fields['ProcessId'] } catch { continue }
  if ($eventPid -ne OWNED_PID) { continue }
  $out += [ordered]@{ AppName=$fields['AppName']; ProcessId=$eventPid;
    ModuleName=$fields['ModuleName']; ExceptionCode=$fields['ExceptionCode']; FaultingOffset=$fields['FaultingOffset'] }
  if ($out.Count -ge 4) { break }
}
ConvertTo-Json -InputObject $out -Compress
""".replace('OWNED_PID', str(pid))
    deadline = time.monotonic() + 8.0
    while (remaining := deadline - time.monotonic()) > 0:
        rows = _read_events(command, pid, min(2.0, remaining))
        if rows:
            return rows
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.25, remaining))
    return []  # Unavailable events remain unknown; the app already failed its exit check.


def _read_events(command, pid, timeout):
    try:
        rows = json.loads(_run_powershell(command, timeout) or '[]')
        if not isinstance(rows, list):
            return []
        result = []
        for row in rows[:4]:
            value = row.get('ProcessId')
            observed = int(value, 0) if isinstance(value, str) else value
            if row.get('AppName', '').lower() != 'flywheel_desktop.exe' or observed != pid:
                continue
            module, code, offset = (row.get(key, '') for key in ('ModuleName', 'ExceptionCode', 'FaultingOffset'))
            if (not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', module)
                    or not re.fullmatch(r'[0-9a-fA-F]{8}', code)
                    or not re.fullmatch(r'[0-9a-fA-F]{1,16}', offset)):
                continue
            result.append({'module': module, 'exception_code': code.lower(), 'fault_offset': offset.lower()})
        return result
    except Exception:
        return []  # Missing diagnostics never relax the already-failed exit check.
