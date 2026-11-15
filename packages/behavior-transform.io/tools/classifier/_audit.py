from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_AUDIT_PATH = _HERE.parent / ".aup-audit.jsonl"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _audit_write(event: str, data: dict) -> None:
    entry = {"ts": _now(), "event": event, **data}
    try:
        with _AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def audit_log_cmd(limit: int = 50) -> list[dict]:
    if not _AUDIT_PATH.is_file():
        return []
    entries: list[dict] = []
    for line in _AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries[-limit:]