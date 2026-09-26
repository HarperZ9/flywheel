"""An append-only witness outside Flywheel's files (7.15, G19, I15).

Deletions, exports, retention runs and settings adoptions append one ledger
entry and also write one event to the Windows Application log, source
`Flywheel`. The event text holds the operation kind, the ledger sequence, a
16-hex prefix of the plan or root digest, the presence method, a count and an
8-hex owner prefix: no content and no path. On this machine a standard user
can write the Application log and cannot clear it without elevation
(experiment X1), and the log overwrites its oldest events at 20 MiB, so
same-user code can evict entries by flooding it (inferred; experiment X13).
A missing event is evidence of tampering or loss, not proof of either.
Other systems have no witness in this round and say so.
"""
from __future__ import annotations

import logging
import re
import subprocess
import sys

from .trace_custody_ledger import CustodyLedger

_log = logging.getLogger(__name__)
SOURCE = "Flywheel"
WITNESSED = ("deletion", "export", "retention_run", "settings_adopted")
_EVENT_IDS = {kind: 1000 + i for i, kind in enumerate(WITNESSED)}
_FIELD = re.compile(r"(kind|seq|plan|presence|items|owner)=([A-Za-z0-9_.:\-]+)")


def event_text(kind: str, seq: int, owner_ref: str, fields: dict, method: str) -> str:
    digest = fields.get("plan_digest") or fields.get("root_digest") or fields.get("digest") or ""
    items = fields.get("items")
    parts = [f"kind={kind}", f"seq={seq}", f"plan={str(digest)[:16] or 'none'}",
             f"presence={method}", f"owner={owner_ref[6:14]}"]
    if type(items) is int:
        parts.append(f"items={items}")
    return "flywheel custody v1 " + " ".join(parts)


def parse_text(text: str) -> dict:
    found = dict(_FIELD.findall(text or ""))
    if "seq" in found and found["seq"].isdigit():
        found["seq"] = int(found["seq"])
    return found


class MemorySink:
    """For tests: keeps texts in memory; `drop_next` loses one event."""

    def __init__(self, drop_next: bool = False) -> None:
        self.texts: list[str] = []
        self.drop_next = drop_next

    def write(self, kind: str, text: str) -> None:
        if self.drop_next:
            self.drop_next = False
            return
        self.texts.append(text)

    def read(self) -> list[dict]:
        return [parse_text(t) for t in self.texts]

    def status(self) -> str:
        return "memory witness (test)"


class NullSink:
    def write(self, kind: str, text: str) -> None:
        return None

    def read(self) -> list[dict]:
        return []

    def status(self) -> str:
        return "no witness on this system"


class WindowsEventLogSink:
    def write(self, kind: str, text: str) -> None:
        import ctypes
        from ctypes import wintypes
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.RegisterEventSourceW.restype = wintypes.HANDLE
        advapi.RegisterEventSourceW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
        advapi.ReportEventW.argtypes = (wintypes.HANDLE, wintypes.WORD, wintypes.WORD,
                                        wintypes.DWORD, ctypes.c_void_p, wintypes.WORD,
                                        wintypes.DWORD, ctypes.POINTER(wintypes.LPCWSTR),
                                        ctypes.c_void_p)
        advapi.ReportEventW.restype = wintypes.BOOL
        advapi.DeregisterEventSource.argtypes = (wintypes.HANDLE,)
        handle = advapi.RegisterEventSourceW(None, SOURCE)
        if not handle:
            raise OSError(ctypes.get_last_error(), "event source unavailable")
        try:
            strings = (wintypes.LPCWSTR * 1)(text)
            if not advapi.ReportEventW(handle, 4, 0, _EVENT_IDS.get(kind, 1099), None, 1, 0,
                                       strings, None):
                raise OSError(ctypes.get_last_error(), "event not written")
        finally:
            advapi.DeregisterEventSource(handle)

    def read(self, limit: int = 5000) -> list[dict]:
        import xml.etree.ElementTree as ET
        query = f"*[System[Provider[@Name='{SOURCE}']]]"
        try:
            done = subprocess.run(["wevtutil", "qe", "Application", f"/q:{query}", "/f:xml",
                                   "/rd:true", f"/c:{limit}"], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OSError("event log unreadable") from exc
        root = ET.fromstring(b"<Events>" + done.stdout + b"</Events>")
        return [parse_text(node.text or "") for node in root.iter()
                if node.tag.endswith("}Data") or node.tag == "Data"]

    def status(self) -> str:
        return "Windows Application log"


def default_sink():
    return WindowsEventLogSink() if sys.platform == "win32" else NullSink()


def record_custody_event(home, owner_ref: str, kind: str, fields: dict, method: str, *,
                         sink=None) -> dict:
    """One ledger entry (with the presence method) and, for witnessed kinds,
    one witness event. Returns what a report shows about presence and witness."""
    from .trace_presence import STATEMENT
    entry = CustodyLedger(home, owner_ref).append(kind, {**fields, "presence": method})
    sink = sink or default_sink()
    witness = sink.status()
    if kind in WITNESSED:
        try:
            sink.write(kind, event_text(kind, entry["seq"], owner_ref, fields, method))
        except OSError as exc:
            _log.warning("custody witness event not written (%s)", type(exc).__name__)
            witness = f"not written ({type(exc).__name__})"
    return {"presence": method, "presence_statement": STATEMENT if method == "none" else "",
            "ledger_seq": entry["seq"], "witness": witness}


def reconcile(entries: list[dict], events: list[dict], owner_ref: str | None = None) -> list:
    """WITNESS_MISMATCH for each witnessed ledger entry with no matching event."""
    seen = {(e.get("kind"), e.get("seq"), e.get("owner")) for e in events}
    missing = []
    for entry in entries:
        if entry.get("kind") not in WITNESSED:
            continue
        owner = (owner_ref or "")[6:14] or None
        keys = {(entry["kind"], entry["seq"], owner)} if owner else {
            k for k in seen if k[:2] == (entry["kind"], entry["seq"])}
        if not keys & seen:
            missing.append({"code": "WITNESS_MISMATCH", "kind": entry["kind"],
                            "seq": entry["seq"]})
    return missing
