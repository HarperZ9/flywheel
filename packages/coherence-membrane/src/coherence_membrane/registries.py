"""In-code registries that resolve a memory's serialized references back to callables.

A MemoryRecord stores only names+versions (it is JSON-serialisable). At recall time
these registries map a criterion_ref -> Criterion and a perceive_ref -> perceive fn.
An unregistered reference resolves to None, which the freshness check treats as
UNVERIFIABLE (fail-closed). Stdlib only.
"""
from __future__ import annotations

from typing import Callable

from .reconcile import Criterion


class CriterionRegistry:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], Criterion] = {}

    def register(self, criterion: Criterion, *, version: str) -> None:
        key = (criterion.name, version)
        existing = self._by_key.get(key)
        if existing is not None and existing is not criterion:
            raise ValueError(
                f"version collision: ({criterion.name!r},{version!r}) already bound to a different criterion"
            )
        self._by_key[key] = criterion

    def get(self, name: str, version: str) -> Criterion | None:
        return self._by_key.get((name, version))


class PerceiverRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None:
        self._by_name[name] = fn

    def get(self, name: str) -> Callable | None:
        return self._by_name.get(name)
