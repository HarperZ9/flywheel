"""Negative control: a deliberately weak shim (SPEC.md section 16.2, drill 2).

It skips checks 4 to 6, so it accepts an order that no log holds. It exists
only so the daily recheck can be shown to catch it. A checker that reads
MATCH for its receipts fails the drill.
"""

from __future__ import annotations

from .device import Device
from .shim import Refusal, _apply, _check1, _check2_3


def weak_receive(dev: Device, pkg: dict) -> dict:
    try:
        msg = _check1(pkg.get("order_bytes") or pkg.get("order"))
        _check2_3(dev, msg)
    except Refusal as err:
        return {"status": "refused", "check": err.check, "reason": err.reason}
    return _apply(dev, msg)
