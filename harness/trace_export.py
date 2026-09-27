"""Bulk export of private traces, verifiable by anyone (7.5, I8).

`export` writes `flywheel.trace-export/v1` into an `.incomplete` folder
beside the destination, with an owner-only ACL and the not-indexed
attribute: the stores' files, `manifest.json`, `README.txt` and a copy of the
standard-library verifier as `verify.py`. It runs that verifier on the
result and renames the folder into place only on MATCH; anything else leaves
the `.incomplete` folder and says why. Presence bound to the export digest
(the exact destination and the options) is required first. Credentials are
redacted by default. One custody ledger entry and one witness event record
the root digest and a keyed digest of the destination; the ledger is the
only custody file an export changes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import secrets
import shutil

from .evidence_json import canonical_sha256
from .trace_export_dest import ExportError, check, destination_digest, protect

_log = logging.getLogger(__name__)
OPTIONS = {"redact": True, "redact_personal": False, "stable_tags": False, "zip": False,
           "allow_sync_root": False}
EXPORTED = ("S1", "CT", "S8b", "IM", "TD")
__all__ = ["ExportError", "export", "export_digest"]


def _options(options: dict) -> dict:
    unknown = set(options) - set(OPTIONS)
    if unknown or not all(type(v) is bool for v in options.values()):
        raise ExportError("OPTIONS_INVALID")
    return {**OPTIONS, **options}


def export_digest(out, options: dict) -> str:
    """What presence confirms: the exact destination and every option."""
    return canonical_sha256({"schema": "flywheel.trace-export-request/v1",
                             "destination": os.path.normcase(os.path.abspath(str(out))),
                             "options": _options(options)})


class Redactor:
    """Credential (and optionally personal) redaction plus home paths to ~."""

    def __init__(self, home, owner: str, opts: dict) -> None:
        import re
        self.active, self.personal = opts["redact"], opts["redact_personal"]
        self.key = _stable_key(home, owner) if opts["stable_tags"] else secrets.token_bytes(32)
        self.counts: dict[str, int] = {}
        text = str(Path.home())
        variants = sorted({text, text.replace("\\", "/"), text.replace("\\", "\\\\")},
                          key=len, reverse=True)
        flags = re.IGNORECASE if os.name == "nt" else 0
        self.home = re.compile("(?:" + "|".join(re.escape(v) for v in variants)
                               + ")(?![A-Za-z0-9_.-])", flags)
        # Claude Code names project folders after the path with every
        # non-alphanumeric character as "-": C:\Users\x -> C--Users-x.
        encoded = re.sub(r"[^A-Za-z0-9]", "-", text)
        self.encoded = re.compile(re.escape(encoded) + "(?![A-Za-z0-9_.])", flags)

    def line(self, text: str) -> str:
        if not self.active:
            return text
        from .trace_redact import redact_line
        new, counts = redact_line(text, key=self.key, personal=self.personal)
        for rule, n in counts.items():
            self.counts[rule] = self.counts.get(rule, 0) + n
        return self.encoded.sub("~", self.home.sub("~", new))


def _stable_key(home, owner: str) -> bytes:
    import hashlib
    import hmac
    from .trace_keystore import Keystore
    key = Keystore(Path(home) / "state", owner).custody_key(create=False)
    if key is None:
        raise ExportError("CUSTODY_KEY_UNAVAILABLE")
    return hmac.new(key, b"flywheel.redaction-tags/v1", hashlib.sha256).digest()


def _header(collector, opts: dict) -> dict:
    from .cli_version import installed_version
    from .trace_inventory import Gap, stores
    from .trace_redact_rules import CATALOG_VERSION
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    excluded = [{"id": s.id, "reason": s.export.reason if isinstance(s.export, Gap)
                 else "not part of the trace export"} for s in stores() if s.id not in EXPORTED]
    return {"created_at": stamp, "flywheel_version": installed_version(),
            "catalog_version": CATALOG_VERSION,
            "redaction": {"mode": {"credentials": opts["redact"],
                                   "personal": opts["redact"] and opts["redact_personal"]},
                          "tags": "stable" if opts["stable_tags"] else "per-export"},
            "selection": {"stores": list(EXPORTED)}, "traces": collector.traces,
            "lineage": collector.lineage, "redaction_counts": collector.redactor.counts,
            "unredacted_traces": collector.unredacted, "omissions": collector.omissions,
            "excluded": excluded}


def _write(home: Path, owner: str, folder: Path, opts: dict) -> dict:
    from .trace_export_manifest import build, readme
    from .trace_export_stores import Collector, dump
    collector = Collector(folder, Redactor(home, owner, opts))
    collector.gateway(home, owner)
    collector.snapshots(home, owner, collector.turns(home, owner))
    collector.imports(home, owner)
    collector.tombstones(home, owner)
    header = _header(collector, opts)
    collector.write("README.txt", readme(header).encode("utf-8"), None, None)
    manifest = build(header, collector.files)
    (folder / "manifest.json").write_bytes(dump(manifest))
    verifier = Path(__file__).with_name("trace_export_verify.py")
    (folder / "verify.py").write_bytes(verifier.read_bytes())
    return manifest


def _authorize(home: Path, owner: str, out, opts: dict, presence_ref, sync_presence_ref):
    from .trace_presence import require
    digest = export_digest(out, opts)
    path, synced = check(out, home, allow_sync_root=opts["allow_sync_root"])
    method = require(home / "state", owner, "export", digest, presence_ref)
    if synced:
        require(home / "state", owner, "export_allow_sync_root", digest, sync_presence_ref)
    return path, method


def _zip(folder: Path, archive: Path) -> None:
    """Create the zip new, protect it, then fill it without re-creating it,
    so it keeps the owner-only ACL and the not-indexed attribute."""
    import zipfile
    descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(
        os, "O_BINARY", 0), 0o600)
    os.close(descriptor)
    protect(archive, directory=False)
    with open(archive, "r+b") as stream, zipfile.ZipFile(stream, "w",
                                                         zipfile.ZIP_DEFLATED) as bundle:
        for member in sorted(p for p in folder.rglob("*") if p.is_file()):
            bundle.write(member, member.relative_to(folder).as_posix())


def _finish(path: Path, staging: Path, opts: dict) -> tuple[Path, str | None]:
    """Rename into place; with zip, keep the zip only if it verifies too
    (a zip over the verifier's caps would be one nobody could check)."""
    from .trace_export_verify import verify
    staging.replace(path)
    if not opts["zip"]:
        return path, None
    archive = path.with_name(path.name + ".zip")
    _zip(path, archive)
    code, reasons = verify(archive)
    if code != "MATCH":
        _log.warning("zip export did not verify (%s); the folder is kept instead", code)
        archive.unlink()
        return path, "; ".join(reasons) or code
    shutil.rmtree(path)
    return archive, None


def _incomplete(home: Path, owner: str, path: Path, method: str, reason: str, sink, *,
                path_: Path) -> dict:
    """A partial plaintext copy exists outside custody: the ledger says so."""
    from .trace_witness import record_custody_event
    code = reason if reason.replace("_", "").isalnum() else "EXPORT_FAILED"
    event = record_custody_event(home, owner, "export", {
        "items": 0, "reason_code": code[:64],
        "destination_digest": destination_digest(home, owner, path)}, method, sink=sink)
    return {"state": "INCOMPLETE", "reason": reason, "path": str(path_), **event}


def export(home, owner: str, out, presence_ref, *, sink=None, sync_presence_ref=None,
           **options) -> dict:
    from .trace_export_verify import verify
    from .trace_witness import record_custody_event
    home, opts = Path(home), _options(options)
    path, method = _authorize(home, owner, out, opts, presence_ref, sync_presence_ref)
    staging = path.with_name(path.name + ".incomplete")
    if staging.exists():
        raise ExportError("DESTINATION_EXISTS")
    staging.mkdir(parents=True)
    protect(staging)
    try:
        manifest = _write(home, owner, staging, opts)
    except (OSError, ValueError) as exc:
        _log.exception("export stopped; the partial folder stays as .incomplete")
        return _incomplete(home, owner, path, method, type(exc).__name__, sink,
                           path_=staging)
    code, reasons = verify(staging)
    if code != "MATCH":
        return {**_incomplete(home, owner, path, method, code, sink, path_=staging),
                "details": reasons}
    try:
        final, zip_refused = _finish(path, staging, opts)
    except (OSError, ExportError) as exc:
        _log.exception("export verified but was not moved into place")
        where = path if path.exists() else staging
        return _incomplete(home, owner, path, method, getattr(exc, "code", type(exc).__name__),
                           sink, path_=where)
    stores = sorted({f["store"] for f in manifest["files"] if f["store"]})
    items = len({f["item_ref"] for f in manifest["files"] if f["item_ref"]})
    size = sum(f["bytes"] for f in manifest["files"])
    mode = manifest["redaction"]["mode"]
    event = record_custody_event(home, owner, "export", {
        "root_digest": manifest["root_sha256"], "items": items, "bytes": size, "stores": stores,
        "redaction": ("none" if not mode["credentials"] else
                      "credentials_personal" if mode["personal"] else "credentials"),
        "destination_digest": destination_digest(home, owner, path)}, method, sink=sink)
    return {"state": "EXPORTED", "verify": code, "path": str(final), "items": items,
            "bytes": size, "stores": stores, "root_sha256": manifest["root_sha256"],
            "redaction": mode, "omissions": len(manifest["omissions"]),
            **({"zip_refused": zip_refused} if zip_refused else {}), **event}
