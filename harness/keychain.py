"""keychain.py -- provider secrets in the OS credential store, never on disk.

Windows Credential Manager over ctypes (zero deps): secrets are written as
generic credentials under `flywheel/<ENV_NAME>`, read at call time, and
surfaced everywhere else as presence booleans only. Resolution order is the
environment first (explicit wins), then the keychain. On platforms without
a supported store, every call degrades to a named no -- the environment
path keeps working and nothing pretends."""
from __future__ import annotations

import os
import sys

_PREFIX = "flywheel/"
_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    _PCREDENTIAL = ctypes.POINTER(_CREDENTIAL)


def keychain_available() -> bool:
    return _IS_WINDOWS


def keychain_get(name: str) -> "str | None":
    """The stored secret for `name`, or None. Callers must never log it."""
    if not _IS_WINDOWS or not name:
        return None
    pcred = _PCREDENTIAL()
    ok = _advapi32.CredReadW(_PREFIX + name, _CRED_TYPE_GENERIC, 0,
                             ctypes.byref(pcred))
    if not ok:
        return None
    try:
        cred = pcred.contents
        size = cred.CredentialBlobSize
        if not size:
            return None
        raw = ctypes.string_at(cred.CredentialBlob, size)
        return raw.decode("utf-16-le", "replace")
    finally:
        _advapi32.CredFree(pcred)


def keychain_set(name: str, secret: str) -> dict:
    if not name or not secret:
        return {"error": "provide 'name' and a non-empty secret"}
    if not _IS_WINDOWS:
        return {"error": "no supported OS credential store on this platform; "
                         "use the environment variable instead"}
    blob = secret.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    cred = _CREDENTIAL()
    cred.Type = _CRED_TYPE_GENERIC
    cred.TargetName = _PREFIX + name
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = "flywheel"
    if not _advapi32.CredWriteW(ctypes.byref(cred), 0):
        return {"error": f"credential store write failed "
                         f"(code {ctypes.get_last_error()})"}
    return {"stored": name}


def keychain_delete(name: str) -> dict:
    if not _IS_WINDOWS:
        return {"error": "no supported OS credential store on this platform"}
    if not _advapi32.CredDeleteW(_PREFIX + name, _CRED_TYPE_GENERIC, 0):
        return {"error": f"no stored credential named '{name}'"}
    return {"deleted": name}


def resolve_credential(key_env: str) -> str:
    """The credential for a provider: the environment wins, the keychain
    backs it. Returns '' when neither holds it."""
    if not key_env:
        return ""
    return os.environ.get(key_env) or keychain_get(key_env) or ""


def credential_source(key_env: str) -> str:
    """Where the credential would come from: env | keychain | absent.
    Presence only; the value never leaves resolve_credential's callers."""
    if not key_env:
        return "absent"
    if os.environ.get(key_env):
        return "env"
    if keychain_get(key_env):
        return "keychain"
    return "absent"
