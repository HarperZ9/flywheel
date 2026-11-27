"""Logged maintenance windows (SPEC.md section 12.4; README.md Finding P55).

Routine service opens chassis. Without a window, every opening is a hard
tamper signal whose restoration needs an inspection record and K_RESTORE
seat signatures, so seven people would sit inside every repair loop. With a
window, the operator logs, before it opens a chassis, which devices, why and
which technician. A tamper event inside a window the device accepted fails
that device closed with the reason ``maintenance_tamper``, which is not a
hard signal. Restoration then needs a registered inspector's record and a
fresh attestation (the running firmware in the reference set, the tamper
sensor clear), and no seat vote. A tamper event outside every window keeps
the K_RESTORE rule.

The device limits windows to MAINT_RATE per device per 30 days (PH-S). A
per-operator limit is a check the seats run on the log, and this module
does not model it.
"""

from __future__ import annotations

from .crypto import envelope, valid_signers
from .proofs import verify_in_logs

MAINT_TYPE = "maintenance-window"
RATE_SPAN_MS = 30 * 86_400_000


def window_msg(operator, operator_id: str, device_keys: list[str], reason_fp: str,
               technician_fp: str, opens_ms: int, closes_ms: int) -> dict:
    body = {"operator_id": operator_id, "device_keys": sorted(device_keys),
            "reason_fp": reason_fp, "technician_fp": technician_fp,
            "opens_ms": opens_ms, "closes_ms": closes_ms}
    return envelope(MAINT_TYPE, body, [operator])


def accept_window(dev, msg: dict, bundles: list[dict]) -> tuple[bool, str]:
    body = msg.get("body", {}) if isinstance(msg, dict) else {}
    if msg.get("type") != MAINT_TYPE or dev.key not in body.get("device_keys", []):
        return False, "not a maintenance window naming this device"
    if not set(valid_signers(msg)) & dev.trust.operator_keys:
        return False, "window not signed by the registered operator"
    opens, closes = body.get("opens_ms"), body.get("closes_ms")
    if not (isinstance(opens, int) and isinstance(closes, int)) or closes <= opens:
        return False, "window times are malformed"
    if closes - opens > dev.params.maint_window * 1000:
        return False, "window longer than MAINT_WINDOW"
    now = dev.t_work()
    if now is None or closes < now:
        return False, "no working time, or the window already closed"
    recent = [t for t in dev.maint_log if now - t < RATE_SPAN_MS]
    if len(recent) >= dev.params.maint_rate:
        return False, "MAINT_RATE windows already used in the last 30 days"
    res = verify_in_logs(msg, bundles, dev.trust.policy, dev.view)
    if not res.ok:
        return False, f"window not proven in the logs: {res.reason}"
    dev.windows.append(body)
    dev.maint_log.append(now)
    return True, "ok"


def in_window(dev, now: int | None) -> bool:
    return now is not None and any(w["opens_ms"] <= now <= w["closes_ms"] for w in dev.windows)


def restore(dev, inspection: dict) -> tuple[bool, str]:
    """Restoration after a tamper event inside a window: inspection plus attestation."""
    if dev.failed != "maintenance_tamper":
        return False, "not failed closed inside a maintenance window"
    inspectors = set(valid_signers(inspection)) & dev.trust.inspector_keys
    if inspection.get("type") != "inspection" or not inspectors:
        return False, "no inspection record signed by a registered inspector"
    if dev.backend.tamper_fired():
        return False, "tamper sensor still reads fired"
    if dev.backend.fw_measurement not in dev.trust.reference_fw:
        return False, "fresh attestation fails: firmware not in the reference set"
    dev.failed, dev.tamper_counter = None, None
    dev._enforce()
    dev.outbox.append(dev.sign("restored", {"device_key": dev.key, "from": "maintenance_tamper",
                                            "at_ms": dev.t_work(),
                                            "counter": dev.backend.counter_read()}))
    return True, "ok"
