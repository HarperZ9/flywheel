"""Encrypting one item's files, and writing them new-or-equivalent (7.3).

`ItemCipher` is what a store uses per item: `seal(file, plaintext)` returns
the bytes to write (ciphertext when a provider is available, the plaintext
otherwise unless the store's floor forbids it), making the item key durable
first and setting the floor after the first encrypted write; `open(file,
blob)` returns the plaintext, enforcing binding, the prefix rule and key
presence. A lost OS key (OS_KEY_UNAVAILABLE) writes one loss record per item
and process, never an integrity failure.

The pinned filesystem's `write_new_or_same` compares bytes, and ciphertext
differs on every write, so `write_new_or_equivalent` reads a conflicting file
back, decrypts it and compares plaintext. Nothing is added to the 300-line
backend.
"""
from __future__ import annotations

import logging
from pathlib import Path
import threading

from . import trace_enc
from .trace_enc import EncError, decode, encode, is_encrypted
from .trace_enc_floor import PrefixCheck, has_floor, set_floor

_log = logging.getLogger(__name__)
_REPORTED: set[tuple[str, str, str]] = set()
_REPORTED_LOCK = threading.Lock()


class ItemCipher:
    def __init__(self, state_root, owner_ref: str, store: str, item: str, *,
                 provider=None, keystore=None) -> None:
        from .trace_keystore import Keystore
        self.state_root, self.owner_ref = Path(state_root), owner_ref
        self.store, self.item = store, item
        self.provider = provider or trace_enc.default_provider()
        self.keystore = keystore or Keystore(self.state_root, owner_ref, self.provider)
        self.prefix = PrefixCheck()

    @property
    def encrypting(self) -> bool:
        return self.provider.name != "none"

    def bound(self, plaintext_max: int) -> int:
        return trace_enc.overhead(plaintext_max)

    def seal(self, file: str, plaintext: bytes) -> bytes:
        if not self.encrypting:
            if has_floor(self.state_root, self.owner_ref, self.store):
                raise EncError("ENC_REQUIRED")
            return plaintext
        key = self.keystore.item_key(self.store, self.item, create=True)
        blob = encode(self.provider, key, self.item, file, plaintext)
        set_floor(self.state_root, self.owner_ref, self.store)
        return blob

    def open(self, file: str, blob: bytes) -> bytes:
        if not self.prefix.feed(blob):
            return blob
        if not self.encrypting:
            raise EncError("OS_KEY_UNAVAILABLE")
        try:
            return decode(self.provider, lambda item: self.keystore.item_key(self.store, item),
                          self.item, file, blob)
        except EncError as exc:
            if exc.code == "OS_KEY_UNAVAILABLE":
                self._report_loss()
            raise

    def _report_loss(self) -> None:
        key = (str(self.state_root), self.store, self.item)
        with _REPORTED_LOCK:
            if key in _REPORTED:
                return
            _REPORTED.add(key)
        try:
            from .trace_custody_ledger import CustodyLedger
            CustodyLedger(self.state_root.parent, self.owner_ref).append("loss", {
                "store": self.store, "items": 1, "reason_code": "OS_KEY_UNAVAILABLE",
                "original": "none"})
        except Exception as exc:  # the read still fails closed with its own code
            _log.warning("loss record not written (%s)", type(exc).__name__)


def write_new_or_equivalent(fs, rel, blob: bytes, plaintext: bytes, cipher: ItemCipher,
                            file: str) -> None:
    from .private_artifact_fs import PrivateArtifactError
    try:
        fs.write_new_or_same(rel, blob)
        return
    except PrivateArtifactError as exc:
        if exc.code != "CONFLICT" or not is_encrypted(blob):
            raise
    existing = fs.read_bytes(rel, max_bytes=cipher.bound(len(plaintext)))
    check = ItemCipher(cipher.state_root, cipher.owner_ref, cipher.store, cipher.item,
                       provider=cipher.provider, keystore=cipher.keystore)
    if check.open(file, existing) != plaintext:
        raise PrivateArtifactError("CONFLICT")
