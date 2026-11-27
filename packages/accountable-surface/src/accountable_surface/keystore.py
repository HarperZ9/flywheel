"""Scoped OS keystore (Win32 Credential Manager / DPAPI) and portable authenticated vaults."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Protocol

KEYSTORE_PREFIX = "accountable-surface:"
_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
_CRED_TYPE_GENERIC, _CRED_PERSIST_SESSION, _CRYPTPROTECT_UI_FORBIDDEN = 1, 1, 0x1


class KeystoreError(RuntimeError):
    """Base error for keystore operations (never carries secret values)."""


class KeystoreScopeError(KeystoreError):
    """Target attempted to escape the accountable-surface namespace."""


class KeystoreTamperError(KeystoreError):
    """Encrypted keystore record failed MAC authentication."""


class KeystoreUnavailableError(KeystoreError):
    """Platform-specific keystore is unavailable on the current OS."""


class KeystoreProtocol(Protocol):
    """Zero-leakage keystore contract."""

    def put(self, handle: str, secret: str) -> str: ...
    def get(self, handle: str) -> str | None: ...
    def delete(self, handle: str) -> bool: ...
    def has(self, handle: str) -> bool: ...
    def fingerprint(self, handle: str) -> str | None: ...


def secret_fingerprint(secret: str | bytes) -> str:
    """Return a non-reversible sha256 fingerprint safe for status and receipt surfaces."""
    raw = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
    return "sha256:" + hashlib.sha256(raw).hexdigest()[:16]


def scoped_target_name(namespace: str, handle: str) -> str:
    """Build a strictly scoped keystore target under accountable-surface:<ns>:<handle>."""
    if not _SEGMENT_RE.fullmatch(namespace) or ".." in namespace or not _SEGMENT_RE.fullmatch(handle) or ".." in handle:
        raise KeystoreScopeError("invalid keystore namespace or handle")
    return f"{KEYSTORE_PREFIX}{namespace}:{handle}"


def validate_scoped_target(target: str) -> str:
    """Fail-closed guard ensuring target never escapes the accountable-surface prefix."""
    if not isinstance(target, str) or not target.startswith(KEYSTORE_PREFIX):
        raise KeystoreScopeError("refused keystore access outside accountable-surface: namespace")
    parts = target[len(KEYSTORE_PREFIX):].split(":")
    if len(parts) != 2 or not all(_SEGMENT_RE.fullmatch(p) and ".." not in p for p in parts):
        raise KeystoreScopeError("malformed scoped keystore target")
    return target


def _validate_secret_text(secret: str) -> str:
    if not isinstance(secret, str) or not secret or "\x00" in secret:
        raise KeystoreError("secret must be a non-empty string without null bytes")
    return secret


class MemoryKeystore:
    """Deterministic in-memory scoped keystore with redacted repr."""

    def __init__(self, namespace: str = "default") -> None:
        scoped_target_name(namespace, "probe")
        self.namespace, self._items = namespace, {}

    def __repr__(self) -> str:
        return f"MemoryKeystore(namespace={self.namespace!r}, count={len(self._items)})"

    def put(self, handle: str, secret: str) -> str:
        val = _validate_secret_text(secret)
        self._items[scoped_target_name(self.namespace, handle)] = val
        return secret_fingerprint(val)

    def get(self, handle: str) -> str | None:
        return self._items.get(scoped_target_name(self.namespace, handle))

    def delete(self, handle: str) -> bool:
        return self._items.pop(scoped_target_name(self.namespace, handle), None) is not None

    def has(self, handle: str) -> bool:
        return scoped_target_name(self.namespace, handle) in self._items

    def fingerprint(self, handle: str) -> str | None:
        val = self.get(handle)
        return secret_fingerprint(val) if val is not None else None


def _xor_keystream(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    out, offset = bytearray(len(data)), 0
    for counter in range((len(data) + 31) // 32):
        block = hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        chunk = data[offset: offset + 32]
        for idx, b in enumerate(chunk):
            out[offset + idx] = b ^ block[idx]
        offset += len(chunk)
    return bytes(out)


def _derive_keys(master_key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    dk = hashlib.pbkdf2_hmac("sha256", master_key, salt, 100_000, dklen=64)
    return dk[:32], dk[32:]


class EncryptedFileKeystore:
    """Portable pure-stdlib authenticated (PBKDF2 + Encrypt-then-MAC) file keystore."""

    def __init__(self, path: str | Path, master_key: str | bytes, *, namespace: str = "default") -> None:
        scoped_target_name(namespace, "probe")
        raw_master = master_key.encode("utf-8") if isinstance(master_key, str) else bytes(master_key)
        if len(raw_master) < 16:
            raise KeystoreError("master_key must be at least 16 bytes")
        self._path, self._master, self.namespace = Path(path), raw_master, namespace

    def __repr__(self) -> str:
        return f"EncryptedFileKeystore(path={str(self._path)!r}, namespace={self.namespace!r})"

    def _load_records(self) -> dict[str, dict[str, str]]:
        if not self._path.is_file():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return dict(data.get("records", {})) if isinstance(data, dict) else {}

    def _save_records(self, records: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"schema": "accountable-surface-keystore/1", "records": records}, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def put(self, handle: str, secret: str) -> str:
        target, val = scoped_target_name(self.namespace, handle), _validate_secret_text(secret)
        salt, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
        enc_key, mac_key = _derive_keys(self._master, salt)
        ct = _xor_keystream(enc_key, nonce, val.encode("utf-8"))
        tag = hmac.new(mac_key, salt + nonce + target.encode("utf-8") + ct, hashlib.sha256).digest()
        records = self._load_records()
        records[target] = {k: base64.b64encode(v).decode("ascii") for k, v in (("salt", salt), ("nonce", nonce), ("ct", ct), ("tag", tag))}
        self._save_records(records)
        return secret_fingerprint(val)

    def get(self, handle: str) -> str | None:
        target = scoped_target_name(self.namespace, handle)
        rec = self._load_records().get(target)
        if rec is None:
            return None
        salt, nonce, ct, tag = (base64.b64decode(rec[k]) for k in ("salt", "nonce", "ct", "tag"))
        enc_key, mac_key = _derive_keys(self._master, salt)
        expected = hmac.new(mac_key, salt + nonce + target.encode("utf-8") + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, tag):
            raise KeystoreTamperError(f"keystore MAC verification failed for handle: {handle}")
        return _xor_keystream(enc_key, nonce, ct).decode("utf-8")

    def delete(self, handle: str) -> bool:
        target, records = scoped_target_name(self.namespace, handle), self._load_records()
        if target not in records:
            return False
        del records[target]
        self._save_records(records)
        return True

    def has(self, handle: str) -> bool:
        return scoped_target_name(self.namespace, handle) in self._load_records()

    def fingerprint(self, handle: str) -> str | None:
        val = self.get(handle)
        return secret_fingerprint(val) if val is not None else None


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class _CredentialW(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p), ("LastWritten", ctypes.c_uint64), ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32), ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p), ("UserName", ctypes.c_wchar_p),
    ]


def _make_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_ubyte]]:
    buf = (ctypes.c_ubyte * max(len(data), 1))()
    if data:
        ctypes.memmove(buf, data, len(data))
    return _DataBlob(len(data), buf), buf


def _dpapi_call(protect: bool, data: bytes, entropy: bytes | None) -> bytes:
    if sys.platform != "win32":
        raise KeystoreUnavailableError("Win32 DPAPI is only available on Windows")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    in_blob, _b1 = _make_blob(data)
    ent_blob, _b2 = _make_blob(entropy) if entropy else (None, None)
    out_blob = _DataBlob()
    ent_ref = ctypes.byref(ent_blob) if ent_blob is not None else None
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(in_blob), "accountable-surface", ent_ref, None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, ent_ref, None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
    if not ok:
        raise (KeystoreError("Win32 CryptProtectData failed") if protect else KeystoreTamperError("Win32 CryptUnprotectData failed"))
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def dpapi_protect(data: bytes, *, entropy: bytes | None = None) -> bytes:
    """Protect bytes using documented Win32 crypt32.dll CryptProtectData (DPAPI)."""
    return _dpapi_call(True, data, entropy)


def dpapi_unprotect(blob: bytes, *, entropy: bytes | None = None) -> bytes:
    """Unprotect DPAPI bytes using documented Win32 crypt32.dll CryptUnprotectData."""
    return _dpapi_call(False, blob, entropy)


class Win32CredentialKeystore:
    """Win32 Credential Manager + DPAPI keystore strictly scoped under accountable-surface:."""

    def __init__(self, namespace: str = "default", *, wrap_dpapi: bool = True, persist: int = _CRED_PERSIST_SESSION) -> None:
        if sys.platform != "win32":
            raise KeystoreUnavailableError("Win32CredentialKeystore is only available on Windows")
        scoped_target_name(namespace, "probe")
        self.namespace, self.wrap_dpapi, self.persist, self._adv = namespace, bool(wrap_dpapi), int(persist), ctypes.windll.advapi32

    def __repr__(self) -> str:
        return f"Win32CredentialKeystore(namespace={self.namespace!r}, wrap_dpapi={self.wrap_dpapi})"

    def read_scoped_target(self, target: str) -> str | None:
        """Read a raw target name only if it passes validate_scoped_target fail-closed."""
        safe_target, pcred = validate_scoped_target(target), ctypes.POINTER(_CredentialW)()
        if not self._adv.CredReadW(ctypes.c_wchar_p(safe_target), _CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
            return None
        try:
            raw = ctypes.string_at(pcred.contents.CredentialBlob, pcred.contents.CredentialBlobSize)
            return (dpapi_unprotect(raw, entropy=safe_target.encode("utf-8")) if self.wrap_dpapi else raw).decode("utf-8")
        finally:
            self._adv.CredFree(pcred)

    def put(self, handle: str, secret: str) -> str:
        target, val = scoped_target_name(self.namespace, handle), _validate_secret_text(secret)
        raw = dpapi_protect(val.encode("utf-8"), entropy=target.encode("utf-8")) if self.wrap_dpapi else val.encode("utf-8")
        buf = (ctypes.c_ubyte * max(len(raw), 1))()
        ctypes.memmove(buf, raw, len(raw))
        cred = _CredentialW(Type=_CRED_TYPE_GENERIC, TargetName=target, Comment="accountable-surface scoped credential", CredentialBlobSize=len(raw), CredentialBlob=buf, Persist=self.persist, UserName=os.environ.get("USERNAME", "operator"))
        if not self._adv.CredWriteW(ctypes.byref(cred), 0):
            raise KeystoreError(f"Win32 CredWriteW failed for handle: {handle}")
        return secret_fingerprint(val)

    def get(self, handle: str) -> str | None:
        return self.read_scoped_target(scoped_target_name(self.namespace, handle))

    def delete(self, handle: str) -> bool:
        return bool(self._adv.CredDeleteW(ctypes.c_wchar_p(scoped_target_name(self.namespace, handle)), _CRED_TYPE_GENERIC, 0))

    def has(self, handle: str) -> bool:
        return self.get(handle) is not None

    def fingerprint(self, handle: str) -> str | None:
        val = self.get(handle)
        return secret_fingerprint(val) if val is not None else None
