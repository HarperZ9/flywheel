"""Bounded cleanup for live-screen source resources."""

from __future__ import annotations


def close_session_resources(session, *, limit: int = 4) -> list[str]:
    errors: list[str] = []
    seen: set[int] = set()
    for sid, resource in list(session.iterators.items()):
        _close_one(errors, seen, sid, "iterator", resource, limit)
    for sid, resource in list(session.capture_sources.items()):
        _close_one(errors, seen, sid, "source", resource, limit)
    session.iterators.clear()
    session.capture_sources.clear()
    return errors


def _close_one(errors: list[str], seen: set[int], sid: str, role: str,
               resource, limit: int) -> None:
    if resource is None or id(resource) in seen:
        return
    seen.add(id(resource))
    close = getattr(resource, "close", None)
    if not callable(close):
        close = getattr(resource, "__exit__", None)
        if callable(close):
            def close(close=close):
                return close(None, None, None)
    if not callable(close):
        return
    try:
        close()
    except Exception as exc:  # cleanup failure must not strand reservations
        if len(errors) < limit:
            message = " ".join(str(exc).split())[:120]
            errors.append(f"{sid} {role} close {type(exc).__name__}: {message}")
