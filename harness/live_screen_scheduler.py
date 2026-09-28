"""Background producer lifecycle for admitted live-screen sessions."""

from __future__ import annotations

import threading
import time

from .live_screen_feed import LiveScreenError, LiveScreenManager
from .live_screen_types import check_id


class LiveScreenProducerScheduler:
    def __init__(self, manager: LiveScreenManager, *, clock_ns=time.monotonic_ns,
                 tick_interval_ms: int = 250):
        self.manager = manager
        self.clock_ns = clock_ns
        self.tick_interval_s = max(0.001, tick_interval_ms / 1000)
        self.active: dict[tuple[str, str], bool] = {}
        self.bindings: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def bind_session(self, session_id: str, *, session_ref: str, instrument_ref: str) -> None:
        self.bindings[check_id(session_id, "session_id")] = {
            "session_ref": check_id(session_ref, "session_ref"),
            "instrument_ref": check_id(instrument_ref, "instrument_ref"),
        }

    def start(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> list[dict]:
        with self._lock:
            self.active[(session_id, owner_ref)] = True
            self._ensure_loop()
        events = self.tick(session_id, owner_ref=owner_ref, now_ns=now_ns)
        self._wake.set()
        return events

    def pause(self, session_id: str, *, owner_ref: str) -> None:
        with self._lock:
            self.active[(session_id, owner_ref)] = False

    def stop(self, session_id: str, *, owner_ref: str) -> None:
        with self._lock:
            self.active.pop((session_id, owner_ref), None)

    def cleanup_expired(self, *, owner_ref: str, now_ns: int) -> int:
        stopped = 0
        sessions = list(getattr(self.manager, "_sessions", {}).items())
        for session_id, session in sessions:
            if session.owner_ref != owner_ref or session.state == "stopped" or now_ns < session.expires_at_ns:
                continue
            self.stop(session_id, owner_ref=owner_ref)
            try:
                self.manager.stop_session(session_id, owner_ref=owner_ref, now_ns=now_ns)
                stopped += 1
            except LiveScreenError:
                pass
        return stopped

    def tick(self, session_id: str, *, owner_ref: str, now_ns: int | None = None) -> list[dict]:
        with self._lock:
            if not self.active.get((session_id, owner_ref), False):
                return []
            now_ns = self.clock_ns() if now_ns is None else now_ns
            try:
                return self.manager.producer_tick(session_id, owner_ref=owner_ref, now_ns=now_ns)
            except LiveScreenError as exc:
                if exc.code in {"SCREEN_SHARE_EXPIRED", "SESSION_NOT_ACTIVE", "SESSION_STOPPED"}:
                    self.stop(session_id, owner_ref=owner_ref)
                    self.cleanup_expired(owner_ref=owner_ref, now_ns=now_ns)
                    return []
                raise

    def tick_all(self, *, now_ns: int | None = None) -> int:
        now_ns = self.clock_ns() if now_ns is None else now_ns
        keys = [key for key, active in list(self.active.items()) if active]
        count = 0
        for session_id, owner_ref in keys:
            count += len(self.tick(session_id, owner_ref=owner_ref, now_ns=now_ns))
        for owner_ref in {owner for _, owner in keys}:
            self.cleanup_expired(owner_ref=owner_ref, now_ns=now_ns)
        return count

    def _ensure_loop(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="flywheel-live-screen", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            self._wake.wait(self.tick_interval_s)
            self._wake.clear()
            self.tick_all()
