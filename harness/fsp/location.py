"""Location by signal delay against simulated landmarks (SPEC.md section 10).

The only statement checked is an upper bound: the key holder answered from
within r = c * RTT / 2 of the landmark, with c the speed of light in vacuum.
Round-trip times are simulated from great-circle distance at two thirds of
c, as in fibre, plus processing and any added delay. A drill here tests the
rule, not the physics.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Callable

from .canon import canon, tag
from .crypto import Ed25519Signer, envelope, valid_signers, verify

C = 299_792_458            # m/s, exact by definition (NIST CODATA)
MEDIUM = C * 2 / 3         # simulated propagation speed in fibre
EARTH_R = 6_371_000


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def bound_m(rtt_s: float) -> float:
    return C * rtt_s / 2


@dataclass
class Responder:
    """Whoever holds a device key and answers the challenge, at a position."""
    signer: object
    position: tuple[float, float]


class Landmark:
    def __init__(self, landmark_id: str, party: str, position: tuple[float, float],
                 radius_m: float, clock: Callable[[], float] | None = None) -> None:
        self.landmark_id, self.party, self.position = landmark_id, party, position
        self.radius_m = radius_m
        self.signer = Ed25519Signer()
        # Stands in for the landmark's own time quorum (SPEC.md section 6).
        self.clock = clock or time.time

    def measure(self, device_key: str, responder: Responder, counter: int,
                relay: tuple[float, float] | None = None, added_delay_s: float = 0.0,
                processing_s: float = 0.0002) -> dict | None:
        # Physics allows delay to be added and never removed (SPEC.md 10.3), so
        # the simulator refuses a negative delay rather than report a false pass.
        if added_delay_s < 0 or processing_s < 0:
            raise ValueError("added delay and processing time cannot be negative")
        nonce = os.urandom(16).hex()
        message = tag("loc") + canon({"nonce": nonce, "counter": counter})
        sig = responder.signer.sign(message).hex()
        if not verify(responder.signer.alg, device_key, message, sig):
            return None
        if relay is None:
            path = distance_m(self.position, responder.position)
        else:
            path = distance_m(self.position, relay) + distance_m(relay, responder.position)
        rtt = 2 * path / MEDIUM + processing_s + added_delay_s
        body = {"landmark": self.landmark_id, "device_key": device_key, "nonce": nonce,
                "rtt_us": int(rtt * 1e6), "bound_m": int(bound_m(rtt)),
                "radius_m": int(self.radius_m), "measured_ms": int(self.clock() * 1000)}
        return envelope("loc-measurement", body, [self.signer])


def _usable(rec, by_id: dict, device_key: str | None, now_ms: int | None,
            max_age_s: int) -> bool:
    if not isinstance(rec, dict):
        return False
    body = rec.get("body", {})
    lm = by_id.get(body.get("landmark"))
    if lm is None or lm.signer.public_hex() not in valid_signers(rec):
        return False
    if device_key is not None and body.get("device_key") != device_key:
        return False
    if now_ms is not None and now_ms - body.get("measured_ms", -1) > max_age_s * 1000:
        return False
    return True


def region_check(landmarks: list[Landmark], records: list[dict], landmarks_min: int,
                 device_key: str | None = None, now_ms: int | None = None,
                 max_age_s: int = 6 * 3600) -> dict:
    """Pass when a region with enough landmarks and parties bounds the named device.

    ``verdict`` reads PASS, FAIL or UNVERIFIABLE. A region below
    LANDMARKS_MIN landmarks or 2 parties reads UNVERIFIABLE, never a fail,
    and an UNVERIFIABLE reading never counts toward convergence (SPEC.md
    10.2). With ``device_key``, only records naming that device count; with
    ``now_ms``, only records measured within ``max_age_s`` (LOC_INTERVAL).
    Without ``device_key`` every counted record must name one device, and the
    result names it, so a caller cannot read a pass as another device's.
    """
    parties = {lm.party for lm in landmarks}
    if len(landmarks) < landmarks_min or len(parties) < 2:
        return {"pass": False, "verdict": "UNVERIFIABLE", "device_key": device_key,
                "reason": "region lacks LANDMARKS_MIN landmarks or 2 parties"}
    by_id = {lm.landmark_id: lm for lm in landmarks}
    usable = [r for r in records if _usable(r, by_id, device_key, now_ms, max_age_s)]
    named = {r["body"]["device_key"] for r in usable}
    if len(named) > 1:
        return {"pass": False, "verdict": "UNVERIFIABLE", "device_key": None,
                "reason": "records name more than one device; name the device to check"}
    who = device_key or (named.pop() if named else None)
    for rec in usable:
        lm = by_id[rec["body"]["landmark"]]
        if rec["body"]["bound_m"] <= lm.radius_m:
            return {"pass": True, "verdict": "PASS", "device_key": who,
                    "reason": f"within {int(lm.radius_m)} m of {lm.landmark_id}"}
    return {"pass": False, "verdict": "FAIL", "device_key": who,
            "reason": "no landmark bounds the device inside its radius; "
                      "a soft signal, never a hard one"}
