"""Typed client wrapper for an injected Claude Code stream-json process."""
from __future__ import annotations

from .claude_session_transport import (
    ClaudeSessionLaunchConfig,
    ClaudeSessionTransport,
    build_claude_session_argv,
)


class ClaudeSessionCleanupError(RuntimeError):
    def __init__(self, code: str, process=None):
        self.code = code
        self.process = process
        super().__init__(code)


class ClaudeSessionClient:
    def __init__(self, process, transport: ClaudeSessionTransport, *, initialized: bool = False):
        self._process = process
        self._transport = transport
        self._initialized = initialized

    @classmethod
    def start(cls, config: ClaudeSessionLaunchConfig, *, launcher=None, env=None,
              initialize_timeout: float = 5.0):
        if launcher is None:
            raise ValueError(
                "ClaudeSessionClient requires an injected launcher until "
                "runtime custody and execution policy are bound")
        argv = build_claude_session_argv(config)
        cwd = config.working_directory or None
        process = launcher(argv, cwd, {} if env is None else dict(env))
        if getattr(process, "stdin", None) is None:
            cls._cleanup_process_or_raise(process, initialize_timeout)
            raise ValueError("Claude session process missing stdin")
        if getattr(process, "stdout", None) is None:
            cls._cleanup_process_or_raise(process, initialize_timeout)
            raise ValueError("Claude session process missing stdout")
        transport = ClaudeSessionTransport(
            incoming=process.stdout, outgoing=process.stdin)
        client = cls(process, transport)
        try:
            client.initialize(timeout=initialize_timeout)
        except Exception:
            if not client._cleanup_after_failure(initialize_timeout):
                raise ClaudeSessionCleanupError("cleanup_incomplete", process) from None
            raise
        return client

    @property
    def session_id(self) -> str:
        return self._transport.session_id

    def initialize(self, *, timeout: float | None = None) -> dict:
        result = self._transport.initialize(timeout=timeout)
        self._initialized = True
        return result

    def send_text(self, text: str) -> None:
        self._require_initialized()
        self._transport.send_user_message(text)

    def send_blocks(self, blocks: list[dict]) -> None:
        self._require_initialized()
        self._transport.send_user_message(blocks)

    def interrupt(self, *, timeout: float | None = None) -> dict:
        self._require_initialized()
        return self._transport.interrupt(timeout=timeout)

    def next_event(self, timeout: float | None = None):
        return self._transport.pop_event(timeout=timeout)

    def next_protocol_event(self, timeout: float | None = None):
        return self._transport.pop_protocol_event(timeout=timeout)

    def next_control_request(self, timeout: float | None = None):
        return self._transport.pop_control_request(timeout=timeout)

    def send_permission_decision(self, request, decision) -> None:
        self._require_initialized()
        self._transport.send_permission_decision(request, decision)

    def needs_recovery(self) -> bool:
        return self._transport.needs_recovery()

    def has_pending_control_requests(self) -> bool:
        return self._transport.has_pending_control_requests()

    def mark_recovery_needed(self) -> None:
        self._transport.mark_recovery_needed()

    def cancel(self, *, wait_timeout: float = 5.0) -> bool:
        self._transport.mark_recovery_needed()
        self._close_pipe(getattr(self._process, "stdin", None))
        self._call("terminate")
        process_ok = self._wait(wait_timeout)
        if not process_ok:
            self._call("kill")
            process_ok = self._wait(wait_timeout)
        transport_ok = self._transport.shutdown(timeout=wait_timeout)
        self._close_pipe(getattr(self._process, "stderr", None))
        return self._release_runtime_if_complete(process_ok and transport_ok)

    def kill(self, *, wait_timeout: float = 5.0) -> bool:
        self._transport.mark_recovery_needed()
        self._close_pipe(getattr(self._process, "stdin", None))
        self._call("kill")
        process_ok = self._wait(wait_timeout)
        transport_ok = self._transport.shutdown(timeout=wait_timeout)
        self._close_pipe(getattr(self._process, "stderr", None))
        return self._release_runtime_if_complete(process_ok and transport_ok)

    def close(self, *, wait_timeout: float = 5.0) -> bool:
        self._transport.mark_recovery_needed()
        process_ok = self._close_process(wait_timeout)
        transport_ok = self._transport.shutdown(timeout=wait_timeout)
        self._close_pipe(getattr(self._process, "stderr", None))
        return self._release_runtime_if_complete(process_ok and transport_ok)

    def _release_runtime_if_complete(self, ok: bool) -> bool:
        if not ok:
            return False
        release = getattr(self, "_runtime_release", None)
        if ok and callable(release):
            try:
                release()
                self._runtime_release = None
            except Exception:
                return False
        return True

    def _require_initialized(self) -> None:
        if not self._initialized:
            from .claude_session_transport import ClaudeSessionTransportError
            raise ClaudeSessionTransportError("not_initialized", "Claude session is not initialized")

    def _call(self, method: str) -> None:
        fn = getattr(self._process, method, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _wait(self, timeout: float) -> bool:
        wait = getattr(self._process, "wait", None)
        if not callable(wait):
            return False
        try:
            wait(timeout=timeout)
            return True
        except (TimeoutError, TypeError):
            return False
        except Exception:
            return False

    def _cleanup_after_failure(self, timeout: float) -> bool:
        self._transport.mark_recovery_needed()
        process_ok = self._close_process(timeout)
        transport_ok = self._transport.shutdown(timeout=timeout)
        self._close_pipe(getattr(self._process, "stderr", None))
        return process_ok and transport_ok

    def _close_process(self, timeout: float) -> bool:
        return self._close_process_object(self._process, timeout)

    @classmethod
    def _cleanup_process_or_raise(cls, process, timeout: float) -> None:
        if not cls._close_process_object(process, timeout):
            raise ClaudeSessionCleanupError("cleanup_incomplete", process) from None

    @classmethod
    def _close_process_object(cls, process, timeout: float) -> bool:
        close = getattr(process, "close", None)
        if callable(close):
            try:
                cleanup = close(timeout_s=timeout)
            except TypeError:
                try:
                    cleanup = close()
                except Exception:
                    return False
            except Exception:
                return False
            return cls._cleanup_complete(cleanup)
        cls._close_pipe(getattr(process, "stdin", None))
        cls._call_process(process, "terminate")
        process_ok = cls._wait_process(process, timeout)
        if not process_ok:
            cls._call_process(process, "kill")
            process_ok = cls._wait_process(process, timeout)
        return process_ok

    @staticmethod
    def _call_process(process, method: str) -> None:
        fn = getattr(process, method, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    @staticmethod
    def _wait_process(process, timeout: float) -> bool:
        wait = getattr(process, "wait", None)
        if not callable(wait):
            return False
        try:
            wait(timeout=timeout)
            return True
        except (TimeoutError, TypeError):
            return False
        except Exception:
            return False

    @staticmethod
    def _cleanup_complete(cleanup) -> bool:
        fields = ("exited", "job_closed", "stderr_drain_complete")
        if all(hasattr(cleanup, field) for field in fields):
            return all(bool(getattr(cleanup, field)) for field in fields)
        return cleanup is not False

    @staticmethod
    def _close_pipe(pipe) -> None:
        close = getattr(pipe, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
