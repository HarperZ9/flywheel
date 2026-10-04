"""server.py -- the signer process: three operations, nothing else.

  * ``hello``: the public key, its key id, and the isolation the signer
    measured for this caller. Lets a client check the pin before relying on it.
  * ``sign_record``: attest one store record, if and only if it extends the
    store's signed history by exactly one (see journal.py).
  * ``head``: a signed statement of the last record signed for a store.

Every reply that carries a signature carries the caller isolation the signer
measured itself, inside the signed bytes, so the caller cannot relabel a
same-identity signature as a separate-identity one.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from . import keys, statement
from .journal import Journal, JournalConflict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z")


class Signer:
    def __init__(self, home: Path, clock=_now) -> None:
        self.sign, self.public = keys.load(home)
        self.key_id = statement.key_id_for(self.public)
        self.journal = Journal(home)
        self.clock = clock

    def _signed(self, body: dict) -> dict:
        body["signature"] = bytes(self.sign(statement.preimage(body))).hex()
        return body

    def sign_record(self, req: dict, isolation: dict) -> dict:
        store, seq = req.get("store"), req.get("seq")
        prev, seal = req.get("prev", ""), req.get("seal")
        statement.check_record_fields(store, seq, prev, seal)
        self.journal.advance(store, seq, prev, seal)
        return self._signed(statement.attestation_body(
            store=store, seq=seq, prev=prev, seal=seal, signed_at=self.clock(),
            isolation=isolation, key_id=self.key_id))

    def head(self, req: dict, isolation: dict) -> dict:
        store = req.get("store")
        if not isinstance(store, str) or not store:
            raise statement.StatementError("store must be a non-empty string")
        last = self.journal.head(store)
        return self._signed(statement.head_body(
            store=store, seq=last["seq"], seal=last["seal"],
            rewinds=last["rewinds"], signed_at=self.clock(),
            isolation=isolation, key_id=self.key_id))

    def handle(self, req: dict, isolation: dict) -> dict:
        op = req.get("op")
        try:
            if op == "hello":
                return {"ok": True, "public_key": self.public.hex(),
                        "key_id": self.key_id, "isolation": isolation}
            if op == "sign_record":
                return {"ok": True, "attestation": self.sign_record(req, isolation)}
            if op == "head":
                return {"ok": True, "head": self.head(req, isolation)}
            return {"ok": False, "error": "unknown_op"}
        except JournalConflict as exc:
            return {"ok": False, "error": "conflict", "detail": str(exc)}
        except statement.StatementError as exc:
            return {"ok": False, "error": "bad_request", "detail": str(exc)}


def transport():
    if sys.platform == "win32":
        from . import transport_win as t
    else:
        from . import transport_posix as t
    return t


def serve(home: Path, address: str, ready=None) -> None:
    signer = Signer(home)
    transport().serve(address, signer.handle, ready=ready)
