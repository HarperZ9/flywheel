"""`flywheel traces encrypt --legacy`: encrypt traces written before
encryption at rest (7.3, FW-04b).

Each gateway trace is converted from its last file backwards (checkpoint,
then record, newest first), so at every moment the trace is a plaintext
prefix followed by encrypted files and still reads. Each file is encrypted
into a dot-named temporary beside it, read back and checked, then renamed
over the plaintext in one step, so no moment exists in which the file is
missing. The encrypted file keeps the plaintext file's access and
modification times, so retention still reads a trace's age from its first
record. A trace whose writer holds its lock is skipped, and one that cannot
be read (a corrupt record, or a record a crash left without its head) is
skipped as UNREADABLE; every other trace is still converted. The rename
frees the plaintext's clusters without overwriting them; the report names
that residue as `freed_clusters`, which only volume encryption reaches.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .gateway_agent_trace import AgentTrace, TraceError
from .journey_lock import JourneyLockBusy
from .trace_enc import EncError
from .trace_enc import default_provider, is_encrypted


def _state_root() -> Path:
    from .trace_inventory_scan import resolve_roots
    return resolve_roots()["state"]


def _items(state_root: Path):
    base = state_root / "gateway-agent-traces" / "v1" / "owners"
    for owner in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        for item in sorted(p for p in owner.iterdir() if p.is_dir()):
            yield owner.name, item


def _journey(item: Path) -> str | None:
    first = item / "00000000.json"
    try:
        raw = first.read_bytes()
        return None if is_encrypted(raw) else json.loads(raw).get("journey_ref")
    except (OSError, ValueError, AttributeError):
        return None


def _convert(trace: AgentTrace, item: Path, name: str) -> bool:
    path = item / name
    raw = path.read_bytes()
    if is_encrypted(raw):
        return False
    times = os.stat(path)
    blob = trace.cipher.seal(name, raw)
    temporary = item / f".{name}.enc-tmp"
    temporary.write_bytes(blob)
    trace.cipher.prefix.reset()
    if trace.cipher.open(name, temporary.read_bytes()) != raw:
        temporary.unlink()
        raise OSError("ENC_VERIFY_FAILED")
    os.utime(temporary, ns=(times.st_atime_ns, times.st_mtime_ns))
    os.replace(temporary, path)
    return True


def _migrate_item(trace: AgentTrace, item: Path, on_file) -> int:
    count = len(trace.read())
    converted = 0
    for seq in reversed(range(count)):
        for name in (f"head-{seq:08d}.json", f"{seq:08d}.json"):
            if _convert(trace, item, name):
                converted += 1
                if on_file:
                    on_file(name)
    trace.read()
    return converted


def migrate_legacy(state_root=None, *, on_file=None) -> dict:
    state_root = Path(state_root) if state_root is not None else _state_root()
    report = {"state": "DONE", "items": 0, "converted_files": 0, "skipped": {},
              "residue": {}}
    if default_provider().name == "none":
        return {**report, "state": "UNAVAILABLE"}
    for owner, item in _items(state_root):
        journey = _journey(item)
        if journey is None:
            continue  # already encrypted from its first record, or not a trace
        trace = AgentTrace(state_root, owner, journey, item.name)
        try:
            with trace.hold(timeout_s=0):
                converted = _migrate_item(trace, item, on_file)
        except JourneyLockBusy:
            report["skipped"]["LOCKED"] = report["skipped"].get("LOCKED", 0) + 1
            continue
        except (TraceError, EncError, ValueError):
            report["skipped"]["UNREADABLE"] = report["skipped"].get("UNREADABLE", 0) + 1
            continue
        if converted:
            report["items"] += 1
            report["converted_files"] += converted
    if report["converted_files"]:
        report["residue"] = {"freed_clusters": report["converted_files"]}
    return report


def render(report: dict) -> list[str]:
    if report["state"] == "UNAVAILABLE":
        return ["No OS key store is available, so nothing was encrypted."]
    noun = "trace" if report["items"] == 1 else "traces"
    lines = [f"{report['converted_files']} files encrypted in {report['items']} {noun}."]
    for reason, count in sorted(report["skipped"].items()):
        why = ("a run is writing them; try again later" if reason == "LOCKED" else
               "they cannot be read and stay as they are; flywheel traces doctor names them")
        lines.append(f"{count} skipped ({reason}): {why}.")
    if report["residue"]:
        lines.append(f"Residue: the plaintext of {report['residue']['freed_clusters']} files "
                     "stays in freed clusters on disk until overwritten; only volume "
                     "encryption (BitLocker or Device Encryption) protects those.")
    return lines
