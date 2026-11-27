"""A TPM-backed, non-exportable ECDSA P-256 key through Windows NCrypt.

The key lives in the Microsoft Platform Crypto Provider, the Windows key
storage provider for the TPM. The module creates the key with export policy
0 (no export), signs SHA-256 digests with it, exports only the public point
and can prove the private half refuses export. It also reads the TPM clock
with TPM2_ReadClock through the TPM Base Services, a read-only command.

Every call here acts on a key this prototype creates under its own name in
the current user's key store. Nothing else on the machine is touched.
"""

from __future__ import annotations

import ctypes
import hashlib
import struct
import sys

if sys.platform == "win32":
    from ctypes import wintypes
else:
    wintypes = None  # type: ignore[assignment]

from ..crypto import P256

PCP = "Microsoft Platform Crypto Provider"
NTE_BAD_KEYSET = 0x80090016
BCRYPT_ECDSA_PUBLIC_P256_MAGIC = 0x31534345


class TpmError(RuntimeError):
    def __init__(self, call: str, status: int) -> None:
        self.call, self.status = call, status & 0xFFFFFFFF
        super().__init__(f"{call} failed with status 0x{self.status:08X}")


def _ncrypt():
    if sys.platform != "win32":
        raise TpmError("platform", 0xFFFFFFFF)
    return ctypes.WinDLL("ncrypt.dll")


def _check(call: str, status: int) -> None:
    if status != 0:
        raise TpmError(call, status)


class TpmKey:
    """A named NCrypt key in the Platform Crypto Provider."""

    alg = P256

    def __init__(self, name: str) -> None:
        self.name = name
        self._nc = _ncrypt()
        self._prov = ctypes.c_size_t()
        self._key = ctypes.c_size_t()
        _check("NCryptOpenStorageProvider",
               self._nc.NCryptOpenStorageProvider(ctypes.byref(self._prov), PCP, 0))
        self.created = self._open_or_create()
        self._pub = self._export_public()

    def _open_or_create(self) -> bool:
        st = self._nc.NCryptOpenKey(self._prov, ctypes.byref(self._key), self.name, 0, 0)
        if st == 0:
            return False
        if st & 0xFFFFFFFF != NTE_BAD_KEYSET:
            raise TpmError("NCryptOpenKey", st)
        _check("NCryptCreatePersistedKey", self._nc.NCryptCreatePersistedKey(
            self._prov, ctypes.byref(self._key), "ECDSA_P256", self.name, 0, 0))
        policy = wintypes.DWORD(0)
        _check("NCryptSetProperty(Export Policy)", self._nc.NCryptSetProperty(
            self._key, "Export Policy", ctypes.byref(policy), 4, 0))
        _check("NCryptFinalizeKey", self._nc.NCryptFinalizeKey(self._key, 0))
        return True

    def _export(self, blob_type: str) -> bytes:
        size = wintypes.DWORD()
        _check(f"NCryptExportKey({blob_type}) size", self._nc.NCryptExportKey(
            self._key, 0, blob_type, None, None, 0, ctypes.byref(size), 0))
        buf = (ctypes.c_ubyte * size.value)()
        _check(f"NCryptExportKey({blob_type})", self._nc.NCryptExportKey(
            self._key, 0, blob_type, None, buf, size, ctypes.byref(size), 0))
        return bytes(buf[: size.value])

    def _export_public(self) -> bytes:
        blob = self._export("ECCPUBLICBLOB")
        magic, cb = struct.unpack("<II", blob[:8])
        if magic != BCRYPT_ECDSA_PUBLIC_P256_MAGIC or cb != 32:
            raise TpmError("unexpected public blob", magic)
        return b"\x04" + blob[8:8 + 2 * cb]

    def private_export_refused(self) -> str:
        """Try to export the private key. Returns the refusal status code."""
        try:
            self._export("ECCPRIVATEBLOB")
        except TpmError as exc:
            return f"0x{exc.status:08X}"
        return "EXPORTED"

    def dword_property(self, name: str, provider: bool = False) -> int | None:
        handle = self._prov if provider else self._key
        out, size = wintypes.DWORD(), wintypes.DWORD()
        st = self._nc.NCryptGetProperty(handle, name, ctypes.byref(out), 4,
                                        ctypes.byref(size), 0)
        return out.value if st == 0 else None

    def public_hex(self) -> str:
        return self._pub.hex()

    def sign(self, message: bytes) -> bytes:
        digest = hashlib.sha256(message).digest()
        sig = (ctypes.c_ubyte * 64)()
        size = wintypes.DWORD()
        hbuf = (ctypes.c_ubyte * 32).from_buffer_copy(digest)
        _check("NCryptSignHash", self._nc.NCryptSignHash(
            self._key, None, hbuf, 32, sig, 64, ctypes.byref(size), 0))
        return bytes(sig[: size.value])

    def delete(self) -> None:
        if self._key.value:
            _check("NCryptDeleteKey", self._nc.NCryptDeleteKey(self._key, 0))
            self._key = ctypes.c_size_t()
        self.close()

    def close(self) -> None:
        if self._key.value:
            self._nc.NCryptFreeObject(self._key)
            self._key = ctypes.c_size_t()
        if self._prov.value:
            self._nc.NCryptFreeObject(self._prov)
            self._prov = ctypes.c_size_t()


class TpmClock:
    """TPM2_ReadClock through TPM Base Services (read-only)."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise TpmError("platform", 0xFFFFFFFF)
        self._tbs = ctypes.WinDLL("tbs.dll")

        class _Params(ctypes.Structure):
            _fields_ = [("version", wintypes.UINT), ("flags", wintypes.UINT)]

        params = _Params(2, 1 << 2)  # TBS_CONTEXT_VERSION_TWO, include TPM 2.0
        self._ctx = ctypes.c_void_p()
        _check("Tbsi_Context_Create",
               self._tbs.Tbsi_Context_Create(ctypes.byref(params), ctypes.byref(self._ctx)))

    def read(self) -> dict:
        cmd = struct.pack(">HII", 0x8001, 10, 0x00000181)  # TPM2_ReadClock
        out = (ctypes.c_ubyte * 64)()
        size = wintypes.UINT(64)
        _check("Tbsip_Submit_Command", self._tbs.Tbsip_Submit_Command(
            self._ctx, 0, 200, (ctypes.c_ubyte * len(cmd)).from_buffer_copy(cmd),
            len(cmd), out, ctypes.byref(size)))
        resp = bytes(out[: size.value])
        _tag, _len, rc = struct.unpack(">HII", resp[:10])
        if rc != 0:
            raise TpmError("TPM2_ReadClock", rc)
        t, clock, resets, restarts, safe = struct.unpack(">QQIIB", resp[10:35])
        return {"time_ms": t, "clock_ms": clock, "reset_count": resets,
                "restart_count": restarts, "safe": bool(safe)}

    def close(self) -> None:
        if self._ctx.value:
            self._tbs.Tbsip_Context_Close(self._ctx)
            self._ctx = ctypes.c_void_p()
