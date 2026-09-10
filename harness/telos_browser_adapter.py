"""Bounded Telos reuse behind the persisted browser-admission driver seam."""
from __future__ import annotations

import os
from pathlib import Path
import time

from .cross_harness_process import start_owned_process
from .evidence_json import canonical_bytes, strict_load_json
from .telos_browser_config import BrowserConfig, ConfigError, canonical_origin

MAX_REQUEST_BYTES = 16_384
MAX_RESULT_BYTES = 32_768
MAX_TIMEOUT_SECONDS = 10.0
_ENV = frozenset(("SYSTEMROOT", "WINDIR", "TEMP", "TMP"))


class AdapterUnknown(OSError):
    """A dispatched request lacks a trustworthy terminal acknowledgement."""


def _not_performed(code: str) -> dict:
    return {"ok": False, "performed": False, "code": code}


class TelosBrowserAdapter:
    driver_name = "telos-browser"

    def __init__(self, config: BrowserConfig, *, launcher=None,
                 timeout_seconds: float = MAX_TIMEOUT_SECONDS) -> None:
        self._config = BrowserConfig.from_dict(config.as_dict())
        if (type(timeout_seconds) not in (int, float)
                or not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS):
            raise ConfigError("invalid_adapter_timeout")
        self._timeout = float(timeout_seconds)
        self._launcher = start_owned_process if launcher is None else launcher
        self._fixture = launcher is not None

    @property
    def binding_sha256(self) -> str:
        return self._config.binding_sha256

    def __call__(self, action: dict) -> dict:
        try:
            request = self._request(action)
            self._config.verify_runtime()
        except (ConfigError, TypeError, ValueError):
            return _not_performed("adapter_preflight_refused")
        owned = None
        try:
            deadline = time.monotonic() + self._timeout
            owned = self._launcher(
                (self._config.node_path, str(Path(__file__).with_name("telos_browser_bridge.mjs"))),
                cwd=Path(__file__).parent, stdin_bytes=request,
                env={k: v for k, v in os.environ.items() if k.upper() in _ENV},
                hide_window=True)
            if time.monotonic() >= deadline or not owned.resume():
                raise AdapterUnknown("browser_delivery_unknown")
            while True:
                if owned.capture_overflow():
                    owned.signal_tree()
                    raise AdapterUnknown("browser_delivery_unknown")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    owned.signal_tree()
                    raise AdapterUnknown("browser_delivery_unknown")
                outcome = owned.wait(min(.02, remaining))
                if outcome is not None:
                    if time.monotonic() >= deadline:
                        owned.signal_tree()
                        raise AdapterUnknown("browser_delivery_unknown")
                    return self._outcome(outcome, action["kind"])
        except Exception:
            raise AdapterUnknown("browser_delivery_unknown") from None
        finally:
            if owned is not None:
                try:
                    owned.close()
                except Exception:
                    raise AdapterUnknown("browser_delivery_unknown") from None

    def _request(self, action: dict) -> bytes:
        if (not isinstance(action, dict) or action.get("kind") not in ("read", "navigate")
                or action.get("origin") != self._config.allowed_origin):
            raise ConfigError("action_not_supported")
        if action.get("selector") or action.get("field"):
            raise ConfigError("action_not_supported")
        url = action.get("url", "")
        if action["kind"] == "navigate":
            if not isinstance(url, str) or canonical_origin(url) != self._config.allowed_origin:
                raise ConfigError("destination_not_allowed")
        elif url:
            raise ConfigError("action_not_supported")
        request = canonical_bytes({
            "schema": "flywheel.telos-browser-request/v1", "config": self._config.as_dict(),
            "action": {"kind": action["kind"], "url": url},
            "timeout_ms": max(1, int(self._timeout * 900)),
        })
        if len(request) > MAX_REQUEST_BYTES:
            raise ConfigError("request_too_large")
        return request

    def _outcome(self, outcome, kind: str) -> dict:
        if (outcome.returncode != 0 or outcome.timed_out or outcome.malformed_output
                or len(outcome.stdout.encode("utf-8")) > MAX_RESULT_BYTES):
            raise AdapterUnknown("browser_delivery_unknown")
        row = strict_load_json(outcome.stdout)
        if (not isinstance(row, dict) or type(row.get("ok")) is not bool
                or type(row.get("performed")) is not bool
                or row["ok"] != row["performed"]
                or row.get("code") not in ("read", "navigation_requested", "preflight_refused")):
            raise AdapterUnknown("browser_delivery_unknown")
        if row["performed"]:
            expected = {"ok", "performed", "code"} | ({"observation"} if kind == "read" else set())
            if (set(row) != expected or row["code"] != ("read" if kind == "read" else "navigation_requested")
                    or (kind == "read" and (not isinstance(row["observation"], str)
                        or len(row["observation"].encode("utf-8")) > 16_384))):
                raise AdapterUnknown("browser_delivery_unknown")
            if self._fixture:
                return _not_performed("fixture_only")
            return row
        if set(row) != {"ok", "performed", "code"} or row["code"] != "preflight_refused":
            raise AdapterUnknown("browser_delivery_unknown")
        return _not_performed("adapter_preflight_refused")
