"""Where an export may be written (7.5, SP-36, I12).

A destination comes from the local CLI or from a grant the CLI wrote naming
the exact path; no HTTP request supplies one. It is refused inside
FLYWHEEL_HOME, refused when it exists and is not empty, and refused under a
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

_DEVICE = re.compile(r"^(\\\\[?.]\\|//[?.]/)")
_GRANT = re.compile(r"xgr_[0-9a-f]{32}\Z")


class ExportError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _inside(path: Path, root: Path) -> bool:
    a = os.path.normcase(os.path.abspath(str(path)))
    b = os.path.normcase(os.path.abspath(str(root)))
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def check(out, home, *, allow_sync_root: bool = False) -> tuple[Path, str | None]:
    """(absolute destination, sync client or None); raises ExportError."""
    from .trace_fs_attrs import sync_root
    text = str(out)
    if _DEVICE.match(text):
        raise ExportError("DESTINATION_DEVICE")
    path = Path(os.path.abspath(text))
    if _inside(path, Path(home)) or _inside(Path(home), path):
        raise ExportError("DESTINATION_IN_CUSTODY")
    synced = sync_root(path)
    if synced and not allow_sync_root:
        raise ExportError("DESTINATION_SYNC_ROOT")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ExportError("DESTINATION_NOT_EMPTY")
    return path, synced


def protect(folder: Path) -> None:
    """Owner-only ACL and not-indexed, on the folder before files go in."""
    from .operation_grants import _secure_owner_only
    from .trace_fs_attrs import set_not_indexed
    try:
        _secure_owner_only(folder, directory=True)
        set_not_indexed(folder)
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


def _grants(home, owner: str) -> Path:
    return Path(home) / "state" / "trace-export" / "v1" / "owners" / owner / "grants"


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
