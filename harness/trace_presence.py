"""Owner presence for destructive and egress custody operations (7.15, I17).

An agent running as the owner holds the owner's operating-system authority
but not the owner's intent. Delete apply, retention adoption and large runs,
export, re-import, sync-root export, capture settings, recovery keys, bulk
replay and a change of the presence method itself each need a confirmation
bound to the operation's plan digest, one use, valid for five minutes.

The method in effect is `windows-hello`, `desktop-dialog` or `none` (plus
`doctor-synthetic`, for records the doctor made in the same run). It is
adopted only through presence under the method already in effect, and a
missing method file after an adoption is refused rather than read as `none`.
With `none`, status and every report say that any process running as the
owner, agents included, can perform these operations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import time

from .evidence_json import canonical_bytes, canonical_sha256
from .trace_custody_lock import custody_lock

TTL_S = 300
KINDS = ("delete_apply", "retention_adopt", "retention_apply", "export",
         "import_allow_reimport", "import_suffix", "export_allow_sync_root",
         "capture_settings", "recovery_key", "bench_replay", "presence_method")
METHODS = ("windows-hello", "desktop-dialog", "none")
STATEMENT = ("any process running as the owner, agents included, can perform delete, "
             "export, retention and capture-setting changes")
_REF = re.compile(r"prs_[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class PresenceError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _root(state_root, owner_ref: str) -> Path:
    return Path(state_root) / "presence" / "v1" / "owners" / owner_ref


def method_path(state_root, owner_ref: str) -> Path:
    return _root(state_root, owner_ref) / "method.json"


def method_digest(method: str) -> str:
    return canonical_sha256({"schema": "flywheel.presence-method/v1", "method": method})


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_bytes(doc))
    os.replace(temporary, path)


class PresenceStore:
    def __init__(self, state_root, owner_ref: str, *, clock=None) -> None:
        self.state_root, self.owner_ref = Path(state_root), owner_ref
        self.dir = _root(state_root, owner_ref) / "challenges"
        self.clock = clock or time.time

    def _path(self, ref: str) -> Path:
        if type(ref) is not str or not _REF.fullmatch(ref):
            raise PresenceError("PRESENCE_REQUIRED")
        return self.dir / f"{ref}.json"

    def _load(self, ref: str) -> dict:
        try:
            return json.loads(self._path(ref).read_bytes())
        except (OSError, ValueError):
            raise PresenceError("PRESENCE_REQUIRED") from None

    def create(self, kind: str, plan_digest: str, *, synthetic: bool = False) -> dict:
        if kind not in KINDS or type(plan_digest) is not str or not _DIGEST.fullmatch(plan_digest):
            raise PresenceError("PRESENCE_INVALID")
        now = self.clock()
        doc = {"schema": "flywheel.presence-challenge/v1", "ref": "prs_" + secrets.token_hex(16),
               "kind": kind, "plan_digest": plan_digest, "created_at": now,
               "expires_at": now + TTL_S, "state": "pending", "method": None,
               "synthetic": synthetic}
        with custody_lock(self.state_root):
            _write(self._path(doc["ref"]), doc)
        return doc

    def satisfy(self, ref: str, method: str) -> None:
        with custody_lock(self.state_root):
            doc = self._load(ref)
            if method == "doctor-synthetic" and not doc["synthetic"] or (
                    method not in METHODS and method != "doctor-synthetic"):
                raise PresenceError("PRESENCE_METHOD")
            if doc["state"] != "pending":
                raise PresenceError("PRESENCE_USED")
            _write(self._path(ref), {**doc, "state": "satisfied", "method": method})

    def deny(self, ref: str) -> None:
        with custody_lock(self.state_root):
            _write(self._path(ref), {**self._load(ref), "state": "denied"})

    def consume(self, ref, kind: str, plan_digest: str) -> str:
        if ref is None:
            raise PresenceError("PRESENCE_REQUIRED")
        with custody_lock(self.state_root):
            doc = self._load(ref)
            if doc["kind"] != kind or doc["plan_digest"] != plan_digest:
                raise PresenceError("PRESENCE_MISMATCH")
            if doc["state"] == "used":
                raise PresenceError("PRESENCE_USED")
            if self.clock() > doc["expires_at"]:
                raise PresenceError("PRESENCE_EXPIRED")
            if doc["state"] != "satisfied":
                raise PresenceError("PRESENCE_REQUIRED")
            _write(self._path(ref), {**doc, "state": "used"})
            return doc["method"]

    def pending(self) -> list[dict]:
        now, out = self.clock(), []
        for path in sorted(self.dir.glob("prs_*.json")) if self.dir.is_dir() else []:
            doc = self._load(path.stem)
            if doc["state"] == "pending" and now <= doc["expires_at"]:
                out.append({k: doc[k] for k in ("ref", "kind", "plan_digest", "expires_at")})
        return out


def adopted_method(state_root, owner_ref: str) -> str:
    path = method_path(state_root, owner_ref)
    try:
        method = json.loads(path.read_bytes()).get("method")
    except FileNotFoundError:
        from .trace_custody_ledger import CustodyLedger
        entries = CustodyLedger(Path(state_root).parent, owner_ref).entries()
        if any(e["kind"] == "settings_adopted" and e["fields"].get("settings") ==
               "presence_method" for e in entries):
            raise PresenceError("PRESENCE_CONFIG_MISSING") from None
        return "none"
    except (OSError, ValueError, AttributeError):
        raise PresenceError("PRESENCE_CONFIG_MISSING") from None
    if method not in METHODS:
        raise PresenceError("PRESENCE_CONFIG_MISSING")
    return method


def confirm(state_root, owner_ref: str, kind: str, plan_digest: str, summary: str, *,
            verifier=None, clock=None, synthetic: bool = False) -> str:
    """Create a challenge and have the adopted method's verifier answer it."""
    from .trace_presence_verifiers import verifier_for
    method = adopted_method(state_root, owner_ref)
    verifier = verifier or verifier_for(method)
    if verifier.name != method:
        raise PresenceError("PRESENCE_METHOD")
    store = PresenceStore(state_root, owner_ref, clock=clock)
    ref = store.create(kind, plan_digest, synthetic=synthetic)["ref"]
    if method == "desktop-dialog":
        return ref  # pending until the desktop app approves it
    if not verifier.ask(summary):
        store.deny(ref)
        raise PresenceError("PRESENCE_DENIED")
    store.satisfy(ref, method)
    return ref


def require(state_root, owner_ref: str, kind: str, plan_digest: str, presence_ref, *,
            clock=None) -> str:
    """The method that confirmed this operation; raises PRESENCE_* otherwise."""
    return PresenceStore(state_root, owner_ref, clock=clock).consume(presence_ref, kind,
                                                                     plan_digest)


def approve_from_desktop(state_root, owner_ref: str, ref: str) -> None:
    if adopted_method(state_root, owner_ref) != "desktop-dialog":
        raise PresenceError("PRESENCE_METHOD")
    PresenceStore(state_root, owner_ref).satisfy(ref, "desktop-dialog")


def set_method(state_root, owner_ref: str, method: str, presence_ref) -> dict:
    from .trace_witness import record_custody_event
    if method not in METHODS:
        raise PresenceError("PRESENCE_INVALID")
    digest = method_digest(method)
    used = require(state_root, owner_ref, "presence_method", digest, presence_ref)
    _write(method_path(state_root, owner_ref), {"schema": "flywheel.presence-method/v1",
                                                "method": method})
    return record_custody_event(Path(state_root).parent, owner_ref, "settings_adopted",
                                {"settings": "presence_method", "digest": digest}, used)


def presence_status(state_root, owner_ref: str) -> dict:
    try:
        method = adopted_method(state_root, owner_ref)
    except PresenceError as exc:
        return {"method": "unknown", "statement": exc.code}
    return {"method": method, "statement": STATEMENT if method == "none" else
            "an operation proceeds only after this method confirms its plan digest"}
