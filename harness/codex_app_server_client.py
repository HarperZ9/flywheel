"""Codex app-server JSON-RPC client.

Codex owns managed ChatGPT login and token custody. This module speaks the
official local app-server protocol and returns only protocol responses; it does
not read Codex auth files, scrape tokens, or call provider inference APIs.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from typing import Any, Protocol

_ACCOUNT_LOGIN_COMPLETED = "account/login/completed"


class RpcTransport(Protocol):
    def request(self, method: str, params: Any = None) -> Any:
        ...


class CodexAppServerError(RuntimeError):
    """Public app-server failure. Raw server error text is intentionally omitted."""

    def __init__(self, method: str, *, code: int | None = None):
        suffix = f" ({code})" if code is not None else ""
        super().__init__(f"{method} failed{suffix}")
        self.method = method
        self.code = code


class CodexAppServerStdioTransport:
    """JSON-RPC over `codex app-server --stdio`.

    The process may be injected in tests. Real callers get a fresh local
    app-server process and exchange one JSON object per line.
    """

    def __init__(
            self, argv: tuple[str, ...] | None = None, *,
            process=None, popen=None, timeout: float = 10.0,
            close_timeout: float = 2.0,
            notification_queue_size: int = 64):
        self.argv = argv or ("codex", "app-server", "--stdio")
        self.timeout = timeout
        self.close_timeout = close_timeout
        self._next_id = 0
        self._closed = False
        self.process = process if process is not None else self._spawn(popen)
        self._responses: "queue.Queue[Any]" = queue.Queue()
        self._notifications: "queue.Queue[dict]" = queue.Queue(
            maxsize=max(1, int(notification_queue_size)))
        self._notification_overflowed = False
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _spawn(self, popen):
        popen = popen or subprocess.Popen
        kwargs = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "bufsize": 1,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return popen(list(self.argv), **kwargs)

    def _read_stdout(self) -> None:
        stdout = getattr(self.process, "stdout", None)
        if stdout is None:
            self._responses.put(CodexAppServerError("app-server/stdout"))
            return
        while True:
            try:
                line = stdout.readline()
            except Exception:
                self._responses.put(CodexAppServerError("app-server/read"))
                return
            if not line:
                return
            try:
                msg = json.loads(line)
            except ValueError:
                self._responses.put(CodexAppServerError("app-server/json"))
                continue
            if isinstance(msg, dict) and "id" not in msg and isinstance(
                    msg.get("method"), str):
                self._queue_notification(msg)
                continue
            self._responses.put(msg)

    def request(self, method: str, params: Any = None) -> Any:
        self._next_id += 1
        request_id = self._next_id
        payload: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        stdin = getattr(self.process, "stdin", None)
        if stdin is None:
            raise CodexAppServerError(method)
        try:
            stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            stdin.flush()
        except Exception as exc:
            raise CodexAppServerError(method) from exc
        return self._wait_for_response(method, request_id)

    def _wait_for_response(self, method: str, request_id: int) -> Any:
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexAppServerError(method)
            try:
                msg = self._responses.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                poll = getattr(self.process, "poll", lambda: None)
                if poll() is not None:
                    raise CodexAppServerError(method)
                continue
            if isinstance(msg, CodexAppServerError):
                raise CodexAppServerError(method) from msg
            if not isinstance(msg, dict):
                continue
            if "id" not in msg and isinstance(msg.get("method"), str):
                self._queue_notification(msg)
                continue
            if msg.get("id") != request_id:
                continue
            if "error" in msg:
                error = msg.get("error")
                code = error.get("code") if isinstance(error, dict) else None
                raise CodexAppServerError(method, code=code)
            if "result" in msg:
                return msg["result"]
            raise CodexAppServerError(method)

    def _queue_notification(self, msg: dict) -> None:
        if msg.get("method") != _ACCOUNT_LOGIN_COMPLETED:
            return
        try:
            self._notifications.put_nowait(msg)
        except queue.Full:
            self._notification_overflowed = True

    def pop_notification(self, *, timeout: float = 0.0) -> dict | None:
        try:
            return self._notifications.get(timeout=timeout)
        except queue.Empty:
            return None

    def notification_overflowed(self) -> bool:
        return self._notification_overflowed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            stdin = getattr(self.process, "stdin", None)
            if stdin is not None:
                stdin.close()
        except Exception:
            pass
        try:
            poll = getattr(self.process, "poll", lambda: None)
            if poll() is not None:
                return
            self.process.terminate()
            wait = getattr(self.process, "wait", None)
            if wait is None:
                return
            try:
                wait(timeout=self.close_timeout)
            except subprocess.TimeoutExpired:
                kill = getattr(self.process, "kill", None)
                if kill is not None:
                    kill()
                wait(timeout=self.close_timeout)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        self.close()


class CodexAppServerClient:
    """Typed convenience methods for the generated app-server account/model API."""

    def __init__(self, transport: RpcTransport | None = None):
        self.transport = transport or CodexAppServerStdioTransport()

    @classmethod
    def connect(cls, *, initialize: bool = True, **transport_kwargs):
        client = cls(CodexAppServerStdioTransport(**transport_kwargs))
        try:
            if initialize:
                client.initialize()
            return client
        except Exception:
            client.close()
            raise

    def initialize(self) -> dict:
        return self.transport.request("initialize", {
            "clientInfo": {
                "name": "flywheel",
                "title": "Flywheel",
                "version": "1.0.0",
            },
            "capabilities": {
                "experimentalApi": True,
                "requestAttestation": False,
            },
        })

    def get_account(self, *, refresh_token: bool = False) -> dict:
        params = {"refreshToken": True} if refresh_token else {}
        return self.transport.request("account/read", params)

    def start_chatgpt_login(self, **options) -> dict:
        params = {"type": "chatgpt"}
        for key, value in options.items():
            if value is not None:
                params[key] = value
        return self.transport.request("account/login/start", params)

    def start_device_code_login(self) -> dict:
        return self.transport.request(
            "account/login/start", {"type": "chatgptDeviceCode"})

    def cancel_login(self, login_id: str) -> dict:
        return self.transport.request(
            "account/login/cancel", {"loginId": login_id})

    def logout(self) -> dict:
        return self.transport.request("account/logout")

    def list_models(
            self, *, cursor: str | None = None, limit: int | None = None,
            include_hidden: bool | None = None) -> dict:
        params: dict[str, Any] = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit
        if include_hidden is not None:
            params["includeHidden"] = include_hidden
        return self.transport.request("model/list", params)

    def read_model_provider_capabilities(self) -> dict:
        return self.transport.request("modelProvider/capabilities/read", {})

    def pop_notification(self, *, timeout: float = 0.0) -> dict | None:
        pop = getattr(self.transport, "pop_notification", None)
        if pop is None:
            return None
        return pop(timeout=timeout)

    def notification_overflowed(self) -> bool:
        overflowed = getattr(self.transport, "notification_overflowed", None)
        return bool(overflowed()) if overflowed else False

    def close(self) -> None:
        close = getattr(self.transport, "close", None)
        if close:
            close()
