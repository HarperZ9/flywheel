"""Owner-scoped Codex account login sessions."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .codex_account_binding import LoginCompletionContext, account_client, close_account_client, successful_login_response
from .codex_account_login import start_managed_login_raw, validated_login_start
from .codex_account_safety import DEFAULT_ALLOWED_LOGIN_HOSTS, login_id as safe_login_id, owner_ref, public_string, safe_error
from .codex_account_state import (LOGIN_MODES, Session, bad_request_response,
    completion_for, notification_overflowed, rejected_response, route_state,
    unknown_login_response)
from .codex_app_server_client import CodexAppServerClient
from .codex_consumer_account import cancel_managed_login, logout_account, read_account_state, read_model_provider_capabilities

class CodexAccountUnavailable(RuntimeError):
    def __init__(self, state: str, *, reason: str, status: int = 503) -> None:
        self.state, self.reason, self.status = state, reason, status
        super().__init__(reason)


def _unavailable_response(exc: CodexAccountUnavailable) -> tuple[dict, int]:
    return route_state(exc.state, reason=exc.reason), exc.status

class CodexAccountSessionManager:
    def __init__(
            self, *, client_factory: Callable[[], Any] | None = None,
            owner_client_factory: Callable[..., Any] | None = None,
            key_source: Callable[[str], str] | None = None,
            clock: Callable[[], float] | None = None,
            ttl_seconds: float = 600.0,
            allowed_login_hosts: tuple[str, ...] | None = None,
            max_pending_sessions: int = 16,
            login_success_hook: Callable[[LoginCompletionContext], Any] | None = None):
        if client_factory is not None and owner_client_factory is not None:
            raise ValueError('only one account client factory is allowed')
        self.client_factory = client_factory or CodexAppServerClient.connect
        self.owner_client_factory = owner_client_factory
        self.key_source = (key_source if key_source is not None else
                           (lambda _: 'absent') if owner_client_factory is not None else None)
        self.clock = clock or time.time
        self.ttl_seconds = ttl_seconds
        self.allowed_login_hosts = allowed_login_hosts or DEFAULT_ALLOWED_LOGIN_HOSTS
        self.max_pending_sessions = max(1, int(max_pending_sessions))
        self.login_success_hook = login_success_hook
        self._sessions: dict[tuple[str, str], Session] = {}
        self._reservation_seq = 0
        self._lock = threading.RLock()

    def read_status(self, owner_ref_value: Any) -> tuple[dict, int]:
        with self._lock:
            self._expire_locked()
        try:
            owner = owner_ref(owner_ref_value)
        except ValueError:
            return bad_request_response("owner required")
        try:
            client = self._client_for(owner)
        except CodexAccountUnavailable as exc:
            return _unavailable_response(exc)
        except Exception as exc:
            return route_state("unavailable", reason=safe_error(exc)), 503
        try:
            body = route_state("ready")
            body["account"] = read_account_state(account_client(client), key_source=self.key_source)
            body["capabilities"] = read_model_provider_capabilities(account_client(client))
            return body, 200
        finally:
            self._close(client)

    def start_login(self, owner_ref_value: Any, mode: Any, *,
                    visible_ui_action: bool = False) -> tuple[dict, int]:
        if not visible_ui_action:
            return rejected_response()
        try:
            owner = owner_ref(owner_ref_value)
        except ValueError:
            return bad_request_response("owner required")
        mode_value = public_string(mode, limit=40)
        if mode_value not in LOGIN_MODES:
            return bad_request_response("unsupported login mode")
        reserved_key, refused = self._reserve(owner, mode_value)
        if refused:
            return refused
        client = None
        try:
            client = self._client_for(owner)
            started = start_managed_login_raw(account_client(client), mode=mode_value)
            login = safe_login_id(started.get("login_id"))
            body = validated_login_start(started, self.allowed_login_hosts)
            accepted = self._accept_reservation(reserved_key, owner, login, body, client)
            if accepted is not None:
                return accepted
            return body, 202
        except CodexAccountUnavailable as exc:
            with self._lock:
                self._sessions.pop(reserved_key, None)
            return _unavailable_response(exc)
        except Exception as exc:
            with self._lock:
                self._sessions.pop(reserved_key, None)
            if client is not None: self._close(client)
            return route_state("failed", reason=safe_error(exc)), 502

    def login_result(self, owner_ref_value: Any, login_id_value: Any) -> tuple[dict, int]:
        try:
            owner = owner_ref(owner_ref_value)
            login = safe_login_id(login_id_value)
        except ValueError:
            return bad_request_response("login handle required")
        key = (owner, login)
        with self._lock:
            self._expire_locked(except_key=key)
            session = self._sessions.get(key)
            if session is None or session.reserved:
                return unknown_login_response()
            if self.clock() >= session.expires_at:
                self._finish_locked(key, session)
                return route_state("expired", login_id=login), 410
            client = account_client(session.client)
            pop = getattr(client, "pop_notification", None)
            if pop is None:
                body = route_state("pending", login_id=login)
                body.update({"completion_state": "unknown",
                             "reason": "login completion notification unavailable"})
                return body, 202
            try:
                completed = self._poll_completion(session, pop)
            except Exception as exc:
                self._finish_locked(key, session)
                return route_state("client_failed", login_id=login,
                                   reason=safe_error(exc)), 502
            if completed is None:
                if notification_overflowed(client):
                    self._finish_locked(key, session)
                    return route_state("client_failed", login_id=login,
                                       reason="notification overflow"), 502
                body = route_state("pending", login_id=login)
                body.update({"completion_state": "pending",
                             "reason": "waiting for account/login/completed"})
                return body, 202
            cleanup_ok = self._finish_locked(key, session)
        if completed.get("success") is True:
            return successful_login_response(session, login, completed, cleanup_ok,
                                             self.login_success_hook)
        body = route_state("failed", login_id=login,
                           reason=public_string(completed.get("error")))
        body["completion_state"] = "completed"
        return body, 200

    def cancel_login(self, owner_ref_value: Any, login_id_value: Any, *,
                     visible_ui_action: bool = False) -> tuple[dict, int]:
        if not visible_ui_action:
            return rejected_response()
        try:
            owner = owner_ref(owner_ref_value)
            login = safe_login_id(login_id_value)
        except ValueError:
            return bad_request_response("login handle required")
        key = (owner, login)
        with self._lock:
            self._expire_locked()
            session = self._sessions.get(key)
            if session is None or session.reserved:
                return unknown_login_response()
            try:
                result = cancel_managed_login(account_client(session.client), login)
                state = public_string(result.get("state")) or "unknown"
                return route_state(state, login_id=login), 200
            except Exception as exc:
                return route_state("client_failed", login_id=login,
                                   reason=safe_error(exc)), 502
            finally:
                self._finish_locked(key, session)

    def logout(self, owner_ref_value: Any, *,
               visible_ui_action: bool = False) -> tuple[dict, int]:
        if not visible_ui_action:
            return rejected_response()
        try:
            owner = owner_ref(owner_ref_value)
        except ValueError:
            return bad_request_response("owner required")
        with self._lock:
            self._expire_locked()
            client = None
            try:
                client = self._client_for(owner)
                result = logout_account(account_client(client))
                state = public_string(result.get("state")) or "logout_requested"
                return route_state(state), 200
            except CodexAccountUnavailable as exc:
                return _unavailable_response(exc)
            except Exception as exc:
                return route_state("client_failed", reason=safe_error(exc)), 502
            finally:
                if client is not None: self._close(client)
                self._close_owner_sessions_locked(owner)

    def _reserve(self, owner: str, mode: str) -> tuple[tuple[str, str], tuple[dict, int] | None]:
        with self._lock:
            self._expire_locked()
            pending = self._pending_for_locked(owner)
            if pending:
                body = route_state("already_pending")
                if not pending.reserved:
                    body["login_id"] = pending.login_id
                body["mode"] = pending.mode
                return (owner, pending.login_id), (body, 409)
            if len(self._sessions) >= self.max_pending_sessions:
                body = route_state("throttled", reason="pending login limit reached")
                return (owner, ""), (body, 503)
            self._reservation_seq += 1
            login = f"__reserved_{self._reservation_seq}"
            key = (owner, login)
            self._sessions[key] = Session(
                owner, login, mode, None, self.clock() + self.ttl_seconds, True)
            return key, None

    def _accept_reservation(
            self, reserved_key: tuple[str, str], owner: str, login: str,
            body: dict, client: Any) -> tuple[dict, int] | None:
        with self._lock:
            reservation = self._sessions.get(reserved_key)
            if reservation is None:
                self._close(client)
                return route_state("expired", reason="login session no longer pending"), 410
            if self.clock() >= reservation.expires_at:
                self._finish_locked(reserved_key, reservation)
                self._close(client)
                return route_state("expired", reason="login start timed out"), 410
            self._sessions.pop(reserved_key, None)
            expires_at = self.clock() + self.ttl_seconds
            self._sessions[(owner, login)] = Session(
                owner, login, body["mode"], client, expires_at)
            body.update({"login_id": login, "expires_at": expires_at})
            return None

    def _client_for(self, owner: str):
        return (self.owner_client_factory(owner_ref=owner)
                if self.owner_client_factory is not None else self.client_factory())

    def _poll_completion(self, session: Session, pop: Callable[..., Any]) -> dict | None:
        for _ in range(25):
            notification = pop(timeout=0.0)
            if notification is None:
                return None
            completed = completion_for(session, notification)
            if completed is not None:
                return completed
        return None

    def _pending_for_locked(self, owner: str) -> Session | None:
        for session_owner, login in self._sessions:
            if session_owner == owner:
                return self._sessions[(session_owner, login)]
        return None

    def _expire_locked(self, owner: str | None = None,
                       except_key: tuple[str, str] | None = None) -> None:
        now = self.clock()
        expired = [key for key, session in self._sessions.items()
                   if key != except_key
                   if (owner is None or session.owner_ref == owner)
                   and now >= session.expires_at]
        for key in expired:
            session = self._sessions.pop(key)
            self._close(session.client)

    def _finish_locked(self, key: tuple[str, str], session: Session) -> bool:
        self._sessions.pop(key, None); return self._close(session.client)

    def _close_owner_sessions_locked(self, owner: str) -> None:
        keys = [key for key, session in self._sessions.items() if session.owner_ref == owner]
        for key in keys:
            session = self._sessions.pop(key)
            self._close(session.client)

    def shutdown(self) -> bool:
        cleanup_ok = True
        with self._lock:
            for key, session in list(self._sessions.items()):
                if self._close(session.client):
                    self._sessions.pop(key, None)
                else:
                    cleanup_ok = False
        return cleanup_ok

    @staticmethod
    def _close(client: Any) -> bool:
        return close_account_client(client)
