"""Write containment for the frozen lane smoke (POLICY-DECISION C-16).

"A T1 tool writes only inside its lane folder" is a claim about 133 tools read
from source. This makes it a measurement: the smoke snapshots the throwaway
home (which is also the smoke's USERPROFILE, TEMP and app-data folders) before
and after each lane runs its fixture, and reports every file that appeared or
changed outside ``<home>/lanes/<lane>/``. The smoke's own fixture folder
(``<home>/fixtures/<lane>``) is the harness writing, not the lane, and is left
out.

Stated limit: this measures writes under the throwaway home only. A write to
an absolute path elsewhere on the machine, and every read, go unmeasured.
"""
from __future__ import annotations

import os
from pathlib import Path

Snapshot = dict[str, tuple[int, int]]


def snapshot(root: Path) -> Snapshot:
    """Every file under ``root`` as relative path -> (size, mtime_ns)."""
    out: Snapshot = {}
    root = Path(root)
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = Path(dirpath) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            out[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return out


def outside_writes(before: Snapshot, after: Snapshot, lane: str) -> list[str]:
    """Files new or changed between the snapshots, outside the lane's folders."""
    allowed = (f"lanes/{lane}/", f"fixtures/{lane}/")
    return sorted(path for path, meta in after.items()
                  if before.get(path) != meta and not path.startswith(allowed))
