"""The real-hardware backend for this Windows machine.

Parts that run on real hardware, when available:
- device key: a non-exportable ECDSA P-256 key in the TPM, through the
  Microsoft Platform Crypto Provider;
- elapsed timer and boot identifier: the TPM clock, via TPM2_ReadClock;
- telemetry: coarse power and utilization bands from nvidia-smi.

Parts that fall back to the software element, with the reason recorded:
- monotonic counter and time floor: a TPM NV counter needs an NV index defined under the
  owner hierarchy, whose authorization Windows holds; defining one would also
  change this machine's TPM state, which the prototype does not do;
- tamper sensor: this PC has no enclosure switch or tamper mesh wired to
  anything the prototype can read.

If a TPM part fails, ``describe()`` records the exact call and status code
and that part falls back to software.
"""

from __future__ import annotations

import time

from . import nvidia
from .software import SoftwareSecureElement
from .tpm_ncrypt import TpmClock, TpmError, TpmKey

COUNTER_REASON = ("TPM NV counter not attempted: defining an NV index needs owner "
                  "authorization that Windows holds, and would change the TPM's state")
FLOOR_REASON = ("time floor kept in software: TPM NV storage needs owner authorization "
                "that Windows holds, as for the counter")
TAMPER_REASON = "no tamper mesh or enclosure switch on this machine; simulated switch"


class WindowsTpmBackend:
    name = "windows-tpm"

    def __init__(self, key_name: str, fw_measurement: str) -> None:
        self._soft = SoftwareSecureElement(fw_measurement)
        self.fw_measurement = fw_measurement
        self._parts: dict[str, dict] = {}
        self._key = self._init_key(f"{key_name}-{fw_measurement[:12]}")
        self._clock = self._init_clock()
        self._parts["counter"] = {"source": "software", "reason": COUNTER_REASON}
        self._parts["time_floor"] = {"source": "software", "reason": FLOOR_REASON}
        self._parts["tamper"] = {"source": "software", "reason": TAMPER_REASON}

    def _init_key(self, name: str) -> TpmKey | None:
        try:
            key = TpmKey(name)
        except (TpmError, OSError) as exc:
            self._parts["key"] = {"source": "software", "reason": f"TPM key failed: {exc}"}
            return None
        impl = key.dword_property("Impl Type", provider=True)
        self._parts["key"] = {
            "source": "tpm", "provider": "Microsoft Platform Crypto Provider",
            "alg": key.alg, "key_name": name, "created_now": key.created,
            "impl_type_hardware_flag": None if impl is None else bool(impl & 1),
            "export_policy": key.dword_property("Export Policy"),
            "private_export_attempt": key.private_export_refused(),
        }
        return key

    def _init_clock(self) -> TpmClock | None:
        try:
            clk = TpmClock()
            first = clk.read()
        except (TpmError, OSError) as exc:
            self._parts["timer"] = {"source": "software", "reason": f"TPM clock failed: {exc}"}
            return None
        self._parts["timer"] = {"source": "tpm", "call": "TPM2_ReadClock",
                                "reset_count": first["reset_count"], "safe": first["safe"]}
        return clk

    def device_signer(self):
        return self._key if self._key is not None else self._soft.device_signer()

    def counter_read(self) -> int:
        return self._soft.counter_read()

    def counter_increment(self) -> int:
        return self._soft.counter_increment()

    def elapsed_ms(self) -> int:
        if self._clock is not None:
            return self._clock.read()["time_ms"]
        return int(time.monotonic() * 1000)

    def boot_id(self) -> int:
        if self._clock is not None:
            return self._clock.read()["reset_count"]
        return self._soft.boot_id()

    def time_floor_read(self) -> int | None:
        return self._soft.time_floor_read()

    def time_floor_write(self, t_ms: int) -> None:
        self._soft.time_floor_write(t_ms)

    def trip_tamper(self) -> None:
        self._soft.trip_tamper()

    def tamper_fired(self) -> bool:
        return self._soft.tamper_fired()

    def telemetry(self) -> dict | None:
        reading = nvidia.read_coarse()
        self._parts["telemetry"] = ({"source": "nvidia-smi", "fields": "power.draw,utilization.gpu"}
                                    if reading else {"source": "none",
                                                     "reason": "nvidia-smi unavailable"})
        return reading

    def describe(self) -> dict:
        self._parts.setdefault("telemetry", {"source": "not read yet"})
        return {"backend": self.name, **self._parts}

    def close(self, delete_key: bool = True) -> None:
        if self._key is not None:
            if delete_key:
                self._key.delete()
            else:
                self._key.close()
        if self._clock is not None:
            self._clock.close()
