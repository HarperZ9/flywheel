"""Roughtime-style secure time with a quorum (SPEC.md section 6).

Servers are simulated in process. A client queries them in a chain where
each nonce is the hash of the previous signed reply and a fresh blind, so
the order of replies is provable. Querying the server list twice puts each
server both before and after every other one, so a server that is fast or
slow by more than the radii yields a signed malfeasance proof. A quorum is
K_TIME replies whose pairwise spread is at most TIME_TOL, from at least two
parties (Finding P42: an earlier version grouped replies around an anchor,
which let members sit up to 2 x TIME_TOL apart).

The first blind of a chain may come from the device (SPEC.md Finding S43). A device
then checks that ``chain[0]["blind"]`` is a nonce it issued, so a chain
recorded earlier cannot be replayed to it.
"""

from __future__ import annotations

import hashlib
import os
import statistics
from dataclasses import dataclass
from typing import Callable

from .canon import canon, fingerprint
from .crypto import Ed25519Signer, envelope, signed_by
from .log import ms


class TimeServer:
    def __init__(self, server_id: str, party: str, jurisdiction: str,
                 clock: Callable[[], float], radius_ms: int = 1000) -> None:
        self.server_id, self.party, self.jurisdiction = server_id, party, jurisdiction
        self.clock = clock
        self.radius_ms = radius_ms
        self.offset_ms = 0            # red-team knob: a lying server
        self.signer = Ed25519Signer()

    @property
    def key(self) -> str:
        return self.signer.public_hex()

    def respond(self, nonce: str) -> dict:
        body = {"server": self.server_id, "nonce": nonce,
                "midpoint_ms": ms(self.clock()) + self.offset_ms, "radius_ms": self.radius_ms}
        return envelope("time", body, [self.signer])


def _next_nonce(prev: dict | None, blind: bytes) -> str:
    base = canon(prev) if prev is not None else b"fsp/v0/time-chain-start"
    return hashlib.sha256(base + blind).hexdigest()


def query_chain(servers: list[TimeServer], passes: int = 2,
                first_blind: bytes | None = None) -> list[dict]:
    """Chain query; each entry keeps its blind so anyone can recheck the links.

    ``first_blind`` is the device's own nonce, when a device asks for time.
    """
    chain: list[dict] = []
    prev = None
    for i, server in enumerate(servers * passes):
        blind = first_blind if (i == 0 and first_blind is not None) else os.urandom(16)
        reply = server.respond(_next_nonce(prev, blind))
        chain.append({"reply": reply, "blind": blind.hex()})
        prev = reply
    return chain


def chain_links_valid(chain: list[dict], keys: dict[str, str]) -> bool:
    prev = None
    for link in chain:
        reply = link["reply"]
        server = reply["body"]["server"]
        if server not in keys or not signed_by(reply, keys[server]):
            return False
        if reply["body"]["nonce"] != _next_nonce(prev, bytes.fromhex(link["blind"])):
            return False
        prev = reply
    return True


def malfeasance(chain: list[dict], keys: dict[str, str]) -> dict | None:
    """A later reply earlier than an earlier reply, beyond both radii, is a proof."""
    if not chain_links_valid(chain, keys):
        return None
    for i, a in enumerate(chain):
        ab = a["reply"]["body"]
        for b in chain[i + 1:]:
            bb = b["reply"]["body"]
            if bb["midpoint_ms"] + bb["radius_ms"] < ab["midpoint_ms"] - ab["radius_ms"]:
                return {"chain": chain, "earlier": ab["server"], "later": bb["server"]}
    return None


@dataclass
class TimeQuorum:
    t_ms: int
    servers: list[str]
    fp: str


def form_quorum(chain: list[dict], keys: dict[str, str], parties: dict[str, str],
                k_time: int, tol_s: int) -> TimeQuorum | None:
    """Latest reply per server; the largest agreeing set must have k and 2 parties."""
    if not chain_links_valid(chain, keys):
        return None
    latest: dict[str, int] = {}
    for link in chain:
        body = link["reply"]["body"]
        latest[body["server"]] = body["midpoint_ms"]
    best: list[str] = []
    ordered = sorted(latest.items(), key=lambda item: item[1])
    for i, (_s, low) in enumerate(ordered):
        group = [s for s, t in ordered[i:] if t - low <= tol_s * 1000]
        if len(group) > len(best):
            best = group
    if len(best) < k_time or len({parties[s] for s in best}) < 2:
        return None
    t = int(statistics.median(latest[s] for s in best))
    fp = fingerprint("time-quorum", {"t_ms": t, "servers": sorted(best),
                                     "chain": [fingerprint("time", c["reply"]["body"])
                                               for c in chain]})
    return TimeQuorum(t, sorted(best), fp)
