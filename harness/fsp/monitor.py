"""The seat-side desk: heartbeats, counters, clones, silence and standing.

Every seat receives the same device messages. The desk checks each one's
signature against the registered device key, tracks counters and the
heartbeat chain, builds clone proofs, marks devices missed after
MISSED_INTERVALS heartbeat intervals, compares gossiped checkpoints and
computes good standing for the next renewal root (SPEC.md sections 4, 7, 9.4).
"""

from __future__ import annotations

from .canon import fingerprint
from .crypto import signed_by
from .gossip import GossipDesk
from .params import Params

DEVICE_TYPES = ("heartbeat", "failclosed", "receipt", "refusal", "restored",
                "time-malfeasance")


class SeatDesk:
    def __init__(self, params: Params, reference_fw: set) -> None:
        self.params = params
        self.reference_fw = reference_fw
        self.registry: dict[str, dict] = {}        # device key -> cluster, region
        self.last: dict[str, dict] = {}            # device key -> last heartbeat info
        self.by_counter: dict[tuple[str, int], dict] = {}
        self.batch: list[str] = []
        self.missed: set[str] = set()
        self.clones: set[str] = set()
        self.open_fc: dict[str, str] = {}
        self.gossip_desk = GossipDesk()
        self.chain_breaks: set[str] = set()
        self.roots_missed: dict[str, int] = {}

    def register(self, device_key: str, cluster_id: str, region: str,
                 now_ms: int | None = None) -> None:
        """Register a device. The registration time counts as the last contact, so a
        device that never sends a heartbeat is still marked missed (P4)."""
        self.registry[device_key] = {"cluster_id": cluster_id, "region": region,
                                     "registered_ms": now_ms}

    def receive(self, msg: dict, now_ms: int) -> list[dict]:
        """Returns events: dicts with kind, device_key and evidence."""
        mtype = msg.get("type")
        key = msg.get("body", {}).get("device_key")
        if mtype not in DEVICE_TYPES or key not in self.registry or not signed_by(msg, key):
            return [{"kind": "rejected_message", "device_key": key, "evidence": {"type": mtype}}]
        if mtype == "failclosed":
            self.open_fc[key] = msg["body"]["reason"]
            return []
        if mtype == "restored":
            self.open_fc.pop(key, None)
            return []
        if mtype != "heartbeat":
            return []
        return self._heartbeat(msg, key, now_ms)

    def _heartbeat(self, msg: dict, key: str, now_ms: int) -> list[dict]:
        body = msg["body"]
        fp = fingerprint("heartbeat", body)
        events: list[dict] = []
        twin = self.by_counter.get((key, body["counter"]))
        if twin is not None and twin["fp"] != fp:
            self.clones.add(key)
            return [{"kind": "clone_proof", "device_key": key,
                     "evidence": {"a": twin["msg"], "b": msg}}]
        self.by_counter[(key, body["counter"])] = {"fp": fp, "msg": msg}
        prev = self.last.get(key)
        if prev is not None:
            if body["counter"] <= prev["counter"]:
                events.append({"kind": "counter_regression_seen", "device_key": key,
                               "evidence": {"seen": body["counter"], "prev": prev["counter"]}})
            elif body["counter"] > prev["counter"] + 1:
                events.append({"kind": "counter_gap", "device_key": key,
                               "evidence": {"from": prev["counter"], "to": body["counter"]}})
            elif body.get("prev_fp") != prev["fp"]:
                # The next heartbeat in sequence does not chain to the last one seen.
                self.chain_breaks.add(key)
                events.append({"kind": "chain_break", "device_key": key,
                               "evidence": {"a": prev["msg"], "b": msg}})
        self.last[key] = {"counter": max(body["counter"], prev["counter"] if prev else 0),
                          "fp": fp, "seen_ms": now_ms, "body": body, "msg": msg}
        self.missed.discard(key)
        self.batch.append(fp)
        events += self._gossip(key, body)
        return events

    def _gossip(self, key: str, body: dict) -> list[dict]:
        events = []
        for entry in body.get("checkpoints", []):
            ev = self.gossip_desk.observe(entry, key)
            if ev is not None:
                events.append(ev)
        return events

    def scan_missed(self, now_ms: int) -> list[dict]:
        """Mark devices missed after T_MISSED with no heartbeat, counting from the
        last heartbeat or, for a device never heard, from its registration."""
        limit = self.params.t_missed * 1000
        events = []
        for key, reg in self.registry.items():
            info = self.last.get(key)
            since = info["seen_ms"] if info else reg.get("registered_ms")
            if since is None or key in self.missed or now_ms - since < limit:
                continue
            self.missed.add(key)
            events.append({"kind": "missed_heartbeats", "device_key": key,
                           "evidence": {"last_seen_ms": since if info else None,
                                        "registered_ms": reg.get("registered_ms"),
                                        "detected_ms": now_ms}})
        return events

    def take_batch(self) -> list[str]:
        batch, self.batch = self.batch, []
        return batch

    def good_standing(self, now_ms: int) -> dict[str, str]:
        """Device key -> heartbeat fingerprint used for its blinded leaf."""
        members = {}
        epoch_ms = self.params.t_epoch * 1000
        for key, info in self.last.items():
            body = info["body"]
            if now_ms - info["seen_ms"] > epoch_ms or key in self.clones | self.chain_breaks:
                continue
            if body["tamper_state"] != "clear" or body["fw_measurement"] not in self.reference_fw:
                continue
            if self.open_fc.get(key) in ("tamper", "attestation", "counter_regression",
                                         "chain_break"):
                continue
            members[key] = info["fp"]
        return members

    def note_root(self, members: dict[str, str]) -> list[str]:
        """Track consecutive missed roots; return keys that just missed two."""
        warn = []
        for key in self.last:
            if key in members:
                self.roots_missed[key] = 0
                continue
            self.roots_missed[key] = self.roots_missed.get(key, 0) + 1
            if self.roots_missed[key] == 2:
                warn.append(key)
        return warn

    def stale_renewals(self, current_epoch: int) -> list[str]:
        """Devices whose heartbeats show a renewal two or more epochs old (Finding P7).

        Catches a cut renewal path for devices that stay in good standing,
        which the missed-roots rule cannot see.
        """
        stale = []
        for key, info in self.last.items():
            held = info["body"].get("renewal_epoch")
            if held is not None and held <= current_epoch - 2:
                stale.append(key)
        return stale
