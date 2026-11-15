from __future__ import annotations


class BootstrapRuntimeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


__all__ = ["BootstrapRuntimeError"]
