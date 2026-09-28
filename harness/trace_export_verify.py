"""Verify a Flywheel trace export with the standard library only (7.5, SP-36).

Usage: python verify.py <export directory or .zip>

Prints MATCH and exits 0 when every listed file has its recorded hash and
size, the manifest root re-derives, every gateway trace chain re-derives
record by record, and every lineage reference names an exported item. Prints
DRIFT and exits 1 naming each file that differs. Prints UNVERIFIABLE and
exits 2 with the reason when something cannot be checked: a missing file or
manifest, an unsafe member path, or a zip over a cap.

Before opening anything it refuses manifest and trace paths that are
absolute, hold `..`, a drive letter, a UNC or device prefix, a backslash, a
colon (an alternate data stream), a control character or a reserved device
name. A folder holding a link or junction is refused, not followed. A zip is
read member by member in memory under caps on member count, total size and
compression ratio, and is never extracted. Every printed reason has its
control characters escaped.

What MATCH does not prove: that the export holds everything custody held,
that custody recorded what really happened, or who made the export. Anyone
can rewrite the files and the manifest together, so MATCH shows only that
the files match this manifest; compare root_sha256 with the export entry in
the owner's custody ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import zipfile

SCHEMA = "flywheel.trace-export/v1"
GENESIS = "0" * 64
MAX_MEMBERS = 100_000
MAX_TOTAL = 4 * 1024 ** 3
MAX_RATIO = 200
UNHASHED = ("manifest.json", "verify.py")
_RESERVED = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?\Z", re.IGNORECASE)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def root_digest(manifest: dict) -> str:
    """sha256 over the header fields and the sorted [path, sha256, bytes] list."""
    header = {k: v for k, v in manifest.items() if k not in ("files", "root_sha256")}
    files = sorted([f["path"], f["sha256"], f["bytes"]] for f in manifest.get("files", []))
    return hashlib.sha256(canonical({"header": header, "files": files})).hexdigest()


def unsafe(path) -> bool:
    if type(path) is not str or not path or "\\" in path or ":" in path:
        return True
    if path.startswith("/") or any(ord(c) < 32 or ord(c) == 127 for c in path):
        return True
    parts = path.split("/")
    return any(p in ("", ".", "..") or _RESERVED.match(p) or p != p.rstrip(". ")
               for p in parts)


class Unverifiable(Exception):
    pass


def printable(text: str) -> str:
    """Text with control characters escaped, safe to print to a terminal."""
    return "".join(c if 32 <= ord(c) != 127 and not 0x80 <= ord(c) < 0xA0
                   else "\\x%02x" % ord(c) if ord(c) < 256 else "\\u%04x" % ord(c)
                   for c in str(text))


def _zip_members(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if len(infos) > MAX_MEMBERS:
            raise Unverifiable(f"zip has {len(infos)} members, over {MAX_MEMBERS}")
        if sum(i.file_size for i in infos) > MAX_TOTAL:
            raise Unverifiable("zip uncompressed size is over the cap")
        for info in infos:
            if unsafe(info.filename):
                raise Unverifiable(f"unsafe path in zip: {info.filename!r}")
            if info.file_size > MAX_RATIO * max(info.compress_size, 1):
                raise Unverifiable(f"compression ratio over {MAX_RATIO} for {info.filename}")
        return {i.filename: archive.read(i) for i in infos}


def _is_link(path: str) -> bool:
    info = os.lstat(path)
    return os.path.islink(path) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _dir_members(path: Path) -> dict:
    if _is_link(str(path)):
        raise Unverifiable("the export folder is a link")
    members = {}
    for folder, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            full = os.path.join(folder, name)
            if _is_link(full):
                raise Unverifiable("link in export: " + Path(full).relative_to(path).as_posix())
        for name in files:
            full = Path(folder) / name
            members[full.relative_to(path).as_posix()] = full
    return members


def _read(members: dict, rel: str) -> bytes | None:
    value = members.get(rel)
    return value.read_bytes() if isinstance(value, Path) else value


def _manifest(members: dict) -> dict:
    raw = _read(members, "manifest.json")
    if raw is None:
        raise Unverifiable("manifest.json is missing")
    try:
        manifest = json.loads(raw)
    except ValueError:
        raise Unverifiable("manifest.json is not JSON") from None
    if type(manifest) is not dict or type(manifest.get("files")) is not list:
        raise Unverifiable("manifest.json has no file list")
    for entry in manifest["files"]:
        if type(entry) is not dict or unsafe(entry.get("path")):
            raise Unverifiable(f"unsafe path in manifest: {entry.get('path')!r}"
                               if type(entry) is dict else "malformed file entry")
    return manifest


def _files(members: dict, manifest: dict) -> tuple[list, list]:
    drift, missing = [], []
    listed = set()
    for entry in manifest["files"]:
        listed.add(entry["path"])
        data = _read(members, entry["path"])
        if data is None:
            missing.append(f"missing file: {entry['path']}")
        elif hashlib.sha256(data).hexdigest() != entry["sha256"] or len(data) != entry["bytes"]:
            drift.append(f"hash mismatch: {entry['path']}")
    drift += [f"unlisted file: {rel}" for rel in sorted(members)
              if rel not in listed and rel not in UNHASHED]
    return drift, missing


def _chain(data: bytes, expected: dict) -> bool:
    head, count = GENESIS, 0
    for line in data.splitlines():
        record = json.loads(line)
        digest = record.pop("record_sha256", None)
        if (record.get("sequence") != count or record.get("prior_sha256") != head
                or hashlib.sha256(canonical(record)).hexdigest() != digest):
            return False
        head, count = digest, count + 1
    return count == expected.get("records") and head == expected.get("head")


def _traces(members: dict, manifest: dict) -> list:
    drift = []
    for trace in manifest.get("traces", []):
        if type(trace) is not dict or unsafe(trace.get("path")):
            raise Unverifiable("unsafe trace path in manifest")
        data = _read(members, trace["path"])
        try:
            ok = data is not None and _chain(data, trace)
        except (ValueError, AttributeError):
            ok = False
        if data is not None and not ok:
            drift.append(f"trace chain broken: {trace['path']}")
    return drift


def _lineage(manifest: dict) -> list:
    refs = {f.get("item_ref") for f in manifest["files"]}
    return [f"lineage unresolved: {pair}" for pair in manifest.get("lineage", [])
            if type(pair) is not list or len(pair) != 2 or not set(pair) <= refs]


def verify(target) -> tuple[str, list]:
    path = Path(target)
    try:
        members = _zip_members(path) if path.is_file() else _dir_members(path)
        manifest = _manifest(members)
        traces = _traces(members, manifest)
    except (Unverifiable, zipfile.BadZipFile, OSError) as exc:
        return "UNVERIFIABLE", [str(exc) or type(exc).__name__]
    drift, missing = _files(members, manifest)
    if root_digest(manifest) != manifest.get("root_sha256"):
        drift.append("manifest root does not re-derive: manifest.json")
    drift += traces
    missing += _lineage(manifest)
    if missing:
        return "UNVERIFIABLE", missing + drift
    return ("DRIFT", drift) if drift else ("MATCH", [])


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python verify.py <export directory or .zip>")
        return 2
    code, reasons = verify(argv[0])
    print(code)
    for reason in reasons:
        print("  " + printable(reason))
    return {"MATCH": 0, "DRIFT": 1}.get(code, 2)


if __name__ == "__main__":
    raise SystemExit(main())
