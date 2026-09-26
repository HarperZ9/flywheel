"""Captured turns: pending prompts, pairing, turn records (7.2, F-03, S8a).

A prompt hook leaves a pending record per prompt: its key (Claude Code
`prompt_id`, Codex `turn_id`, or none), its commitment and salt, and its text
when content capture is on. A Stop pairs by key, else first-in-first-out
within the session; a Stop with `stop_hook_active` adds a segment to the
prompt it continues; a Stop with no prompt is `unpaired` and records no
prompt commitment, never a digest of an empty prompt. A pending prompt older
than its time to live becomes an unpaired turn, checked lazily on every call.

Pending and turn records are encrypted items of store CT under
`state/captured-turns/v1/owners/<owner>/`: `pending/<session_ref>-<ns>-<rand>.enc`
and `<client>/<yyyy-mm>/<turn_ref>.enc`. Each turn chains a v2 receipt.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import time

from .capture_hooks.protocol import commitment
from .evidence_json import canonical_bytes
from .trace_custody_lock import custody_lock
from .trace_enc_write import ItemCipher
from .trace_keystore import Keystore
from .trace_turn_receipt import build, keyed_ref, store_receipt

STORE = "CT"


def _b64(raw) -> str | None:
    return base64.b64encode(raw).decode("ascii") if raw is not None else None


class TurnStore:
    def __init__(self, home, owner_ref: str, *, clock=None, settings=None, provider=None):
        from .trace_capture_settings import DEFAULTS
        self.home, self.owner_ref = Path(home), owner_ref
        self.state = self.home / "state"
        self.base = self.state / "captured-turns" / "v1" / "owners" / owner_ref
        self.clock = clock or time.time
        self.settings = settings or dict(DEFAULTS)
        self.provider = provider
        self.keystore = Keystore(self.state, owner_ref, provider)

    def _cipher(self, item: str) -> ItemCipher:
        return ItemCipher(self.state, self.owner_ref, STORE, item, provider=self.provider,
                          keystore=self.keystore)

    def _write(self, path: Path, item: str, doc: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name("." + path.name + ".tmp")
        temporary.write_bytes(self._cipher(item).seal("record", canonical_bytes(doc)))
        os.replace(temporary, path)

    def _read(self, path: Path, item: str) -> dict:
        return json.loads(self._cipher(item).open("record", path.read_bytes()))

    def _session_ref(self, client: str, session_id) -> str:
        return keyed_ref(self.keystore.custody_key(), "session", client, session_id or "none")

    def _pendings(self, session_ref: str | None = None) -> list[tuple[Path, dict]]:
        directory = self.base / "pending"
        pattern = f"{session_ref}-*.enc" if session_ref else "*.enc"
        found = sorted(directory.glob(pattern)) if directory.is_dir() else []
        return [(path, self._read(path, path.stem)) for path in found]

    @staticmethod
    def _commit(kind: str, text, given, salt):
        if text is not None:
            salt = os.urandom(32)
            return commitment(kind, salt, text), salt
        return given, salt

    def prompt(self, client: str, session_id, prompt_key, *, commitment=None, salt=None,
               text=None) -> dict:
        self.expire()
        keep_text = text if self.settings.get("content") == "on" else None
        value, salt = self._commit("prompt", text, commitment, salt)
        session_ref = self._session_ref(client, session_id)
        name = f"{session_ref}-{time.time_ns():020d}-{secrets.token_hex(4)}"
        doc = {"schema": "flywheel.capture-pending/v1", "client": client,
               "prompt_key": prompt_key, "prompt_commitment": value, "prompt_salt": _b64(salt),
               "prompt_text": keep_text, "created_at": self.clock(), "state": "pending",
               "segments": 0}
        with custody_lock(self.state):
            self._write(self.base / "pending" / f"{name}.enc", name, doc)
        return {"pending_ref": name}

    def _match(self, session_ref: str, prompt_key, active: bool):
        candidates = self._pendings(session_ref)
        if active:
            paired = [(p, d) for p, d in candidates if d["state"] == "paired"
                      and (prompt_key is None or d["prompt_key"] == prompt_key)]
            return paired[-1] if paired else None
        waiting = [(p, d) for p, d in candidates if d["state"] == "pending"]
        if prompt_key is not None:
            keyed = [(p, d) for p, d in waiting if d["prompt_key"] == prompt_key]
            return keyed[0] if keyed else None
        unkeyed = [(p, d) for p, d in waiting if d["prompt_key"] is None]
        return unkeyed[0] if unkeyed else None

    def stop(self, client: str, session_id, prompt_key, *, commitment=None, salt=None,
             text=None, stop_hook_active: bool = False) -> dict:
        self.expire()
        keep_text = text if self.settings.get("content") == "on" else None
        answer, salt = self._commit("answer", text, commitment, salt)
        session_ref = self._session_ref(client, session_id)
        with custody_lock(self.state):
            found = self._match(session_ref, prompt_key, stop_hook_active)
            mode = "unpaired" if found is None else (
                "fifo" if found[1]["prompt_key"] is None else
                ("turn_id" if client == "codex" else "prompt_id"))
            pending = found[1] if found else {}
            segment = pending.get("segments", 0)
            result = self._record(client, session_ref, prompt_key, mode, segment, pending,
                                  answer, salt, keep_text)
            if found is not None:
                self._write(found[0], found[0].stem, {**pending, "state": "paired",
                                                      "segments": segment + 1})
        return result

    def _record(self, client, session_ref, prompt_key, mode, segment, pending, answer, salt,
                answer_text) -> dict:
        custody = self.keystore.custody_key()
        key_ref = keyed_ref(custody, "prompt-key", client, prompt_key) if prompt_key else None
        envelope, freeze_salt = pending.get("freeze"), os.urandom(32)
        freeze_value = (commitment("freeze", freeze_salt, canonical_bytes(envelope).decode())
                        if envelope else None)
        receipt = store_receipt(self.home, build(
            client=client, session_ref=session_ref, prompt_key_ref=key_ref, pairing=mode,
            segment=segment, prompt_commitment=pending.get("prompt_commitment"),
            answer_commitment=answer,
            captured_content=bool(pending.get("prompt_text") or answer_text),
            frozen_urls=len(envelope["sources"]) if envelope else 0,
            refused_urls=envelope["refused"] if envelope else 0,
            freeze_commitment=freeze_value))
        turn_ref = "turn_" + secrets.token_hex(16)
        month = datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y-%m")
        doc = {"schema": "flywheel.captured-turn/v1", "turn_ref": turn_ref, "client": client,
               "receipt_eid": receipt["eid"], "pairing": mode, "segment": segment,
               "prompt_salt": pending.get("prompt_salt"), "answer_salt": _b64(salt),
               "prompt_text": pending.get("prompt_text"), "answer_text": answer_text,
               "freeze": envelope, "freeze_salt": _b64(freeze_salt) if envelope else None}
        self._write(self.base / client / month / f"{turn_ref}.enc", turn_ref, doc)
        return {"eid": receipt["eid"], "pairing": mode, "segment": segment,
                "turn_ref": turn_ref}

    def freeze(self, client: str, session_id, prompt_key, urls) -> dict:
        from .trace_capture_freeze import freeze
        if self.settings.get("freeze_urls") != "on":
            return {"frozen": 0, "refused": 0, "failed": 0, "sources": [],
                    "reason": "FREEZE_OFF"}
        return freeze(self, client, session_id, prompt_key, urls)

    def expire(self) -> int:
        """Pending prompts past their time to live become unpaired turns; paired
        records past it are removed with their keys."""
        ttl = self.settings.get("pending_ttl_hours", 24) * 3600
        written = 0
        with custody_lock(self.state):
            for path, doc in self._pendings():
                if self.clock() - doc["created_at"] <= ttl:
                    continue
                if doc["state"] == "pending":
                    self._record(doc["client"], path.stem.split("-")[0], doc["prompt_key"],
                                 "unpaired", 0, doc, None, None, None)
                    written += 1
                self.keystore.destroy(STORE, [path.stem])
                path.unlink()
        return written

    def turns(self) -> list[dict]:
        out = []
        for path in sorted(self.base.glob("*/*/turn_*.enc")) if self.base.is_dir() else []:
            out.append({"turn_ref": path.stem, "client": path.parent.parent.name,
                        "month": path.parent.name})
        return out

    def read_turn(self, turn_ref: str) -> dict:
        for path in self.base.glob(f"*/*/{turn_ref}.enc"):
            return self._read(path, turn_ref)
        raise FileNotFoundError(turn_ref)


def _owners(home) -> list[str]:
    base = Path(home) / "state" / "captured-turns" / "v1" / "owners"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def export_records(home) -> list[dict]:
    """Export adapter: every captured turn, decrypted; the owner's own copy."""
    out = []
    for owner in _owners(home):
        store = TurnStore(home, owner)
        out.extend(store.read_turn(t["turn_ref"]) for t in store.turns())
    return out


def delete_all(home) -> dict:
    """Delete adapter for a whole-custody deletion: keys first, then files."""
    from .trace_meta_adapters import remove_tree
    removed = 0
    for owner in _owners(home):
        store = TurnStore(home, owner)
        items = [p.stem for p in store.base.rglob("*.enc")]
        store.keystore.destroy(STORE, items)
        removed += remove_tree(store.base)
    return {"removed": removed}
