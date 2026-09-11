"""Read shortcut metadata with literal paths carried as JSON, never script text."""
import json
import os
import subprocess
from pathlib import Path

try:
    from .installed_launch_acceptance_model import ShortcutRecord, WINDOW_FLAGS
except ImportError:
    from installed_launch_acceptance_model import ShortcutRecord, WINDOW_FLAGS  # type: ignore


# An unreadable existing link keeps an empty target record, so H05 fails instead of skipping.
_SCRIPT = (
    "$ErrorActionPreference='Stop'; "
    "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
    "$s=New-Object -ComObject WScript.Shell; "
    "$paths=[Console]::In.ReadToEnd() | ConvertFrom-Json; $paths | % { "
    "$l=$s.CreateShortcut($_); "
    "$target=''; if([string]::Equals($l.FullName,[IO.Path]::GetFullPath($_),"
    "[StringComparison]::OrdinalIgnoreCase)){$target=$l.TargetPath}; "
    "[pscustomobject]@{name=[IO.Path]::GetFileNameWithoutExtension($_); target=$target} "
    "} | ConvertTo-Json"
)


def resolve_links(paths: list[Path]) -> list[ShortcutRecord]:
    found = [str(path) for path in paths if path.exists()]
    if not found or os.name != "nt":
        return []
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", _SCRIPT],
        input=json.dumps(found), encoding="utf-8", stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, creationflags=WINDOW_FLAGS,
    )
    if out.returncode != 0 or not out.stdout.strip():
        return []
    data = json.loads(out.stdout)
    rows = data if isinstance(data, list) else [data]
    return [ShortcutRecord(str(row["name"]), Path(str(row["target"]))) for row in rows]
