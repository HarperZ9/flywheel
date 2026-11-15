from __future__ import annotations

from dataclasses import dataclass

from .receipts import GuardrailReceipt


@dataclass(frozen=True)
class GuardedTextResult:
    text: str
    receipt: GuardrailReceipt


@dataclass(frozen=True)
class GuardedExecResult:
    stdout: str
    stderr: str
    returncode: int
    receipt: GuardrailReceipt


@dataclass(frozen=True)
class GuardedFetchResult:
    text: str
    status_code: int
    receipt: GuardrailReceipt
