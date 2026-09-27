"""Where an export may be written (7.5, SP-36, I12).

A destination comes from the local CLI or from a grant the CLI wrote naming
the exact path; no HTTP request supplies one. It is refused inside
FLYWHEEL_HOME, refused when any existing folder on its path is a link or
junction (so the path checked is the path written), refused when it exists
at all (an empty folder too: the export renames into place), and refused under a
sync root (the OneDrive variables and folder names, which also cover Desktop
and Documents folders that Known Folder Move redirected into OneDrive, and
the Dropbox, Google Drive and iCloudDrive folder names) unless the owner
allows it with presence. The export folder gets an owner-only ACL and the
not-content-indexed attribute before anything is written into it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat

_DEVICE = re.compile(r"^(\\\\[?.]\\|//[?.]/)")
_GRANT = re.compile(r"xgr_[0-9a-f]{32}\Z")
_REPARSE = 0x400


class ExportError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _inside(path: Path, root: Path) -> bool:
    a = os.path.normcase(os.path.abspath(str(path)))
    b = os.path.normcase(os.path.abspath(str(root)))
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def _is_link(path: str) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE)


def _links_on(path: Path) -> bool:
    """Whether the path or any existing folder above it is a link or junction."""
    current = str(path)
    while True:
        if _is_link(current):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def check(out, home, *, allow_sync_root: bool = False) -> tuple[Path, str | None]:
    """(absolute destination, sync client or None); raises ExportError."""
    from .trace_fs_attrs import sync_root
    text = str(out)
    if _DEVICE.match(text):
        raise ExportError("DESTINATION_DEVICE")
    path = Path(os.path.abspath(text))
    for zipped in (path, path.with_name(path.name + ".zip")):
        if _links_on(zipped):
            raise ExportError("DESTINATION_LINK")
    real, home_real = Path(os.path.realpath(path)), Path(os.path.realpath(home))
    for a, b in ((path, Path(home)), (real, home_real)):
        if _inside(a, b) or _inside(b, a):
            raise ExportError("DESTINATION_IN_CUSTODY")
    synced = sync_root(path) or sync_root(real)
    if synced and not allow_sync_root:
        raise ExportError("DESTINATION_SYNC_ROOT")
    if os.path.lexists(path) or os.path.lexists(path.with_name(path.name + ".zip")):
        raise ExportError("DESTINATION_EXISTS")
    return path, synced


def protect(target: Path, *, directory: bool = True) -> None:
    """Owner-only ACL and not-indexed, on the folder before files go in (or
    on the zip file before it is written)."""
    from .operation_grants import _secure_owner_only
    from .trace_fs_attrs import set_not_indexed
    try:
        _secure_owner_only(target, directory=directory)
        set_not_indexed(target)
    except (OSError, PermissionError) as exc:
        raise ExportError("DESTINATION_PROTECTION_FAILED") from exc


def destination_digest(home, owner: str, path: Path) -> str | None:
    """A keyed digest of the destination, so the ledger names no path."""
    from .trace_keystore import Keystore
    key = Keystore(Path(home) / "state", owner).custody_key(create=False)
    if key is None:
        return None
    message = os.path.normcase(os.path.abspath(str(path))).encode("utf-8", "surrogatepass")
    return hmac.new(key, b"export-destination\x00" + message, hashlib.sha256).hexdigest()


def grant_folder(home, owner: str) -> Path:
    return Path(home) / "state" / "trace-export" / "v1" / "owners" / owner / "grants"


_grants = grant_folder


def create_grant(home, owner: str, out, options: dict) -> dict:
    """A one-use grant naming the exact destination, for the export route."""
    path, _ = check(out, home, allow_sync_root=bool(options.get("allow_sync_root")))
    ref = "xgr_" + secrets.token_hex(16)
    folder = _grants(home, owner)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    (folder / f"{ref}.json").write_text(json.dumps(
        {"schema": "flywheel.trace-export-grant/v1", "destination": str(path),
         "options": options, "created_at": stamp}, sort_keys=True), encoding="utf-8")
    from .trace_export import export_digest
    return {"grant_ref": ref, "destination": str(path),
            "export_digest": export_digest(path, options)}


def take_grant(home, owner: str, ref) -> tuple[Path, dict]:
    """Read and remove a grant; a grant is used once."""
    if type(ref) is not str or not _GRANT.fullmatch(ref):
        raise ExportError("GRANT_NOT_FOUND")
    path = _grants(home, owner) / f"{ref}.json"
    try:
        doc = json.loads(path.read_bytes())
        path.unlink()
    except (OSError, ValueError):
        raise ExportError("GRANT_NOT_FOUND") from None
    return Path(doc["destination"]), dict(doc["options"])
