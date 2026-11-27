"""A software secure element for tests and simulation.

It stands in for a discrete secure element. The device key is derived
DICE-style from a unique device secret and the firmware measurement, so a
firmware change yields a new key (SPEC.md section 3.1). The class exposes no
method that returns the private key. ``snapshot`` and ``restore`` exist only
so red-team tests can simulate a storage rollback attack.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Callable

from ..crypto import Ed25519Signer


class SoftwareSecureElement:
    name = "software-secure-element"

    def __init__(self, fw_measurement: str, clock: Callable[[], float] | None = None,
                 uds: bytes | None = None) -> None:
        self._uds = uds or os.urandom(32)
        self.fw_measurement = fw_measurement
        seed = hmac.new(self._uds, bytes.fromhex(fw_measurement), hashlib.sha256).digest()
        self._signer = Ed25519Signer.from_seed(seed)
        self._counter = 0
        self._clock = clock or time.monotonic
        self._t0 = self._clock()
        self._boot = 1
        self._floor: int | None = None
        self._tamper = False
        self._telemetry: dict | None = None

    def device_signer(self) -> Ed25519Signer:
        return self._signer

    def counter_read(self) -> int:
        return self._counter

    def counter_increment(self) -> int:
        self._counter += 1
        return self._counter

    def elapsed_ms(self) -> int:
        return int((self._clock() - self._t0) * 1000)

    def boot_id(self) -> int:
        return self._boot

    def time_floor_read(self) -> int | None:
        """The last working time the device stored; it survives a power cycle."""
        return self._floor

    def time_floor_write(self, t_ms: int) -> None:
        """Raise the stored floor; it never moves down."""
        if self._floor is None or t_ms > self._floor:
            self._floor = t_ms

    def power_cycle(self) -> None:
        """Simulate power loss: the elapsed timer restarts, the boot id moves."""
        self._t0 = self._clock()
        self._boot += 1

    def trip_tamper(self) -> None:
        """Simulate the enclosure switch or tamper mesh firing."""
        self._tamper = True

    def tamper_fired(self) -> bool:
        return self._tamper

    def clear_tamper_after_inspection(self) -> None:
        self._tamper = False

    def set_telemetry(self, value: dict | None) -> None:
        self._telemetry = value

    def telemetry(self) -> dict | None:
        return self._telemetry

    def snapshot(self) -> dict:
        """Attack simulation only: copy the counter storage."""
        return {"counter": self._counter}

    def restore(self, snap: dict) -> None:
        """Attack simulation only: roll the counter storage back."""
        self._counter = snap["counter"]

    def reflash(self, fw_measurement: str) -> None:
        """Simulate new firmware: the DICE derivation gives a new key."""
        self.fw_measurement = fw_measurement
        seed = hmac.new(self._uds, bytes.fromhex(fw_measurement), hashlib.sha256).digest()
        self._signer = Ed25519Signer.from_seed(seed)

    def describe(self) -> dict:
        part = {"source": "software", "reason": "simulation backend"}
        return {"backend": self.name, "key": part, "counter": part, "timer": part,
                "time_floor": part, "tamper": part, "telemetry": part}

    def close(self) -> None:
        return None
