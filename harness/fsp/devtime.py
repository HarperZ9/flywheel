"""The device time rule (SPEC.md section 6; Findings S43, S44, P40 and P41).

A device accepts a time quorum only when:

- the chain starts from a nonce the device itself issued in this boot, no
  more than TIME_TOL of its own timer ago, so a chain recorded earlier, or
  held back by a carrier, cannot be replayed to it (S43);
- after a boot, the quorum is not earlier than the time floor the device
  stored before it lost power, minus TIME_TOL (S43);
- while the boot id is unchanged, the quorum is neither earlier than working
  time minus TIME_TOL nor later than working time plus TIME_TOL plus the
  timer's drift bound, DRIFT_PPM of the elapsed time (S44).

A refused forward jump goes out as signed device evidence. Unlike a chained
malfeasance proof it rests on the device's own timer, so it is evidence and
not a proof a third party can check alone.
"""

from __future__ import annotations

import os

from .canon import fingerprint
from .timesrc import form_quorum, malfeasance


def new_nonce(dev) -> str:
    """A fresh nonce from the device's own RNG; one chain may use it once."""
    nonce = os.urandom(16).hex()
    dev.time_nonces.append({"nonce": nonce, "boot": dev.backend.boot_id(),
                            "elapsed_ms": dev.backend.elapsed_ms()})
    return nonce


def _take_nonce(dev, nonce: str) -> str | None:
    """Consume the nonce; the reason it is not usable, or None."""
    rec = next((r for r in dev.time_nonces if r["nonce"] == nonce), None)
    if rec is None:
        return "chain does not start from a nonce this device issued"
    dev.time_nonces.remove(rec)
    if rec["boot"] != dev.backend.boot_id():
        return "chain answers a nonce issued before the last boot"
    if dev.backend.elapsed_ms() - rec["elapsed_ms"] > dev.params.time_tol * 1000:
        return "chain answers a nonce older than TIME_TOL"
    return None


def _report_proof(dev, chain: list[dict]) -> None:
    proof = malfeasance(chain, dev.trust.time_keys)
    if proof is not None:
        dev.outbox.append(dev.sign("time-malfeasance", {
            "device_key": dev.key, "kind": "chained", "earlier": proof["earlier"],
            "later": proof["later"], "chain_fp": fingerprint("time-chain", proof["chain"])}))


def _bound_refusal(dev, q_ms: int, chain: list[dict]) -> str | None:
    """The reason a quorum falls outside what the device's own clock allows."""
    tol = dev.params.time_tol * 1000
    now = dev.t_work()
    if now is None:
        floor = dev.backend.time_floor_read()
        if floor is not None and q_ms < floor - tol:
            return "quorum earlier than the time floor stored before boot"
        return None
    if q_ms < now - tol:
        return "quorum earlier than working time; time never moves backward"
    since = max(0, dev.backend.elapsed_ms() - dev.quorum["elapsed_ms"])
    ahead = tol + dev.params.drift_ppm * since // 1_000_000
    if q_ms > now + ahead:
        dev.outbox.append(dev.sign("time-malfeasance", {
            "device_key": dev.key, "kind": "forward_jump", "quorum_ms": q_ms,
            "t_work_ms": now, "allowed_ahead_ms": ahead,
            "chain_fp": fingerprint("time-chain", chain)}))
        return "quorum ahead of the running timer by more than TIME_TOL plus drift"
    return None


def accept_time(dev, chain: list[dict]) -> tuple[bool, str]:
    try:
        first = chain[0]["blind"]
    except (IndexError, KeyError, TypeError):
        return False, "malformed time chain"
    why = _take_nonce(dev, first)
    if why is not None:
        return False, why
    try:
        _report_proof(dev, chain)
        q = form_quorum(chain, dev.trust.time_keys, dev.trust.time_parties,
                        dev.params.k_time, dev.params.time_tol)
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"malformed time chain: {type(exc).__name__}"
    if q is None:
        return False, "no quorum"
    why = _bound_refusal(dev, q.t_ms, chain)
    if why is not None:
        return False, why
    dev.quorum = {"t_ms": q.t_ms, "elapsed_ms": dev.backend.elapsed_ms(),
                  "boot": dev.backend.boot_id(), "fp": q.fp}
    dev.backend.time_floor_write(q.t_ms)
    return True, "ok"


def raise_floor(dev) -> None:
    """Store working time as the floor; called on heartbeats and self-checks."""
    now = dev.t_work()
    if now is not None:
        dev.backend.time_floor_write(now)
