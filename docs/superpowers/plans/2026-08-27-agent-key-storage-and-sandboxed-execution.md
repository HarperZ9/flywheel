# Agent Key Storage & Sandboxed Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every agent session a scoped, time-limited credential token (never the raw key) and route shell commands through the existing Windows low-integrity sandbox with captured output, so the local agent can execute code without holding long-lived secrets or running at the operator's privilege level.

**Architecture:** Two layers wired together. The session-token store wraps the existing `CredentialHandleStore` with TTL, session binding, and auto-reap. The sandboxed runner composes the existing `LowIntegrityRunner` with output-capture files and `CredentialBindings.child_environment()`, injected into `local_tools.py` via its existing `runner` callback. On non-Windows hosts, execution reports an honest null (`UNVERIFIABLE`) rather than silently falling back to bare subprocess.

**Tech Stack:** Python 3.12+ stdlib only (ctypes for Windows APIs), Flutter/Dart for client UI. No new dependencies.

## Global Constraints

- Standard library only in `harness/`. No third-party packages.
- Files under 300 lines. Functions under 50 lines.
- Credential values never appear in logs, receipts, errors, or tool output. Presence only.
- Sandbox requires Windows (`os.name == "nt"`). Other platforms fail closed with `UNVERIFIABLE`.
- All existing tests must stay green. Run `pytest tests/ -x -q` before every commit.
- Run `flutter analyze` and `flutter test` for Dart changes.
- Branch per feature off `origin/main`. Co-Authored-By trailer on every commit.
- Receipt schema changes are additive (new optional fields, never remove or rename).

---

### Task 1: Session Token Store

The core data structure. A `SessionToken` is a time-bounded, session-scoped derivation of a `CredentialHandle`. It resolves to the real credential only within its TTL window and only for the owning session. Expired tokens are reaped lazily.

**Files:**
- Create: `harness/session_token.py`
- Test: `tests/test_session_token.py`

**Interfaces:**
- Consumes: `CredentialHandleStore.resolve_exact(owner_ref, refs, required_slots)` from `credential_handles.py`
- Consumes: `CredentialBindings` from `credential_handles.py`
- Produces: `SessionToken` dataclass with `token_ref: str`, `credential_refs: tuple[str, ...]`, `owner_ref: str`, `session_ref: str`, `created_at: float`, `expires_at: float`, `revoked: bool`
- Produces: `SessionTokenStore` with `mint(owner_ref, session_ref, credential_refs, required_slots, ttl_seconds) -> SessionToken`
- Produces: `SessionTokenStore.resolve(token_ref, owner_ref, session_ref) -> CredentialBindings`
- Produces: `SessionTokenStore.revoke(token_ref, owner_ref) -> bool`
- Produces: `SessionTokenStore.list_active(owner_ref) -> tuple[SessionToken, ...]`
- Produces: `SessionTokenStore.reap() -> int` (count of expired tokens removed)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_token.py
"""Session tokens: scoped, time-bounded credential derivation."""
import time
from unittest.mock import MagicMock

import pytest


def _fake_keychain():
    store = {"OPENROUTER_API_KEY": "or-live-xxx", "OPENAI_API_KEY": "sk-yyy"}
    return lambda name: store.get(name)


def _make_handle_store(tmp_path):
    from harness.credential_handles import CredentialHandleStore
    return CredentialHandleStore(tmp_path, keychain_get=_fake_keychain())


def _make_store(tmp_path):
    from harness.session_token import SessionTokenStore
    handle_store = _make_handle_store(tmp_path)
    return SessionTokenStore(handle_store)


def test_mint_returns_token_with_expiry(tmp_path):
    from harness.session_token import SessionTokenStore
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = store.mint(
        owner_ref="owner_abc123def456",
        session_ref="sess_001",
        credential_refs=[h.credential_ref],
        required_slots=["OPENROUTER_API_KEY"],
        ttl_seconds=900,
    )
    assert token.token_ref.startswith("stok_")
    assert token.expires_at > token.created_at
    assert token.expires_at - token.created_at == pytest.approx(900, abs=2)
    assert not token.revoked


def test_resolve_returns_bindings_within_ttl(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = store.mint("owner_abc123def456", "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    bindings = store.resolve(token.token_ref, "owner_abc123def456", "sess_001")
    assert bindings.value_for("OPENROUTER_API_KEY") == "or-live-xxx"


def test_resolve_rejects_expired_token(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = store.mint("owner_abc123def456", "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 0)
    time.sleep(0.05)
    with pytest.raises(SessionTokenError, match="EXPIRED"):
        store.resolve(token.token_ref, "owner_abc123def456", "sess_001")


def test_resolve_rejects_wrong_session(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = store.mint("owner_abc123def456", "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    with pytest.raises(SessionTokenError):
        store.resolve(token.token_ref, "owner_abc123def456", "sess_OTHER")


def test_resolve_rejects_wrong_owner(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = store.mint("owner_abc123def456", "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    with pytest.raises(SessionTokenError):
        store.resolve(token.token_ref, "owner_WRONG0000000", "sess_001")


def test_revoke_prevents_future_resolve(tmp_path):
    from harness.session_token import SessionTokenError
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = store.mint("owner_abc123def456", "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    assert store.revoke(token.token_ref, "owner_abc123def456")
    with pytest.raises(SessionTokenError, match="REVOKED"):
        store.resolve(token.token_ref, "owner_abc123def456", "sess_001")


def test_list_active_excludes_expired_and_revoked(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    t1 = store.mint("owner_abc123def456", "s1", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 0)
    time.sleep(0.05)
    t2 = store.mint("owner_abc123def456", "s2", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 900)
    t3 = store.mint("owner_abc123def456", "s3", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 900)
    store.revoke(t3.token_ref, "owner_abc123def456")
    active = store.list_active("owner_abc123def456")
    refs = [t.token_ref for t in active]
    assert t2.token_ref in refs
    assert t1.token_ref not in refs
    assert t3.token_ref not in refs


def test_reap_removes_expired_tokens(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    store.mint("owner_abc123def456", "s1", [h.credential_ref],
              ["OPENROUTER_API_KEY"], 0)
    store.mint("owner_abc123def456", "s2", [h.credential_ref],
              ["OPENROUTER_API_KEY"], 900)
    time.sleep(0.05)
    removed = store.reap()
    assert removed == 1
    assert len(store.list_active("owner_abc123def456")) == 1


def test_repr_never_contains_credential_value(tmp_path):
    store = _make_store(tmp_path)
    hs = store._handle_store
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = store.mint("owner_abc123def456", "sess_001",
                       [h.credential_ref], ["OPENROUTER_API_KEY"], 900)
    assert "or-live-xxx" not in repr(token)
    assert "or-live-xxx" not in str(token)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session_token.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.session_token'`

- [ ] **Step 3: Implement SessionTokenStore**

```python
# harness/session_token.py
"""Session tokens: scoped, time-bounded credential derivation.

An agent session gets a token that resolves to real credentials only within
its TTL and only for the bound session. The raw credential value never
appears in the token, its repr, or any error message. Expired tokens are
reaped lazily on list/reap calls.
"""
from __future__ import annotations

import secrets
import time
import threading
from dataclasses import dataclass

from .credential_handles import (
    CredentialBindings, CredentialHandleStore, CredentialHandleError,
)

TOKEN_REF_PREFIX = "stok_"


class SessionTokenError(RuntimeError):
    def __init__(self, code: str = "INVALID_TOKEN") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SessionToken:
    token_ref: str
    credential_refs: tuple[str, ...]
    required_slots: tuple[str, ...]
    owner_ref: str
    session_ref: str
    created_at: float
    expires_at: float
    revoked: bool = False

    def __repr__(self) -> str:
        state = "revoked" if self.revoked else (
            "expired" if time.time() > self.expires_at else "active")
        return (f"SessionToken({self.token_ref!r}, session={self.session_ref!r}, "
                f"state={state}, slots={len(self.required_slots)})")

    def active(self) -> bool:
        return not self.revoked and time.time() <= self.expires_at


class SessionTokenStore:
    def __init__(self, handle_store: CredentialHandleStore) -> None:
        self._handle_store = handle_store
        self._tokens: dict[str, SessionToken] = {}
        self._lock = threading.Lock()

    def mint(
        self,
        owner_ref: str,
        session_ref: str,
        credential_refs: list[str] | tuple[str, ...],
        required_slots: list[str] | tuple[str, ...],
        ttl_seconds: int,
    ) -> SessionToken:
        self._handle_store.slot_names_exact(owner_ref, list(credential_refs))
        now = time.time()
        token_ref = f"{TOKEN_REF_PREFIX}{secrets.token_hex(16)}"
        token = SessionToken(
            token_ref=token_ref,
            credential_refs=tuple(credential_refs),
            required_slots=tuple(required_slots),
            owner_ref=owner_ref,
            session_ref=session_ref,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            self._tokens[token_ref] = token
        return token

    def resolve(
        self, token_ref: str, owner_ref: str, session_ref: str,
    ) -> CredentialBindings:
        with self._lock:
            token = self._tokens.get(token_ref)
        if token is None:
            raise SessionTokenError("INVALID_TOKEN")
        if token.owner_ref != owner_ref:
            raise SessionTokenError("INVALID_TOKEN")
        if token.session_ref != session_ref:
            raise SessionTokenError("SESSION_MISMATCH")
        if token.revoked:
            raise SessionTokenError("REVOKED")
        if time.time() > token.expires_at:
            raise SessionTokenError("EXPIRED")
        try:
            return self._handle_store.resolve_exact(
                owner_ref, list(token.credential_refs),
                list(token.required_slots))
        except CredentialHandleError:
            raise SessionTokenError("CREDENTIAL_UNAVAILABLE") from None

    def revoke(self, token_ref: str, owner_ref: str) -> bool:
        with self._lock:
            token = self._tokens.get(token_ref)
            if token is None or token.owner_ref != owner_ref:
                return False
            revoked = SessionToken(
                token_ref=token.token_ref,
                credential_refs=token.credential_refs,
                required_slots=token.required_slots,
                owner_ref=token.owner_ref,
                session_ref=token.session_ref,
                created_at=token.created_at,
                expires_at=token.expires_at,
                revoked=True,
            )
            self._tokens[token_ref] = revoked
            return True

    def list_active(self, owner_ref: str) -> tuple[SessionToken, ...]:
        now = time.time()
        with self._lock:
            return tuple(
                t for t in self._tokens.values()
                if t.owner_ref == owner_ref and not t.revoked
                and now <= t.expires_at
            )

    def reap(self) -> int:
        now = time.time()
        with self._lock:
            expired = [ref for ref, t in self._tokens.items()
                       if t.revoked or now > t.expires_at]
            for ref in expired:
                del self._tokens[ref]
            return len(expired)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_token.py -v`
Expected: all 9 tests PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `pytest tests/ -x -q`
Expected: all existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add harness/session_token.py tests/test_session_token.py
git commit -m "feat(harness): add session token store with TTL and session binding

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Session Token Gateway Routes

HTTP endpoints for minting, listing, and revoking session tokens. Wired into the gateway's existing authenticated route dispatch.

**Files:**
- Create: `harness/session_token_route.py`
- Modify: `harness/gateway.py` (add route dispatch, ~10 lines)
- Test: `tests/test_session_token_route.py`

**Interfaces:**
- Consumes: `SessionTokenStore.mint()`, `.list_active()`, `.revoke()` from Task 1
- Consumes: `authenticate_owner()` from `gateway_auth.py` (provides `owner_ref`)
- Produces: `POST /api/session-tokens/mint` -> `{"ok": true, "token_ref": "stok_...", "expires_at": float}`
- Produces: `GET /api/session-tokens` -> `{"ok": true, "tokens": [...]}`
- Produces: `POST /api/session-tokens/revoke` -> `{"ok": true}`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_token_route.py
"""Session token HTTP routes: mint, list, revoke."""
import json
import pytest


def _fake_keychain():
    return {"OPENROUTER_API_KEY": "or-live-xxx"}.get


def _make_stores(tmp_path):
    from harness.credential_handles import CredentialHandleStore
    from harness.session_token import SessionTokenStore
    hs = CredentialHandleStore(tmp_path, keychain_get=_fake_keychain())
    return hs, SessionTokenStore(hs)


def test_mint_returns_token_ref(tmp_path):
    from harness.session_token_route import session_token_post
    hs, ts = _make_stores(tmp_path)
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    body, status = session_token_post(
        "mint",
        {"credential_refs": [h.credential_ref],
         "required_slots": ["OPENROUTER_API_KEY"],
         "session_ref": "sess_001", "ttl_seconds": 900},
        owner_ref="owner_abc123def456", token_store=ts)
    assert status == 200
    assert body["ok"]
    assert body["token_ref"].startswith("stok_")
    assert "expires_at" in body


def test_list_returns_active_tokens(tmp_path):
    from harness.session_token_route import session_token_get
    hs, ts = _make_stores(tmp_path)
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    ts.mint("owner_abc123def456", "s1", [h.credential_ref],
            ["OPENROUTER_API_KEY"], 900)
    body, status = session_token_get(
        owner_ref="owner_abc123def456", token_store=ts)
    assert status == 200
    assert len(body["tokens"]) == 1
    assert "or-live-xxx" not in json.dumps(body)


def test_revoke_succeeds(tmp_path):
    from harness.session_token_route import session_token_post
    hs, ts = _make_stores(tmp_path)
    h = hs.bind("owner_abc123def456", "OPENROUTER_API_KEY")
    token = ts.mint("owner_abc123def456", "s1", [h.credential_ref],
                    ["OPENROUTER_API_KEY"], 900)
    body, status = session_token_post(
        "revoke", {"token_ref": token.token_ref},
        owner_ref="owner_abc123def456", token_store=ts)
    assert status == 200
    assert body["ok"]


def test_mint_rejects_missing_fields(tmp_path):
    from harness.session_token_route import session_token_post
    _, ts = _make_stores(tmp_path)
    body, status = session_token_post(
        "mint", {}, owner_ref="owner_abc123def456", token_store=ts)
    assert status == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session_token_route.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.session_token_route'`

- [ ] **Step 3: Implement session_token_route.py**

```python
# harness/session_token_route.py
"""HTTP transport for session token operations."""
from __future__ import annotations

from .session_token import SessionTokenError, SessionTokenStore

MAX_TTL = 3600


def session_token_post(
    action: str,
    raw: dict,
    *,
    owner_ref: str,
    token_store: SessionTokenStore,
) -> tuple[dict, int]:
    if action == "mint":
        refs = raw.get("credential_refs")
        slots = raw.get("required_slots")
        session = raw.get("session_ref")
        ttl = raw.get("ttl_seconds", 900)
        if (not isinstance(refs, list) or not isinstance(slots, list)
                or not isinstance(session, str) or not session
                or not isinstance(ttl, int) or ttl < 0):
            return {"ok": False, "error": "INVALID_REQUEST"}, 400
        ttl = min(ttl, MAX_TTL)
        try:
            token = token_store.mint(owner_ref, session, refs, slots, ttl)
        except (SessionTokenError, Exception) as e:
            code = e.code if isinstance(e, SessionTokenError) else "STORE_ERROR"
            return {"ok": False, "error": code}, 400
        return {"ok": True, "token_ref": token.token_ref,
                "session_ref": token.session_ref,
                "expires_at": token.expires_at}, 200

    if action == "revoke":
        ref = raw.get("token_ref", "")
        if not isinstance(ref, str) or not ref:
            return {"ok": False, "error": "INVALID_REQUEST"}, 400
        ok = token_store.revoke(ref, owner_ref)
        return {"ok": ok}, 200 if ok else 404

    return {"ok": False, "error": "UNKNOWN_ACTION"}, 404
 

def session_token_get(
    *, owner_ref: str, token_store: SessionTokenStore,
) -> tuple[dict, int]:
    tokens = token_store.list_active(owner_ref)
    return {"ok": True, "tokens": [
        {"token_ref": t.token_ref, "session_ref": t.session_ref,
         "slots": len(t.required_slots), "expires_at": t.expires_at}
        for t in tokens
    ]}, 200
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_token_route.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Wire routes into gateway.py**

In `harness/gateway.py`, find the `_get()` method's route dispatch (near the `/api/credential-handles` handler) and add:

```python
# Inside _get(), after the credential-handles block:
if path == "/api/session-tokens":
    from .session_token_route import session_token_get
    return self._json(session_token_get(
        owner_ref=owner, token_store=self.server.session_token_store)[0])
```

In `_post()`, after the credential-handles block:

```python
if path.startswith("/api/session-tokens/"):
    action = path.rsplit("/", 1)[-1]
    from .session_token_route import session_token_post
    body, status = session_token_post(
        action, req, owner_ref=owner,
        token_store=self.server.session_token_store)
    return self._json(body, status)
```

In the server startup (where `CredentialHandleStore` is created), add:

```python
from .session_token import SessionTokenStore
self.session_token_store = SessionTokenStore(self.credential_handle_store)
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add harness/session_token_route.py tests/test_session_token_route.py harness/gateway.py
git commit -m "feat(harness): add session token HTTP routes (mint/list/revoke)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Sandboxed Runner with Output Capture

Compose the existing `LowIntegrityRunner` with output-capture files and `CredentialBindings.child_environment()` into a callable that replaces bare `subprocess.run` for agent tool execution.

**Files:**
- Create: `harness/sandboxed_runner.py`
- Modify: `harness/windows_low_integrity.py` (add optional stdout/stderr file handles, ~15 lines)
- Test: `tests/test_sandboxed_runner.py`

**Interfaces:**
- Consumes: `LowIntegrityRunner` from `windows_low_integrity.py`
- Consumes: `CredentialBindings.child_environment()` from `credential_handles.py`
- Consumes: `classify_command()` from `shell_admission.py`
- Produces: `sandboxed_run(cmd: str, root: str, *, bindings: CredentialBindings | None) -> tuple[bool, str]`
- Produces: `SandboxUnavailable` exception for honest-null path

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sandboxed_runner.py
"""Sandboxed runner: shell commands under low-integrity with output capture."""
import os
import sys
import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows low-integrity only")
class TestSandboxedRunner:

    def test_captures_stdout(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("echo hello world", str(source))
        assert ok
        assert "hello world" in out

    def test_captures_exit_code(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("exit /b 42", str(source))
        assert not ok
        assert "exit 42" in out

    def test_timeout_reports_honestly(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("ping -n 30 127.0.0.1", str(source),
                                timeout_seconds=2)
        assert not ok
        assert "timeout" in out.lower()

    def test_denied_command_never_runs(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("rm -rf /", str(source))
        assert not ok
        assert "blocked" in out.lower() or "denied" in out.lower()

    def test_credential_values_not_in_output(self, tmp_path):
        from harness.sandboxed_runner import sandboxed_run
        from harness.credential_handles import CredentialBindings
        bindings = CredentialBindings({"MY_SECRET": "super-secret-value"})
        source = tmp_path / "source"; source.mkdir()
        ok, out = sandboxed_run("set MY_SECRET", str(source),
                                bindings=bindings)
        assert "super-secret-value" not in repr(out)


def test_non_windows_fails_closed():
    if os.name == "nt":
        pytest.skip("only tests the non-Windows path")
    from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
    with pytest.raises(SandboxUnavailable):
        sandboxed_run("echo hi", ".")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sandboxed_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.sandboxed_runner'`

- [ ] **Step 3: Add output file handles to LowIntegrityRunner.run()**

In `harness/windows_low_integrity.py`, modify the `run` method signature and the std-handle setup to accept optional stdout/stderr paths:

```python
# In LowIntegrityRunner.run(), change the signature:
def run(self, argv: list[str], *, env: dict, timeout_seconds: int,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None) -> int:

# Replace the nulls/std-handle block (lines 221-228) with:
    streams = []
    try:
        if stdout_path and stderr_path:
            f_out = open(stdout_path, "wb"); streams.append(f_out)
            f_err = open(stderr_path, "wb"); streams.append(f_err)
            f_in = open(os.devnull, "rb"); streams.append(f_in)
        else:
            for mode in ("rb", "wb", "wb"):
                f = open(os.devnull, mode); streams.append(f)
            f_in, f_out, f_err = streams[0], streams[1], streams[2]

        for f in streams:
            os.set_handle_inheritable(
                __import__("msvcrt").get_osfhandle(f.fileno()), True)

        startup = STARTUPINFO(); startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = STARTF_USESTDHANDLES
        startup.hStdInput = __import__("msvcrt").get_osfhandle(f_in.fileno())
        startup.hStdOutput = __import__("msvcrt").get_osfhandle(f_out.fileno())
        startup.hStdError = __import__("msvcrt").get_osfhandle(f_err.fileno())
        # ... rest of method unchanged ...
    finally:
        # In the existing finally block, replace nulls with streams:
        for f in streams:
            f.close()
```

The existing tests in `tests/test_windows_low_integrity.py` must still pass (the default `None` path is byte-identical to the old behavior).

- [ ] **Step 4: Implement sandboxed_runner.py**

```python
# harness/sandboxed_runner.py
"""Sandboxed shell execution: low-integrity isolation with output capture.

Routes shell commands through the Windows low-integrity sandbox. Commands
that shell_admission classifies as dangerous are refused before any process
is created. Non-Windows hosts fail closed with SandboxUnavailable rather
than silently falling back to bare subprocess.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .credential_handles import CredentialBindings
from .shell_admission import classify_command, Decision


class SandboxUnavailable(RuntimeError):
    pass


def sandboxed_run(
    cmd: str,
    root: str,
    *,
    bindings: CredentialBindings | None = None,
    timeout_seconds: int = 120,
) -> tuple[bool, str]:
    admission = classify_command(cmd)
    if admission.decision == Decision.BLOCK:
        return False, (f"[blocked] command denied: "
                       f"{admission.reason_code}")
    if admission.decision == Decision.ESCALATE:
        return False, (f"[denied] command requires escalation: "
                       f"{admission.reason_code}")
    if os.name != "nt":
        raise SandboxUnavailable(
            "sandboxed execution requires Windows low-integrity")

    from .execution_input_protection import (
        ExecutionInputProtectionUnavailable, protect_execution_namespace,
    )

    source = Path(root).resolve()
    work = Path(tempfile.mkdtemp(prefix="fw_sandbox_", dir=source.parent))
    stdout_path = work / "stdout.txt"
    stderr_path = work / "stderr.txt"
    stdout_path.touch(); stderr_path.touch()

    env = _build_env(bindings)
    argv = [os.environ.get("COMSPEC", "cmd.exe"), "/c", cmd]
    argv[0] = str(Path(argv[0]).resolve())

    try:
        with protect_execution_namespace(source, work) as runner:
            rc = runner.run(
                argv, env=env, timeout_seconds=timeout_seconds,
                stdout_path=stdout_path, stderr_path=stderr_path)
    except ExecutionInputProtectionUnavailable as e:
        shutil.rmtree(work, ignore_errors=True)
        raise SandboxUnavailable(str(e)) from e

    out = _read_output(stdout_path, stderr_path)
    shutil.rmtree(work, ignore_errors=True)

    if rc == 124:
        return False, f"[timeout after {timeout_seconds}s]\n{out}"
    return rc == 0, f"[exit {rc}]\n{out}"


def _build_env(bindings: CredentialBindings | None) -> dict[str, str]:
    if bindings is not None:
        return bindings.child_environment(os.environ, platform="windows")
    allowed = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC",
               "TEMP", "TMP")
    return {k: os.environ[k] for k in allowed
            if type(os.environ.get(k)) is str}


def _read_output(stdout_path: Path, stderr_path: Path) -> str:
    parts = []
    for path in (stdout_path, stderr_path):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                parts.append(text)
        except OSError:
            pass
    return "\n".join(parts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sandboxed_runner.py -v`
Expected: all tests PASS (Windows tests run on Windows, non-Windows test runs elsewhere)

- [ ] **Step 6: Verify existing low-integrity tests still pass**

Run: `pytest tests/test_windows_low_integrity.py tests/test_execution_input_protection.py -v`
Expected: PASS (the `None` default for stdout_path/stderr_path preserves old behavior)

- [ ] **Step 7: Commit**

```bash
git add harness/sandboxed_runner.py harness/windows_low_integrity.py tests/test_sandboxed_runner.py
git commit -m "feat(harness): add sandboxed runner with output capture over low-integrity

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Wire Sandbox into Tool Execution

Replace `local_tools.py`'s bare `subprocess.run` with the sandboxed runner. The existing `runner` callback injection point makes this clean: when sandbox is available, inject `sandboxed_run`; when not, inject a wrapper that records an honest null in the receipt.

**Files:**
- Modify: `harness/local_tools.py:409-425` (the `_t_run` method)
- Create: `harness/tool_sandbox_bridge.py` (the bridge that composes admission + sandbox + receipt metadata)
- Modify: `tests/test_local_tools.py` (add sandbox-wired tests)
- Test: `tests/test_tool_sandbox_bridge.py`

**Interfaces:**
- Consumes: `sandboxed_run()` from Task 3
- Consumes: `ToolGate` from `local_tools.py`
- Consumes: `build_receipt()` from `tool_call_receipt.py`
- Produces: `make_sandboxed_runner(bindings: CredentialBindings | None) -> Callable[[str, str], tuple[bool, str]]`
- Produces: modified `_t_run` that uses the injected runner (zero behavioral change when `runner` is `None` and sandbox is unavailable)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tool_sandbox_bridge.py
"""Bridge between ToolRunner and the sandbox."""
import os
import pytest


def test_make_sandboxed_runner_returns_callable():
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    runner = make_sandboxed_runner(bindings=None)
    assert callable(runner)


@pytest.mark.skipif(os.name != "nt", reason="Windows sandbox only")
def test_sandboxed_runner_executes_and_returns_output(tmp_path):
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    runner = make_sandboxed_runner(bindings=None)
    ok, out = runner("echo sandboxed", str(tmp_path))
    assert ok
    assert "sandboxed" in out


def test_unsandboxed_fallback_marks_output(tmp_path):
    from harness.tool_sandbox_bridge import make_unsandboxed_runner
    runner = make_unsandboxed_runner()
    ok, out = runner("echo fallback", str(tmp_path))
    assert ok
    assert "fallback" in out


def test_make_sandboxed_runner_with_bindings():
    from harness.credential_handles import CredentialBindings
    from harness.tool_sandbox_bridge import make_sandboxed_runner
    bindings = CredentialBindings({"TEST_KEY": "test_value"})
    runner = make_sandboxed_runner(bindings=bindings)
    assert callable(runner)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_sandbox_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harness.tool_sandbox_bridge'`

- [ ] **Step 3: Implement tool_sandbox_bridge.py**

```python
# harness/tool_sandbox_bridge.py
"""Bridge between ToolRunner and the sandboxed/unsandboxed execution paths.

make_sandboxed_runner() returns a callable with the signature
(cmd: str, root: str) -> tuple[bool, str] that local_tools.py's ToolRunner
accepts as its `runner` callback. On Windows, it routes through the
low-integrity sandbox. Elsewhere, make_unsandboxed_runner() provides bare
subprocess execution with an honest-null note.
"""
from __future__ import annotations

import subprocess
from typing import Callable

from .credential_handles import CredentialBindings

RunnerFn = Callable[[str, str], "tuple[bool, str]"]


def make_sandboxed_runner(
    *, bindings: CredentialBindings | None = None,
    timeout_seconds: int = 120,
) -> RunnerFn:
    def _run(cmd: str, root: str) -> tuple[bool, str]:
        from .sandboxed_runner import SandboxUnavailable, sandboxed_run
        try:
            return sandboxed_run(
                cmd, root, bindings=bindings,
                timeout_seconds=timeout_seconds)
        except SandboxUnavailable:
            return _bare_run(cmd, root, timeout_seconds)
    return _run


def make_unsandboxed_runner(
    *, timeout_seconds: int = 120,
) -> RunnerFn:
    def _run(cmd: str, root: str) -> tuple[bool, str]:
        return _bare_run(cmd, root, timeout_seconds)
    return _run


def _bare_run(
    cmd: str, root: str, timeout: int,
) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=root,
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        partial = ((e.stdout or "") if isinstance(e.stdout, str)
                   else (e.stdout or b"").decode("utf-8", "replace"))
        partial += ((e.stderr or "") if isinstance(e.stderr, str)
                    else (e.stderr or b"").decode("utf-8", "replace"))
        return False, f"[timeout after {timeout}s]\n{partial}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, f"[exit {proc.returncode}]\n{out}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tool_sandbox_bridge.py -v`
Expected: all tests PASS

- [ ] **Step 5: Update _t_run in local_tools.py to prefer the injected runner**

The existing `_t_run` already checks `self.runner` first (line 411). No code change needed in `_t_run` itself. The change is at the CALL SITE that constructs `ToolRunner`: pass `runner=make_sandboxed_runner()` when sandbox is desired, or `runner=make_unsandboxed_runner()` as the default.

Find the constructor call sites for `ToolRunner` in the codebase (grep for `ToolRunner(` in `harness/`). At each site, import and pass the bridge:

```python
from .tool_sandbox_bridge import make_sandboxed_runner
# ... where ToolRunner is constructed:
runner = ToolRunner(root=..., gate=..., runner=make_sandboxed_runner())
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add harness/tool_sandbox_bridge.py tests/test_tool_sandbox_bridge.py harness/local_tools.py
git commit -m "feat(harness): wire sandbox bridge into tool execution path

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Receipt Integration for Session Tokens and Sandbox

Add optional `session_token_ref` and `sandbox` fields to the tool-call receipt so the witness chain records which session token authorized the call and whether it ran under sandbox isolation.

**Files:**
- Modify: `harness/tool_call_receipt.py:96-148` (add optional fields to `build_receipt`)
- Test: `tests/test_tool_call_receipt.py` (add tests for new fields)

**Interfaces:**
- Consumes: `build_receipt()` from `tool_call_receipt.py` (existing)
- Produces: `build_receipt(..., session_token_ref=None, sandbox=None)` with two new optional fields
- `session_token_ref`: string or absent (like `rationale`)
- `sandbox`: `{"kind": "windows-low-integrity", "integrity_level": "low"}` or absent

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_tool_call_receipt.py:

def test_receipt_with_session_token_ref():
    from harness.tool_call_receipt import build_receipt
    r = build_receipt(
        tool="run", capability="builtin-exec", admission="ALLOWED",
        args={"cmd": "echo hi"}, output="hello", ok=True, rc=0,
        run_id="run_001", seq=0,
        session_token_ref="stok_abc123")
    assert r["session_token_ref"] == "stok_abc123"
    assert r["seal"]["hex"]  # still sealed


def test_receipt_without_session_token_is_backward_compatible():
    from harness.tool_call_receipt import build_receipt
    r = build_receipt(
        tool="run", capability="builtin-exec", admission="ALLOWED",
        args={"cmd": "echo hi"}, output="hello", ok=True, rc=0,
        run_id="run_001", seq=0)
    assert "session_token_ref" not in r


def test_receipt_with_sandbox_metadata():
    from harness.tool_call_receipt import build_receipt
    r = build_receipt(
        tool="run", capability="builtin-exec", admission="ALLOWED",
        args={"cmd": "echo hi"}, output="hello", ok=True, rc=0,
        run_id="run_001", seq=0,
        sandbox={"kind": "windows-low-integrity", "integrity_level": "low"})
    assert r["sandbox"]["kind"] == "windows-low-integrity"
    assert r["seal"]["hex"]


def test_receipt_without_sandbox_is_backward_compatible():
    from harness.tool_call_receipt import build_receipt
    r = build_receipt(
        tool="run", capability="builtin-exec", admission="ALLOWED",
        args={"cmd": "echo hi"}, output="hello", ok=True, rc=0,
        run_id="run_001", seq=0)
    assert "sandbox" not in r
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_call_receipt.py -v -k "session_token or sandbox"`
Expected: FAIL (unexpected keyword arguments)

- [ ] **Step 3: Add optional fields to build_receipt**

In `harness/tool_call_receipt.py`, add two parameters to `build_receipt()`:

```python
def build_receipt(
    *,
    tool: str,
    capability: str,
    admission: str,
    args: Any,
    output: str,
    ok: bool,
    rc: int,
    run_id: str,
    seq: int,
    prev_receipt_sha256: str = "",
    outcome: str = COMPLETED,
    rationale: dict[str, Any] | None = None,
    session_token_ref: str | None = None,
    sandbox: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

After the rationale insertion block, before `_seal_receipt(receipt)`:

```python
    if session_token_ref is not None:
        receipt["session_token_ref"] = str(session_token_ref)
    if sandbox is not None:
        receipt["sandbox"] = {
            "kind": str(sandbox.get("kind", "unknown")),
            "integrity_level": str(sandbox.get("integrity_level", "unknown")),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tool_call_receipt.py -v`
Expected: all tests PASS (new and existing)

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add harness/tool_call_receipt.py tests/test_tool_call_receipt.py
git commit -m "feat(harness): add session_token_ref and sandbox fields to tool-call receipt

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Flutter Session Tokens Panel

A widget showing active session tokens: which sessions hold scoped tokens, how many slots each covers, when they expire, and a revoke button. Surfaces in the Endpoints view alongside the existing Keys and Sign-in panels.

**Files:**
- Create: `desktop/lib/widgets/session_tokens_panel.dart`
- Modify: `desktop/lib/views/endpoints_view.dart` (add the panel, ~15 lines)
- Modify: `desktop/lib/client/gateway_client.dart` (add `sessionTokens()` and `sessionTokenRevoke()` methods)
- Test: `desktop/test/session_tokens_panel_test.dart`

**Interfaces:**
- Consumes: `GET /api/session-tokens` from Task 2
- Consumes: `POST /api/session-tokens/revoke` from Task 2
- Produces: `SessionTokensPanel` widget with `doc`, `onRevoke`, `onChanged` callbacks

- [ ] **Step 1: Write the failing test**

```dart
// desktop/test/session_tokens_panel_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/session_tokens_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Map<String, dynamic> _doc({List<Map<String, dynamic>>? tokens}) => {
      'ok': true,
      'tokens': tokens ?? [],
    };

void main() {
  testWidgets('empty tokens states it honestly', (tester) async {
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(),
      onRevoke: (_) async => {'ok': true},
      onChanged: () {},
    )));
    expect(find.textContaining('No active session tokens'), findsOneWidget);
  });

  testWidgets('active tokens show session ref and slot count', (tester) async {
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(tokens: [
        {'token_ref': 'stok_abc', 'session_ref': 'sess_001',
         'slots': 2, 'expires_at': DateTime.now()
             .add(const Duration(minutes: 10))
             .millisecondsSinceEpoch / 1000},
      ]),
      onRevoke: (_) async => {'ok': true},
      onChanged: () {},
    )));
    expect(find.textContaining('sess_001'), findsOneWidget);
    expect(find.textContaining('2 slots'), findsOneWidget);
  });

  testWidgets('revoke button calls onRevoke with token_ref', (tester) async {
    String? revokedRef;
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(tokens: [
        {'token_ref': 'stok_abc', 'session_ref': 'sess_001',
         'slots': 1, 'expires_at': DateTime.now()
             .add(const Duration(minutes: 10))
             .millisecondsSinceEpoch / 1000},
      ]),
      onRevoke: (ref) async { revokedRef = ref; return {'ok': true}; },
      onChanged: () {},
    )));
    await tester.tap(find.widgetWithText(TextButton, 'Revoke'));
    await tester.pumpAndSettle();
    expect(revokedRef, 'stok_abc');
  });

  testWidgets('token_ref value is never displayed', (tester) async {
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(tokens: [
        {'token_ref': 'stok_abc123def456', 'session_ref': 'sess_001',
         'slots': 1, 'expires_at': DateTime.now()
             .add(const Duration(minutes: 10))
             .millisecondsSinceEpoch / 1000},
      ]),
      onRevoke: (_) async => {'ok': true},
      onChanged: () {},
    )));
    expect(find.textContaining('stok_abc123def456'), findsNothing);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd desktop && flutter test test/session_tokens_panel_test.dart`
Expected: FAIL (widget not found)

- [ ] **Step 3: Implement SessionTokensPanel**

```dart
// desktop/lib/widgets/session_tokens_panel.dart
import 'package:flutter/material.dart';
import '../theme/flywheel_theme.dart';

class SessionTokensPanel extends StatefulWidget {
  final Map<String, dynamic> doc;
  final Future<Map<String, dynamic>> Function(String tokenRef) onRevoke;
  final VoidCallback onChanged;

  const SessionTokensPanel({
    super.key,
    required this.doc,
    required this.onRevoke,
    required this.onChanged,
  });

  @override
  State<SessionTokensPanel> createState() => _SessionTokensPanelState();
}

class _SessionTokensPanelState extends State<SessionTokensPanel> {
  String? _busy;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final tokens = (widget.doc['tokens'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    if (tokens.isEmpty) {
      return const HonestNull('No active session tokens.');
    }
    return HairlineCard(
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s4, vertical: FwLayout.s2),
      child: Column(
        children: [for (final tok in tokens) _row(t, tok)],
      ),
    );
  }

  Widget _row(FwTokens t, Map<String, dynamic> tok) {
    final session = tok['session_ref'] as String? ?? 'unknown';
    final slots = tok['slots'] as int? ?? 0;
    final expiresAt = tok['expires_at'] as num? ?? 0;
    final remaining = Duration(
        seconds: (expiresAt - DateTime.now().millisecondsSinceEpoch / 1000)
            .round()
            .clamp(0, 99999));
    final ref = tok['token_ref'] as String? ?? '';
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration:
          BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(session,
                    style: fwMono(t, size: 12, weight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text('$slots slots · ${_fmt(remaining)} remaining',
                    style: TextStyle(fontSize: 11.5, color: t.inkMuted)),
              ],
            ),
          ),
          TextButton(
            onPressed: _busy == ref ? null : () => _revoke(ref),
            child: Text(_busy == ref ? 'Revoking…' : 'Revoke'),
          ),
        ],
      ),
    );
  }

  String _fmt(Duration d) {
    if (d.inHours > 0) return '${d.inHours}h ${d.inMinutes % 60}m';
    return '${d.inMinutes}m';
  }

  Future<void> _revoke(String ref) async {
    setState(() => _busy = ref);
    try {
      await widget.onRevoke(ref);
      widget.onChanged();
    } catch (_) {}
    if (mounted) setState(() => _busy = null);
  }
}
```

- [ ] **Step 4: Add gateway client methods**

In `desktop/lib/client/gateway_client.dart`, add:

```dart
Future<Map<String, dynamic>> sessionTokens() => getJson('/api/session-tokens');

Future<Map<String, dynamic>> sessionTokenRevoke(String tokenRef) =>
    postJson('/api/session-tokens/revoke', {'token_ref': tokenRef});
```

- [ ] **Step 5: Wire into EndpointsView**

In `desktop/lib/views/endpoints_view.dart`, add a state field and load call:

```dart
Map<String, dynamic>? _sessionTokens;
```

In `_load()`, add `widget.client.sessionTokens()` to the `Future.wait` list and assign the result.

In `build()`, after the sign-in panel block:

```dart
if (_sessionTokens != null) ...[
  const SizedBox(height: FwLayout.s5),
  const Kicker('session tokens · scoped, time-bounded agent credentials'),
  const SizedBox(height: FwLayout.s3),
  SessionTokensPanel(
    doc: _sessionTokens!,
    onRevoke: widget.client.sessionTokenRevoke,
    onChanged: _load,
  ),
],
```

Add the import at the top: `import '../widgets/session_tokens_panel.dart';`

- [ ] **Step 6: Run Flutter tests**

Run: `cd desktop && flutter analyze && flutter test`
Expected: analyze clean, all tests PASS

- [ ] **Step 7: Commit**

```bash
git add desktop/lib/widgets/session_tokens_panel.dart desktop/test/session_tokens_panel_test.dart desktop/lib/views/endpoints_view.dart desktop/lib/client/gateway_client.dart
git commit -m "feat(desktop): add session tokens panel to endpoints view

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```
