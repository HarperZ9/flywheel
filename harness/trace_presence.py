"""Owner presence for destructive and egress custody operations (7.15, I17).

An agent running as the owner holds the owner's operating-system authority
but not the owner's intent. Delete apply, retention adoption and large runs,
export, re-import, sync-root export, capture settings, recovery keys, bulk
replay and a change of the presence method itself each need a confirmation
bound to the operation's plan digest, one use, valid for five minutes.

A confirmation counts only in the process whose verifier answered it: the
satisfied state lives in that process's memory. The challenge file on disk
is an audit record and is never read back as proof, so writing a file that
says `satisfied` confirms nothing. The CLI confirms and applies in one
process; a route confirms and applies inside the gateway.

The method in effect is `windows-hello` or `none` (plus `doctor-synthetic`,
which only the doctor's own records get, through `confirm_synthetic`). It is
adopted only through presence under the method already in effect. The method
file must match the latest adoption in the verified custody ledger; a file
that does not is SETTINGS_TAMPERED, and a missing file after an adoption is
refused rather than read as `none`. With `none`, status and every report say
that any process running as the owner, agents included, can perform these
operations. Presence gates the CLI and the routes; code that runs as the
owner and calls this library directly is not stopped by it.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import threading
import time

from .evidence_json import canonical_bytes, canonical_sha256
from .trace_custody_lock import custody_lock

TTL_S = 300
KINDS = ("delete_apply", "retention_adopt", "retention_apply", "export",
         "import_allow_reimport", "import_suffix", "export_allow_sync_root",
         "capture_settings", "recovery_key", "bench_replay", "presence_method")
METHODS = ("windows-hello", "none")
RETIRED = ("desktop-dialog",)
STATEMENT = ("any process running as the owner, agents included, can perform delete, "
             "export, retention and capture-setting changes")
_REF = re.compile(r"prs_[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_DOCTOR_SESSION = re.compile(r"flywheel-doctor-[0-9a-f]{16}\Z")
_LIVE: dict[str, dict] = {}
_LIVE_LOCK = threading.Lock()


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


def _scope(state_root, owner_ref: str) -> str:
    return os.path.normcase(os.path.abspath(str(state_root))) + "|" + owner_ref


class PresenceStore:
    """Challenges for one owner. Memory is the authority; files are records."""

    def __init__(self, state_root, owner_ref: str, *, clock=None) -> None:
        self.state_root, self.owner_ref = Path(state_root), owner_ref
        self.dir = _root(state_root, owner_ref) / "challenges"
        self.clock = clock or time.time
        self.scope = _scope(state_root, owner_ref)

    def _path(self, ref: str) -> Path:
        if type(ref) is not str or not _REF.fullmatch(ref):
            raise PresenceError("PRESENCE_REQUIRED")
        return self.dir / f"{ref}.json"

    def _live(self, ref) -> dict:
        self._path(ref)
        doc = _LIVE.get(ref)
        if doc is None or doc["scope"] != self.scope:
            raise PresenceError("PRESENCE_REQUIRED")
        return doc

    def _record(self, doc: dict) -> None:
        with custody_lock(self.state_root):
            _write(self._path(doc["ref"]), {k: v for k, v in doc.items() if k != "scope"})

    def create(self, kind: str, plan_digest: str, *, synthetic: bool = False) -> dict:
        if kind not in KINDS or type(plan_digest) is not str or not _DIGEST.fullmatch(plan_digest):
            raise PresenceError("PRESENCE_INVALID")
        now = self.clock()
        doc = {"schema": "flywheel.presence-challenge/v1", "ref": "prs_" + secrets.token_hex(16),
               "kind": kind, "plan_digest": plan_digest, "created_at": now,
               "expires_at": now + TTL_S, "state": "pending", "method": None,
               "synthetic": synthetic, "scope": self.scope}
        with _LIVE_LOCK:
            for ref in [r for r, d in _LIVE.items() if d["expires_at"] + TTL_S < now]:
                del _LIVE[ref]
            _LIVE[doc["ref"]] = doc
        self._record(doc)
        return {k: v for k, v in doc.items() if k != "scope"}

    def _satisfy(self, ref: str, method: str) -> None:
        with _LIVE_LOCK:
            doc = self._live(ref)
            if method == "doctor-synthetic" and not doc["synthetic"] or (
                    method not in METHODS and method != "doctor-synthetic"):
                raise PresenceError("PRESENCE_METHOD")
            if doc["state"] != "pending":
                raise PresenceError("PRESENCE_USED")
            doc.update(state="satisfied", method=method)
        self._record(doc)

    def deny(self, ref: str) -> None:
        with _LIVE_LOCK:
            doc = self._live(ref)
            doc["state"] = "denied"
        self._record(doc)

    def consume(self, ref, kind: str, plan_digest: str) -> str:
        if ref is None:
            raise PresenceError("PRESENCE_REQUIRED")
        with _LIVE_LOCK:
            doc = self._live(ref)
            if doc["kind"] != kind or doc["plan_digest"] != plan_digest:
                raise PresenceError("PRESENCE_MISMATCH")
            if doc["state"] == "used":
                raise PresenceError("PRESENCE_USED")
            if self.clock() > doc["expires_at"]:
                raise PresenceError("PRESENCE_EXPIRED")
            if doc["state"] != "satisfied":
                raise PresenceError("PRESENCE_REQUIRED")
            doc["state"] = "used"
        self._record(doc)
        return doc["method"]

    def pending(self) -> list[dict]:
        now = self.clock()
        with _LIVE_LOCK:
            return [{k: d[k] for k in ("ref", "kind", "plan_digest", "expires_at")}
                    for d in _LIVE.values() if d["scope"] == self.scope
                    and d["state"] == "pending" and now <= d["expires_at"]]


def adopted_method(state_root, owner_ref: str) -> str:
    """The method in effect; raises PRESENCE_CONFIG_MISSING or SETTINGS_TAMPERED."""
    import json
    from .trace_custody_ledger import LedgerError
    from .trace_settings_guard import TAMPERED, adopted_digest
    try:
        recorded = adopted_digest(Path(state_root).parent, owner_ref, "presence_method")
    except (LedgerError, OSError, ValueError):
        raise PresenceError("PRESENCE_CONFIG_MISSING") from None
    try:
        method = json.loads(method_path(state_root, owner_ref).read_bytes()).get("method")
    except FileNotFoundError:
        if recorded is not None:
            raise PresenceError("PRESENCE_CONFIG_MISSING") from None
        return "none"
    except (OSError, ValueError, AttributeError):
        raise PresenceError("PRESENCE_CONFIG_MISSING") from None
    if method not in METHODS + RETIRED:
        raise PresenceError("PRESENCE_CONFIG_MISSING")
    if recorded != method_digest(method):
        raise PresenceError(TAMPERED)
    return "none" if method in RETIRED else method


def confirm(state_root, owner_ref: str, kind: str, plan_digest: str, summary: str, *,
            verifier=None, clock=None) -> str:
    """Create a challenge and have the adopted method's verifier answer it."""
    from .trace_presence_verifiers import verifier_for
    method = adopted_method(state_root, owner_ref)
    verifier = verifier or verifier_for(method)
    if verifier.name != method:
        raise PresenceError("PRESENCE_METHOD")
    store = PresenceStore(state_root, owner_ref, clock=clock)
    ref = store.create(kind, plan_digest)["ref"]
    if not verifier.ask(summary):
        store.deny(ref)
        raise PresenceError("PRESENCE_DENIED")
    store._satisfy(ref, method)
    return ref


def confirm_synthetic(home, owner_ref: str, session: str) -> tuple[str, str]:
    """(plan digest, presence ref) for deleting the doctor's own synthetic
    session: the plan is built here from that session's turns only."""
    from .trace_delete_adapters_enc import session_turns
    from .trace_delete_plan import make_plan
    if type(session) is not str or not _DOCTOR_SESSION.fullmatch(session):
        raise PresenceError("PRESENCE_METHOD")
    turns = session_turns(Path(home), owner_ref, "claude-code", session)
    if not turns:
        raise PresenceError("PRESENCE_INVALID")
    plan = make_plan(home, owner_ref, {"turn_refs": turns})
    store = PresenceStore(Path(home) / "state", owner_ref)
    ref = store.create("delete_apply", plan["plan_digest"], synthetic=True)["ref"]
    store._satisfy(ref, "doctor-synthetic")
    return plan["plan_digest"], ref


def require(state_root, owner_ref: str, kind: str, plan_digest: str, presence_ref, *,
            clock=None) -> str:
    """The method that confirmed this operation; raises PRESENCE_* otherwise."""
    return PresenceStore(state_root, owner_ref, clock=clock).consume(presence_ref, kind,
                                                                     plan_digest)


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
        return {"method": "unknown", "statement": exc.code + ": gated operations are refused "
                "until the presence method is set again"}
    return {"method": method, "statement": STATEMENT if method == "none" else
            "an operation through the CLI or the gateway proceeds only after this method "
            "confirms its plan digest"}
