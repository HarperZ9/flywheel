"""Adapter from Flywheel source-context routes to Gather's path API."""
from __future__ import annotations

from pathlib import Path

from .source_context_store import SourceContextError
from .source_context_windows import SourceContextWindowsGuard

ADAPTER_VERSION = "gather.context.path-api/v1"


class GatherPathAdapter:
    """Call Gather only while Flywheel retains the protected path guard."""

    adapter_version = ADAPTER_VERSION

    def __init__(self, *, inspect_fn=None, select_fn=None,
                 guard_cls=SourceContextWindowsGuard) -> None:
        self.inspect_fn, self.select_fn = inspect_fn, select_fn
        self.guard_cls = guard_cls
        self.last_identity: dict | None = None
        self.last_identities: tuple[dict, ...] = ()

    def inspect(self, path: Path, **caps) -> dict:
        inspect_fn = self.inspect_fn or _default("inspect")
        with self.guard_cls(path) as guard:
            self._revalidate(guard)
            result = inspect_fn(path, **caps)
            self._revalidate(guard)
            self.last_identity = guard.identity()
            self.last_identities = _identities(guard)
            return result

    def select(self, path: Path, selections: list, *,
               expected_corpus_digest: str, **caps) -> dict:
        select_fn = self.select_fn or _default("select")
        with self.guard_cls(path) as guard:
            self._revalidate(guard)
            result = select_fn(
                path, selections, expected_corpus_digest=expected_corpus_digest,
                **caps)
            self._revalidate(guard)
            self.last_identity = guard.identity()
            self.last_identities = _identities(guard)
            return result

    @staticmethod
    def _revalidate(guard) -> None:
        check = getattr(guard, "revalidate", None)
        if callable(check):
            check()


def _default(kind: str):
    try:
        from gather.context import inspect_corpus, select_context
    except Exception:
        raise SourceContextError("SOURCE_CONTEXT_GATHER_UNAVAILABLE") from None
    return inspect_corpus if kind == "inspect" else select_context


def _identities(guard) -> tuple[dict, ...]:
    read = getattr(guard, "identities", None)
    return tuple(read()) if callable(read) else ()
