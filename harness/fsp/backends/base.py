"""The hardware backend interface a device model runs on.

A backend supplies six things the protocol assumes live in tamper-evident
hardware: a non-exportable device signing key, a monotonic counter, a
monotonic elapsed timer with a boot identifier, a time floor that survives a
power cycle (SPEC.md Finding S43), a tamper sensor, and coarse telemetry.
``describe()`` states, part by part, what is real hardware and what is a
software stand-in, with the reason for each stand-in.
"""

from __future__ import annotations

from typing import Protocol

from ..crypto import Signer


class HardwareBackend(Protocol):
    name: str

    def device_signer(self) -> Signer: ...

    def counter_read(self) -> int: ...

    def counter_increment(self) -> int: ...

    def elapsed_ms(self) -> int: ...

    def boot_id(self) -> int: ...

    def time_floor_read(self) -> int | None: ...

    def time_floor_write(self, t_ms: int) -> None: ...

    def tamper_fired(self) -> bool: ...

    def telemetry(self) -> dict | None: ...

    def describe(self) -> dict: ...

    def close(self) -> None: ...
