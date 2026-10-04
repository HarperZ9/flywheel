"""transport_win.py -- the signer's named pipe on Windows, and who is calling.

One pipe instance, created with an explicit DACL and reused for every client,
so the pipe name never disappears and another process cannot take it over
between clients. ``FILE_FLAG_FIRST_PIPE_INSTANCE`` makes the signer refuse to
start when someone else already owns the name. Remote clients are rejected.

The caller's identity is the SID on the client's token, read by impersonating
the client at identification level and reverting at once. The signer compares
it with its own token's SID: equal is ``same-identity``, different is
``separate-identity``.
"""
from __future__ import annotations

import _winapi
import ctypes
import time
from ctypes import wintypes

from . import wire
from .statement import SAME, SEPARATE, UNATTESTED

# Owner (the signer account) and SYSTEM get full control; authenticated users
# may read and write the pipe, which only lets them ask for attestations.
DEFAULT_SDDL = "D:P(A;;GA;;;SY)(A;;GA;;;OW)(A;;GRGW;;;AU)"

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_adv = ctypes.WinDLL("advapi32", use_last_error=True)
_INVALID = wintypes.HANDLE(-1).value
_PIPE_ACCESS_DUPLEX, _FIRST_INSTANCE = 0x3, 0x00080000
_PIPE_REJECT_REMOTE = 0x8
_ERROR_PIPE_CONNECTED, _ERROR_PIPE_BUSY = 535, 231
# Busy, or the single instance is between two clients (not yet listening).
_RETRY_ERRORS = (_ERROR_PIPE_BUSY, 233, 536)
_ERROR_MORE_DATA = 234
_GENERIC_RW = 0x80000000 | 0x40000000
_TOKEN_QUERY, _TOKEN_USER = 0x0008, 1


class _SA(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL)]


def _sig(lib, name, res, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = res, list(args)


_H, _D, _B, _P = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, ctypes.c_void_p
_sig(_k32, "CreateNamedPipeW", _H, wintypes.LPCWSTR, _D, _D, _D, _D, _D, _D, _P)
_sig(_k32, "ConnectNamedPipe", _B, _H, _P)
_sig(_k32, "DisconnectNamedPipe", _B, _H)
_sig(_k32, "ReadFile", _B, _H, _P, _D, ctypes.POINTER(_D), _P)
_sig(_k32, "WriteFile", _B, _H, ctypes.c_char_p, _D, ctypes.POINTER(_D), _P)
_sig(_k32, "FlushFileBuffers", _B, _H)
_sig(_k32, "CloseHandle", _B, _H)
_sig(_k32, "LocalFree", _P, _P)
_sig(_k32, "GetCurrentThread", _H)
_sig(_k32, "GetCurrentProcess", _H)
_sig(_adv, "OpenProcessToken", _B, _H, _D, ctypes.POINTER(_H))
_sig(_adv, "OpenThreadToken", _B, _H, _D, _B, ctypes.POINTER(_H))
_sig(_adv, "GetTokenInformation", _B, _H, ctypes.c_int, _P, _D, ctypes.POINTER(_D))
_sig(_adv, "ConvertSidToStringSidW", _B, _P, ctypes.POINTER(wintypes.LPWSTR))
_sig(_adv, "ImpersonateNamedPipeClient", _B, _H)
_sig(_adv, "RevertToSelf", _B)
_sig(_adv, "ConvertStringSecurityDescriptorToSecurityDescriptorW", _B,
     wintypes.LPCWSTR, _D, ctypes.POINTER(_P), _P)


def _err(what: str) -> OSError:
    return ctypes.WinError(ctypes.get_last_error(), what)


def _token_sid(token) -> str:
    size = wintypes.DWORD(0)
    _adv.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if not _adv.GetTokenInformation(token, _TOKEN_USER, buf, size, ctypes.byref(size)):
        raise _err("GetTokenInformation")
    sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
    out = wintypes.LPWSTR()
    if not _adv.ConvertSidToStringSidW(ctypes.c_void_p(sid_ptr), ctypes.byref(out)):
        raise _err("ConvertSidToStringSidW")
    try:
        return out.value
    finally:
        _k32.LocalFree(ctypes.cast(out, ctypes.c_void_p))


def own_sid() -> str:
    tok = wintypes.HANDLE()
    if not _adv.OpenProcessToken(_k32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(tok)):
        raise _err("OpenProcessToken")
    try:
        return _token_sid(tok)
    finally:
        _k32.CloseHandle(tok)


def client_sid(pipe) -> str | None:
    """The connected client's SID, or None when it cannot be read."""
    if not _adv.ImpersonateNamedPipeClient(pipe):
        return None
    tok = wintypes.HANDLE()
    try:
        if not _adv.OpenThreadToken(_k32.GetCurrentThread(), _TOKEN_QUERY, True,
                                    ctypes.byref(tok)):
            return None
        try:
            return _token_sid(tok)
        finally:
            _k32.CloseHandle(tok)
    finally:
        _adv.RevertToSelf()


def isolation_for(client: str | None, me: str) -> dict:
    if client is None:
        return {"mode": UNATTESTED, "signer": f"sid:{me}", "client": "unknown",
                "via": "pipe client token unreadable"}
    return {"mode": SEPARATE if client != me else SAME, "signer": f"sid:{me}",
            "client": f"sid:{client}", "via": "named pipe client token"}


def _create_pipe(address: str, sddl: str):
    psd = ctypes.c_void_p()
    if not _adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(psd), None):
        raise _err("ConvertStringSecurityDescriptorToSecurityDescriptorW")
    sa = _SA(ctypes.sizeof(_SA), psd, False)
    h = _k32.CreateNamedPipeW(address, _PIPE_ACCESS_DUPLEX | _FIRST_INSTANCE,
                              _PIPE_REJECT_REMOTE, 1, wire.MAX_FRAME + 4,
                              wire.MAX_FRAME + 4, 0, ctypes.addressof(sa))
    if h is None or h == _INVALID:
        raise _err(f"CreateNamedPipeW {address} (is another process holding it?)")
    return h


def _reader(pipe):
    def read(n: int) -> bytes:
        buf = ctypes.create_string_buffer(n)
        got = wintypes.DWORD(0)
        if not _k32.ReadFile(pipe, buf, n, ctypes.byref(got), None):
            return b""
        return buf.raw[:got.value]
    return read


def _write_all(pipe, data: bytes) -> None:
    done = wintypes.DWORD(0)
    if not _k32.WriteFile(pipe, data, len(data), ctypes.byref(done), None):
        raise _err("WriteFile")
    _k32.FlushFileBuffers(pipe)


def serve(address: str, handle, ready=None, sddl: str = DEFAULT_SDDL) -> None:
    """Serve forever, one client at a time. ``handle(request, isolation)``."""
    me = own_sid()
    pipe = _create_pipe(address, sddl)
    if ready:
        ready()
    while True:
        if not _k32.ConnectNamedPipe(pipe, None) and \
                ctypes.get_last_error() != _ERROR_PIPE_CONNECTED:
            continue
        try:
            req = wire.decode_from(_reader(pipe))
            _write_all(pipe, wire.encode(handle(req, isolation_for(client_sid(pipe), me))))
        except (wire.WireError, OSError):
            pass
        finally:
            _k32.DisconnectNamedPipe(pipe)


def _open_client(address: str, timeout: float):
    """CreateFile on the pipe, waiting while the one instance serves another
    client. ``open()`` would lose the Windows error code that says "busy"."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return _winapi.CreateFile(address, _GENERIC_RW, 0, _winapi.NULL,
                                      _winapi.OPEN_EXISTING, 0, _winapi.NULL)
        except OSError as exc:
            if getattr(exc, "winerror", None) not in _RETRY_ERRORS \
                    or time.monotonic() > deadline:
                raise
            time.sleep(0.002)


def call(address: str, request: dict, timeout: float = 5.0) -> dict:
    h = _open_client(address, timeout)
    try:
        _winapi.WriteFile(h, wire.encode(request))

        def read(n: int) -> bytes:
            data, err = _winapi.ReadFile(h, n)
            return b"" if err not in (0, _ERROR_MORE_DATA) else bytes(data)
        return wire.decode_from(read)
    finally:
        _winapi.CloseHandle(h)
