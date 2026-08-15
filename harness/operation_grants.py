"""Durable exact-scope, one-use grants and stable local owner identity."""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib, os, re, secrets
from pathlib import Path
from typing import Callable
from uuid import uuid4
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN
OWNER_FILENAME, GRANT_SCHEMA = "owner.ref", "flywheel.operation-grant/v1"
OWNER_REF_PATTERN = re.compile(r"owner_[0-9a-f]{32}\Z")
GRANT_REF_PATTERN = re.compile(r"gnt_[0-9a-f]{32}\Z")
_ERRORS = frozenset(("PERMISSION_REQUIRED", "PERMISSION_DENIED", "APPROVAL_EXPIRED"))
class GrantError(RuntimeError):
    """One fixed non-echoing permission failure."""

    def __init__(self, code: str) -> None:
        if code not in _ERRORS:
            raise ValueError("grant error code is invalid")
        self.code = code
        super().__init__(code)
@dataclass(frozen=True)
class GrantRequest:
    owner_ref: str
    journey_ref: str | None
    expected_event_head: str | None
    operation_sha256: str
    tool: str
    arguments_sha256: str
    scopes: tuple[str, ...]
    data_refs: tuple[str, ...]
    expires_at: str | None
    nonce: str
def _parse_time(value: object) -> datetime:
    if type(value) is not str or not value:
        raise ValueError("timestamp is invalid")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)
def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def _validate_owner_ref(value: object) -> str:
    if type(value) is not str or OWNER_REF_PATTERN.fullmatch(value) is None:
        raise ValueError("owner_ref is invalid")
    return value
def _read_owner_ref(path: Path) -> str:
    try:
        value = path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise ValueError("owner.ref is invalid") from exc
    return _validate_owner_ref(value)
def _windows_owner_only(path: Path, *, directory: bool) -> None:
    import ctypes; from ctypes import wintypes
    advapi = ctypes.WinDLL("advapi32", use_last_error=True); kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
    convert.restype = wintypes.BOOL
    render = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    render.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                       ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p)
    render.restype = wintypes.BOOL
    set_security = advapi.SetFileSecurityW
    set_security.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p)
    set_security.restype = wintypes.BOOL
    get_security = advapi.GetFileSecurityW
    get_security.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
                             wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    get_security.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    descriptor, expected_text = ctypes.c_void_p(), wintypes.LPWSTR()
    flags = "OICI" if directory else ""; sddl = f"D:P(A;{flags};FA;;;OW)"
    if not convert(sddl, 1, ctypes.byref(descriptor), None): raise OSError("security descriptor conversion failed")
    try:
        if not render(descriptor, 1, 4, ctypes.byref(expected_text), None): raise OSError("security descriptor rendering failed")
        if not set_security(str(path), 0x80000004, descriptor): raise OSError("security descriptor application failed")
        needed = wintypes.DWORD(); get_security(str(path), 4, None, 0, ctypes.byref(needed))
        if not needed.value: raise OSError("security descriptor verification failed")
        actual_descriptor = ctypes.create_string_buffer(needed.value)
        if not get_security(str(path), 4, actual_descriptor, needed, ctypes.byref(needed)): raise OSError("security descriptor verification failed")
        actual_text = wintypes.LPWSTR()
        if not render(actual_descriptor, 1, 4, ctypes.byref(actual_text), None): raise OSError("security descriptor verification failed")
        try:
            if actual_text.value != expected_text.value: raise OSError("security descriptor verification failed")
        finally:
            kernel.LocalFree(actual_text)
    finally:
        if expected_text:
            kernel.LocalFree(expected_text)
        kernel.LocalFree(descriptor)
def _secure_owner_only(path: Path, *, directory: bool) -> None:
    try:
        if os.name == "nt":
            _windows_owner_only(path, directory=directory)
            return
        expected = 0o700 if directory else 0o600
        path.chmod(expected)
        if path.stat().st_mode & 0o777 != expected:
            raise OSError("owner-only mode verification failed")
    except (OSError, TypeError, ValueError):
        raise PermissionError("OWNER_STORAGE_UNAVAILABLE") from None
def load_or_create_owner_ref(home: Path) -> str:
    """Load one token-independent owner identity, creating it with private mode."""
    directory = Path(home)
    directory.mkdir(parents=True, exist_ok=True)
    _secure_owner_only(directory, directory=True)
    path = directory / OWNER_FILENAME
    if path.exists():
        _secure_owner_only(path, directory=False)
        return _read_owner_ref(path)
    owner_ref = f"owner_{secrets.token_hex(16)}"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _secure_owner_only(path, directory=False)
        return _read_owner_ref(path)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            _secure_owner_only(path, directory=False)
            stream.write(owner_ref.encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        fsync_directory(directory)
        return owner_ref
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
class GrantStore:
    """Filesystem grant store containing only request/ref digests and state."""
    def __init__(self, state_root: Path, *, clock: Callable[[], str],
                 lock_timeout_s: float = 2.0) -> None:
        self.state_root, self.clock, self.lock_timeout_s = Path(state_root), clock, lock_timeout_s
    def issue(self, request: GrantRequest, *, approved: bool) -> dict:
        if approved is not True: raise GrantError("PERMISSION_DENIED")
        try:
            effective = self._effective_request(request)
            owner_dir = self._prepare_owner_dir(effective.owner_ref)
            with ExclusiveJourneyLock.acquire(owner_dir / ".lock", self.lock_timeout_s):
                grant_ref = f"gnt_{secrets.token_hex(16)}"
                path = self._grant_path(owner_dir, grant_ref)
                while path.exists():
                    grant_ref = f"gnt_{secrets.token_hex(16)}"
                    path = self._grant_path(owner_dir, grant_ref)
                record = self._record(grant_ref, effective)
                self._replace(path, record)
                self._sync(owner_dir)
            return {"grant_ref": grant_ref, "expires_at": effective.expires_at,
                    "consumed": False}
        except GrantError:
            raise
        except (JourneyLockBusy, OSError, TypeError, ValueError):
            raise GrantError("PERMISSION_DENIED") from None
    def issue_exact(self, grant_ref: str, request: GrantRequest, *,
                    approved: bool) -> dict:
        """Idempotently issue one trusted server-planned exact grant ref."""
        if approved is not True: raise GrantError("PERMISSION_DENIED")
        try:
            if type(grant_ref) is not str or GRANT_REF_PATTERN.fullmatch(grant_ref) is None:
                raise ValueError("grant_ref is invalid")
            effective = self._effective_request(request)
            owner_dir = self._prepare_owner_dir(effective.owner_ref)
            with ExclusiveJourneyLock.acquire(owner_dir / ".lock", self.lock_timeout_s):
                path = self._grant_path(owner_dir, grant_ref)
                if path.exists():
                    record = self._read_record(path, grant_ref)
                    if record["request_sha256"] != self._request_sha(effective):
                        raise GrantError("PERMISSION_DENIED")
                else:
                    record = self._record(grant_ref, effective)
                    self._replace(path, record); self._sync(owner_dir)
            return {"grant_ref": grant_ref, "expires_at": record["expires_at"],
                    "consumed": record["consumed"]}
        except GrantError: raise
        except (JourneyLockBusy, OSError, TypeError, ValueError):
            raise GrantError("PERMISSION_DENIED") from None
    def consume(self, grant_ref: str, request: GrantRequest, *, now: str) -> dict:
        try:
            self._validate_request(request, allow_default_expiry=False)
            owner_dir = self._owner_dir(request.owner_ref)
            if not owner_dir.is_dir():
                raise GrantError("PERMISSION_REQUIRED")
            _secure_owner_only(owner_dir.parent, directory=True)
            _secure_owner_only(owner_dir, directory=True)
            path = self._grant_path(owner_dir, grant_ref)
            if not path.exists():
                raise GrantError("PERMISSION_REQUIRED")
            _secure_owner_only(path, directory=False)
            with ExclusiveJourneyLock.acquire(owner_dir / ".lock", self.lock_timeout_s):
                record = self._read_record(path, grant_ref)
                if record["request_sha256"] != self._request_sha(request):
                    raise GrantError("PERMISSION_DENIED")
                if record["consumed"] or _parse_time(now) >= _parse_time(record["expires_at"]):
                    raise GrantError("APPROVAL_EXPIRED")
                record["consumed"], record["consumed_at"] = True, now
                self._replace(path, record)
                self._sync(owner_dir)
            return {"grant_ref": grant_ref, "consumed": True, "consumed_at": now}
        except GrantError:
            raise
        except (JourneyLockBusy, OSError, TypeError, ValueError):
            raise GrantError("PERMISSION_DENIED") from None
    def _effective_request(self, request: GrantRequest) -> GrantRequest:
        self._validate_request(request, allow_default_expiry=True)
        now = _parse_time(self.clock())
        expiry = _parse_time(request.expires_at) if request.expires_at else now + timedelta(seconds=120)
        if expiry <= now or expiry - now > timedelta(seconds=300):
            raise GrantError("PERMISSION_DENIED")
        effective = replace(request, expires_at=request.expires_at or _utc_text(expiry))
        self._validate_request(effective, allow_default_expiry=False)
        return effective
    @staticmethod
    def _validate_request(request: GrantRequest, *, allow_default_expiry: bool) -> None:
        if not isinstance(request, GrantRequest):
            raise ValueError("request is invalid")
        _validate_owner_ref(request.owner_ref)
        for value in (request.operation_sha256, request.arguments_sha256):
            if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError("digest is invalid")
        if type(request.tool) is not str or not request.tool:
            raise ValueError("tool is invalid")
        creating = request.tool == "journey.create"
        if creating != (request.journey_ref is None and request.expected_event_head is None):
            raise ValueError("grant selector is invalid")
        if not creating:
            if (type(request.journey_ref) is not str
                    or JOURNEY_REF_PATTERN.fullmatch(request.journey_ref) is None
                    or type(request.expected_event_head) is not str
                    or SHA256_PATTERN.fullmatch(request.expected_event_head) is None):
                raise ValueError("grant selector is invalid")
        if type(request.scopes) is not tuple or not all(type(item) is str for item in request.scopes):
            raise ValueError("scopes are invalid")
        if type(request.data_refs) is not tuple or not all(type(item) is str for item in request.data_refs):
            raise ValueError("data_refs are invalid")
        if type(request.nonce) is not str or not request.nonce:
            raise ValueError("nonce is invalid")
        if request.expires_at is None and allow_default_expiry:
            return
        _parse_time(request.expires_at)
    @staticmethod
    def _request_sha(request: GrantRequest) -> str:
        value = asdict(request)
        value["scopes"], value["data_refs"] = list(request.scopes), list(request.data_refs)
        return canonical_sha256(value)
    def _owner_dir(self, owner_ref: str) -> Path:
        return self.state_root / "grants" / _validate_owner_ref(owner_ref)
    def _prepare_owner_dir(self, owner_ref: str) -> Path:
        root = self.state_root / "grants"
        root.mkdir(parents=True, exist_ok=True)
        _secure_owner_only(root, directory=True)
        owner_dir = self._owner_dir(owner_ref)
        owner_dir.mkdir(exist_ok=True)
        _secure_owner_only(owner_dir, directory=True)
        return owner_dir
    @staticmethod
    def _grant_path(owner_dir: Path, grant_ref: str) -> Path:
        if type(grant_ref) is not str or GRANT_REF_PATTERN.fullmatch(grant_ref) is None:
            return owner_dir / f"{hashlib.sha256(str(grant_ref).encode()).hexdigest()}.json"
        return owner_dir / f"{hashlib.sha256(grant_ref.encode('ascii')).hexdigest()}.json"
    def _record(self, grant_ref: str, request: GrantRequest) -> dict:
        return {
            "schema": GRANT_SCHEMA, "grant_sha256": canonical_sha256(grant_ref),
            "request_sha256": self._request_sha(request), "expires_at": request.expires_at,
            "consumed": False, "consumed_at": None,
        }
    def _read_record(self, path: Path, grant_ref: str) -> dict:
        value = strict_load_json(path.read_bytes())
        keys = {"schema", "grant_sha256", "request_sha256", "expires_at", "consumed", "consumed_at"}
        if (set(value) != keys or value.get("schema") != GRANT_SCHEMA
                or value.get("grant_sha256") != canonical_sha256(grant_ref)
                or type(value.get("consumed")) is not bool
                or value.get("consumed_at") is not None and type(value["consumed_at"]) is not str):
            raise ValueError("grant record is invalid")
        return value
    @staticmethod
    def _replace(path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                _secure_owner_only(temporary, directory=False)
                stream.write(canonical_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            _secure_owner_only(path, directory=False)
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    def _sync(self, owner_dir: Path) -> None:
        for path in (owner_dir, owner_dir.parent, self.state_root):
            fsync_directory(path)
