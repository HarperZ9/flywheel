"""Loopback gateway fixture for Codex account HTTP route tests."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from harness import gateway
from harness.gateway_auth import DEFAULT_HOSTS
from tests.http_fixture_client import request as socket_request


TOKEN = "synthetic-codex-account-token"
OWNER = "owner_" + "a" * 32
OTHER_OWNER = "owner_" + "b" * 32


class ManagerResponse(dict):
    """Dict body that also supports ``body, status = manager.method(...)``."""

    def __init__(self, body: dict, status: int = 200) -> None:
        super().__init__(body)
        self.http_status = status

    def __iter__(self):
        yield dict(self)
        yield self.http_status


class FakeCodexAccountManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def read_status(self, *args, **kwargs):
        return self._record("read_status", args, kwargs)

    def login_result(self, *args, **kwargs):
        return self._record("login_result", args, kwargs)

    def start_login(self, *args, **kwargs):
        return self._record("start_login", args, kwargs)

    def cancel_login(self, *args, **kwargs):
        return self._record("cancel_login", args, kwargs)

    def logout(self, *args, **kwargs):
        return self._record("logout", args, kwargs)

    def _record(self, method: str, args: tuple, kwargs: dict) -> ManagerResponse:
        call = {"method": method, "args": args, "kwargs": dict(kwargs)}
        self.calls.append(call)
        owner_ref = kwargs.get("owner_ref") or _first_owner(args)
        login_id = kwargs.get("login_id") or _first_matching(args, "login-")
        mode = kwargs.get("mode") or _first_matching(args, ("browser", "device"))
        visible = kwargs.get("visible_ui_action")
        body = {
            "schema": "test.codex-account-manager-call/v1",
            "method": method,
            "owner_ref": owner_ref,
            "visible_ui_action": visible,
        }
        if login_id is not None:
            body["login_id"] = login_id
        if mode is not None:
            body["mode"] = mode
        return ManagerResponse(body)


def _first_owner(args: tuple) -> str | None:
    return next(
        (item for item in args if isinstance(item, str) and item.startswith("owner_")),
        None,
    )


def _first_matching(args: tuple, prefixes) -> str | None:
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    return next(
        (
            item
            for item in args
            if isinstance(item, str) and any(item.startswith(prefix) for prefix in prefixes)
        ),
        None,
    )


def json_bytes(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class CodexAccountGateway:
    def __init__(
        self,
        home: Path,
        *,
        owner_ref: str = OWNER,
        manager: FakeCodexAccountManager | None = None,
    ) -> None:
        self.home = home
        self.manager = manager or FakeCodexAccountManager()
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "owner.ref").write_text(owner_ref, encoding="ascii")
        run_root_value = self.home / "run"
        run_root_value.mkdir()
        repo_root = Path(__file__).resolve().parents[1]
        manager_value = self.manager

        class Handler(gateway._Handler):
            auth_token = TOKEN
            allowed_hosts = DEFAULT_HOSTS
            flywheel_home = home
            root = repo_root
            run_root = str(run_root_value)
            codex_account_manager = manager_value

            def log_message(self, *_args) -> None:
                pass

        self.handler = Handler
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.http.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()

    @property
    def port(self) -> int:
        return self.http.server_address[1]

    def json_request(
        self,
        path: str,
        *,
        body: bytes | dict | None = None,
        token: str | None = TOKEN,
        host: str | None = None,
        content_type: str | None = "application/json",
    ) -> tuple[int, dict | str]:
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None and content_type is not None:
            headers["Content-Type"] = content_type
        if host is not None:
            headers["Host"] = host
        raw = json_bytes(body) if isinstance(body, dict) else body
        status, text = socket_request(self.port, path, data=raw, headers=headers)
        try:
            return status, json.loads(text)
        except json.JSONDecodeError:
            return status, text

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(5)
