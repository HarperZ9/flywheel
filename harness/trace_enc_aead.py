"""AES-256-GCM provider for macOS and Linux, behind the `encryption` extra.

The master key lives in the OS keychain (`security` on macOS, `secret-tool`
on Linux), passed on stdin and never on a command line. Each item is
encrypted under HMAC-SHA256(master, item key), with a random 12-byte nonce
and the file header as associated data. `cryptography` is imported inside
functions, so no console script breaks when the extra is not installed.

Keychain access has no CI coverage; it is a manual check, and when the
keychain or the extra is missing the caller falls back to plaintext and says
so. Tests use the same provider with a key held in memory.

A master key is created only when the keychain says it holds none (the
lookup's own not-found exit), and only when sealing, never when opening what
an earlier key sealed. A lookup that fails or times out (a locked keyring
still waiting on its unlock prompt) is OS_KEY_UNAVAILABLE: creating a key
then would replace the one every sealed shard needs.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
import sys

from .trace_enc import EncError
from . import safe_program

SERVICE = "flywheel-trace-custody"
_NONCE = 12


class AeadProvider:
    name = "aes-256-gcm"

    def __init__(self, master_key, *, sealing_key=None) -> None:
        self._master_key = master_key  # a callable returning 32 bytes
        self._sealing_key = sealing_key or master_key  # may create the key

    def _gcm(self, key: bytes):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key)

    def _item_key(self, key: bytes) -> bytes:
        return hmac.new(self._master_key(), b"flywheel.item.v1\0" + key,
                        hashlib.sha256).digest()

    def _box(self, key: bytes, data: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE)
        return nonce + self._gcm(key).encrypt(nonce, data, aad)

    def _open(self, key: bytes, blob: bytes, aad: bytes) -> bytes:
        from cryptography.exceptions import InvalidTag
        try:
            return self._gcm(key).decrypt(blob[:_NONCE], blob[_NONCE:], aad)
        except (InvalidTag, ValueError):
            raise EncError("ENC_INTEGRITY") from None

    def encrypt(self, key, plaintext, aad):
        return self._box(self._item_key(key), plaintext, aad)

    def decrypt(self, key, blob, aad):
        return self._open(self._item_key(key), blob, aad)

    def seal(self, data, context):
        return self._box(self._sealing_key(), data, context)

    def unseal(self, blob, context):
        return self._open(self._master_key(), blob, context)

    def status(self) -> dict:
        return {"provider": self.name, "available": True,
                "protection": "encrypted (aes-256-gcm, keychain key)"}


_NOT_FOUND = {"darwin": 44}  # security(1): errSecItemNotFound


def _run(argv, stdin: bytes | None = None) -> bytes | None:
    done = _run_status(argv, stdin)
    return done[1] if done and done[0] == 0 else None


def _run_status(argv, stdin: bytes | None = None):
    """(exit code, stdout, stderr), or None when the tool did not run or timed out."""
    try:
        command, env = safe_program.launch(argv)
        done = subprocess.run(command, input=stdin, capture_output=True, timeout=20, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.returncode, done.stdout, done.stderr


def _keychain_lookup() -> tuple[bytes | None, bool]:
    """(key, whether the keychain definitely holds none)."""
    if sys.platform == "darwin":
        done = _run_status(["security", "find-generic-password", "-s", SERVICE, "-a",
                            "custody", "-w"])
    else:
        done = _run_status(["secret-tool", "lookup", "service", SERVICE, "account", "custody"])
    if done is None:
        return None, False
    code, out, err = done
    if code != 0:
        absent = code == _NOT_FOUND.get(sys.platform, 1) and not out.strip() and not err.strip()
        return None, absent
    try:
        key = bytes.fromhex(out.decode().strip())
    except (UnicodeError, ValueError):
        return None, False
    return (key, False) if len(key) == 32 else (None, False)


def _keychain_get() -> bytes | None:
    return _keychain_lookup()[0]


def _keychain_create() -> bytes | None:
    secret = os.urandom(32).hex().encode()
    if sys.platform == "darwin":
        # -w with no value reads the password from stdin, twice (entry and confirm).
        _run(["security", "add-generic-password", "-s", SERVICE, "-a", "custody", "-w"],
             secret + b"\n" + secret + b"\n")
    else:
        _run(["secret-tool", "store", "--label=Flywheel trace custody", "service", SERVICE,
              "account", "custody"], secret)
    return _keychain_get()


def keychain_provider():
    """An AES-GCM provider with a keychain key, or None when the extra or the
    keychain tool is missing."""
    try:
        import cryptography.hazmat.primitives.ciphers.aead  # noqa: F401
    except ImportError:
        return None
    if not safe_program.which("security" if sys.platform == "darwin" else "secret-tool"):
        return None
    opener, sealer = _masters(_keychain_lookup, _keychain_create)
    return AeadProvider(opener, sealing_key=sealer)


def _masters(lookup, create):
    """(open, seal) master-key callables sharing one cache. Only seal creates,
    and only after a lookup that says the keychain holds no key."""
    cache: list[bytes] = []

    def master(may_create: bool) -> bytes:
        if not cache:
            key, absent = lookup()
            if key is None and absent and may_create:
                key = create()
            if key is None:
                raise EncError("OS_KEY_UNAVAILABLE")
            cache.append(key)
        return cache[0]
    return (lambda: master(False)), (lambda: master(True))
