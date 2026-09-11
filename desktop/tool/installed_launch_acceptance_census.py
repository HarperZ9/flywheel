"""Bounded process census: None means unavailable; an empty list is observed empty."""
import json
import os
import subprocess

try:
    from .installed_launch_acceptance_model import WINDOW_FLAGS
except ImportError:
    from installed_launch_acceptance_model import WINDOW_FLAGS  # type: ignore


# powershell.exe cold-start on a loaded Windows CI runner (3-8s) plus a full
# Win32_Process CIM enumeration and JSON serialize can brush against a 10s
# budget, raising TimeoutExpired and making the census read as unavailable.
# A warm local run of the same command completes in under 1s, so this is a
# cold-start ceiling, not a per-row cost. 60s clears the worst realistic cold
# census (~12s) with wide margin while still bounding a genuinely hung shell.
CENSUS_TIMEOUT_SECONDS = 60


def process_rows() -> list[dict] | None:
    if os.name != "nt":
        return None
    script = ("$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,ParentProcessId,CreationDate | ConvertTo-Json")
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                creationflags=WINDOW_FLAGS, timeout=CENSUS_TIMEOUT_SECONDS)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        rows = json.loads(result.stdout)
        rows = rows if isinstance(rows, list) else [rows]
        parsed, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                return None
            pid, parent = row.get("ProcessId"), row.get("ParentProcessId")
            created = row.get("CreationDate")
            if (type(pid) is not int or type(parent) is not int or min(pid, parent) < 0
                    or pid in seen or (created is not None and not isinstance(created, str))):
                return None
            seen.add(pid)
            parsed.append({"pid": pid, "parent_pid": parent, "creation_time": created or ""})
        return parsed
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
