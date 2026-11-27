"""Device-side checks added after the outside review of 25 September 2026.

Kept out of device.py so that module stays readable. Each function takes
the device and returns a refusal reason, or None when the check passes.
"""

from __future__ import annotations

from .canon import fingerprint
from .crypto import msg_id
from .proofs import verify_in_logs
from .seats import Roster


def renewal_span_refusal(dev, body: dict) -> str | None:
    """A renewal may not outlast RENEWAL_VALIDITY or start in the future (SPEC 7.1)."""
    start, end = body.get("valid_from_ms"), body.get("valid_until_ms")
    if not (isinstance(start, int) and isinstance(end, int)):
        return "renewal validity fields are malformed"
    if end <= start or end - start > dev.params.renewal_validity * 1000:
        return "renewal validity exceeds RENEWAL_VALIDITY"
    now = dev.t_work()
    if now is None:
        return "no trustworthy working time"
    if start > now + dev.params.time_tol * 1000:
        return "renewal starts after working time plus TIME_TOL"
    if end < now:
        return "renewal already expired"
    return None


def adopt_roster(dev, msg: dict, bundles: list[dict]) -> tuple[bool, str]:
    """Adopt a successor roster only under the roster rules, including K_REMOVE
    for any seat it drops, and only once it is proven in LOGS_MIN logs (check 2)."""
    p = dev.params
    ok, why = dev.trust.roster.accepts_successor(
        msg, p.k_order, p.n_seats, p.min_signer_regions, p.max_per_region, k_remove=p.k_remove)
    if not ok:
        return False, why
    res = verify_in_logs(msg, bundles, dev.trust.policy, dev.view)
    if not res.ok:
        return False, f"roster not proven in the logs: {res.reason}"
    dev.trust.roster = Roster(msg)
    return True, "ok"


def note_location(dev, records: list[dict]) -> str:
    """Set the heartbeat's location claim from the latest measurement set that
    names this device (SPEC 10.1)."""
    mine = sorted(msg_id(r) for r in records
                  if isinstance(r, dict) and r.get("body", {}).get("device_key") == dev.key)
    if mine:
        dev.location_fp = fingerprint("loc-set", mine)
    return dev.location_fp
