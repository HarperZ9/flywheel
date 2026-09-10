"""Shared source-context exception type."""
from __future__ import annotations


class SourceContextError(RuntimeError):
    """One fixed source-context failure, with no private text in its message."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
