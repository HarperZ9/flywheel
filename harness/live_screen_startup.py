"""Fail-closed startup for live-screen capture sources."""

from __future__ import annotations

from .live_screen_types import fail


def start_session_sources(manager, session) -> None:
    session.capture_sources = {}
    session.iterators = {}
    try:
        for sid in session.source_ids:
            source = manager._sources[sid].factory()
            session.capture_sources[sid] = source
            session.iterators[sid] = iter(source.frames())
    except Exception as exc:
        manager._release_session(session)
        detail = " ".join(str(exc).split())[:120]
        suffix = f": {detail}" if detail else ""
        fail("SOURCE_START_FAILED", "live screen source failed to start" + suffix)
