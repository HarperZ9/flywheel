"""Unregistered Codex consumer-account backend seam.

This file deliberately does not mutate the shared endpoint registry. It gives
composition code a safe readiness snapshot for the supported Codex app-server
route.
"""
from __future__ import annotations

import shutil
from typing import Callable

from .codex_app_server_client import CodexAppServerClient
from .codex_consumer_account import read_account_state


class CodexConsumerBackend:
    """Read supported Codex app-server readiness without provider calls."""

    def __init__(
            self, *, client_factory: Callable[[], CodexAppServerClient] | None = None,
            which: Callable[[str], str | None] | None = None,
            key_source: Callable[[str], str] | None = None):
        self.client_factory = client_factory or CodexAppServerClient.connect
        self.which = which or shutil.which
        self.key_source = key_source
        self._client = None

    def readiness(self) -> dict:
        path = self.which("codex")
        base = {"provider": "codex", "transport": "codex-app-server",
                "cli_present": bool(path), "usable": False}
        if not path:
            base["reason"] = "Codex CLI absent"
            return base
        try:
            self._client = self.client_factory()
        except Exception as exc:
            base["reason"] = f"Codex app-server unavailable: {type(exc).__name__}"
            return base
        try:
            account = read_account_state(self._client, key_source=self.key_source)
            base["account"] = account
            base["usable"] = account.get("usable_for_codex") is True
            base["reason"] = account.get("reason", "") if not base["usable"] else ""
            return base
        finally:
            self.close()

    def close(self) -> None:
        client = self._client
        self._client = None
        close = getattr(client, "close", None)
        if close:
            close()
