"""Shared proposer observation: deadline, call budget, and usage slots."""
from __future__ import annotations

from typing import Callable


class ObservedProposer:
    def __init__(self, inner, timeout: float, clock: Callable,
                 response_model_attested: bool = False, max_calls: int | None = None, *, observer=None):
        self.inner, self.model_ref, self.observed = inner, inner.model_ref, ""
        self.usage_records, self.basis = [], "unknown"
        self.response_model_attested = response_model_attested
        self.clock, self.deadline, self.max_calls, self.calls = clock, clock() + timeout, max_calls, 0
        self.observer = observer

    def remaining_seconds(self) -> float:
        return self.deadline - self.clock()

    def remaining_calls(self) -> "int | None":
        return None if self.max_calls is None else max(0, self.max_calls - self.calls)

    def _generate_from(self, proposer, *args, **kwargs):
        if self.observer is not None:
            self.observer.check()
        remaining = self.remaining_seconds()
        if remaining <= 0:
            raise TimeoutError("shared attempt deadline expired")
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise TimeoutError(
                f"inner proposer invocation budget exhausted: proposer_invocations_max={self.max_calls}")
        invocation = self.observer.started(kwargs.get("max_new_tokens")) if self.observer is not None else None
        self.calls += 1
        self.usage_records.append(None)
        backend = getattr(proposer, "backend", None)
        if backend is not None and hasattr(backend, "timeout"):
            backend.timeout = min(backend.timeout, remaining)
        try:
            out = proposer.generate(*args, **kwargs)
        except BaseException as exc:
            if self.observer is not None:
                self.observer.check()
                evidence = getattr(exc, "evidence", None)
                usage = evidence.get("native_usage") if isinstance(evidence, dict) else None
                self.observer.finished(invocation, "raised", usage)
            raise
        self.usage_records[-1] = getattr(out, "usage", None)
        if self.observer is not None:
            self.observer.check()
            self.observer.finished(invocation, "returned", getattr(out, "usage", None))
        if self.clock() >= self.deadline:
            raise TimeoutError("shared attempt deadline expired")
        self.observed = out.served_model or (
            out.model_ref if self.response_model_attested else "")
        self.basis = ("structured_provider_event" if out.served_model else
                      "structured_provider_response" if self.observed else "unknown")
        return out

    def generate(self, *args, **kwargs):
        return self._generate_from(self.inner, *args, **kwargs)

    def generate_with(self, proposer, *args, **kwargs):
        return self._generate_from(proposer, *args, **kwargs)
