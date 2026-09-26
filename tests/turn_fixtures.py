"""Shared helpers for the turn-capture tests: a TurnStore on a temporary home
with the stdlib test provider, a movable clock, and receipt readers."""
from __future__ import annotations

import contextlib

from harness.trace_capture_settings import DEFAULTS
from trace_enc_fakes import StreamTestProvider, using

OWNER = "owner_" + "a" * 32
SESSION = "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b"


class Clock:
    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@contextlib.contextmanager
def turn_store(home, clock=None, **settings):
    from harness.trace_turn_store import TurnStore
    (home / "state").mkdir(parents=True, exist_ok=True)
    with using(StreamTestProvider()):
        yield TurnStore(home, OWNER, clock=clock or Clock(), settings={**DEFAULTS, **settings})


def receipts(home) -> list[dict]:
    from harness.store import get_entity, query_entities
    rows = query_entities(kind="turn-receipt", home=home, limit=1000)
    return sorted((get_entity(r["eid"], home=home) for r in rows),
                  key=lambda e: e["created"])


def custody_bytes(home) -> bytes:
    return b"".join(p.read_bytes() for p in home.rglob("*") if p.is_file())
