"""Assembles every role of the protocol in one process for tests, drills and the demo.

Seats, logs, witnesses, time servers, the seat desk, signal sources and
devices are objects here. Messages cross role boundaries as signed
canonical JSON and every check runs on those messages. Nothing here opens a
socket or touches software other than the demo's own child processes.
"""

from __future__ import annotations

from typing import Callable

from .canon import fingerprint
from .crypto import Ed25519Signer, envelope
from .device import AppendOnlySet, Device, Trust
from .log import TransparencyLog, ms
from .monitor import SeatDesk
from .orders import device_set_tree
from .params import Params
from .proofs import make_bundle, verify_in_logs
from .seats import Roster, default_seats, make_roster
from .signals import SourceRegistry
from .timesrc import TimeServer, query_chain
from .witness import Refused, Witness

DESK_KINDS = {"missed_heartbeats", "counter_gap", "missing_receipt", "clone_proof",
              "split_view_proof", "time_malfeasance_proof", "tamper", "attestation_failure",
              "counter_regression", "renewal_lapse", "time_lapse", "location_fail"}


class SimClock:
    def __init__(self, start: float = 1_790_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class World:
    def __init__(self, params: Params | None = None, clock: Callable[[], float] | None = None,
                 fw: str = "aa" * 32) -> None:
        self.params = params or Params()
        self.clock = clock or SimClock()
        p = self.params
        self.seats = default_seats()
        self.logs = [TransparencyLog(f"log-{j}", f"J{j + 1}", self.clock, p.t_record,
                                     self._time_fp) for j in range(p.logs_listed)]
        self.witnesses = [Witness(f"witness-{i}", f"state-W{i}", self.clock)
                          for i in range(p.n_witness)]
        self.time_servers = [TimeServer(f"ts-{i}", f"party-{i}", f"J{i + 1}", self.clock)
                             for i in range(p.n_time)]
        self.roster_msg = make_roster(self.seats, 1, self.seats)
        self.inspector = Ed25519Signer()
        self.panel = [Ed25519Signer() for _ in range(3)]
        self.operator = Ed25519Signer()
        self.fw = fw
        self.reference_fw = {fw}
        self.policy = self._policy()
        self.desk = SeatDesk(p, self.reference_fw)
        self.desk.gossip_desk.attach(self.logs)
        self.governance = Ed25519Signer()
        self.open_roots: list[dict] = []       # renewal roots awaiting T_REFUSE
        self.sources = SourceRegistry(p.rate_source_per_hour)
        self.desk_source = Ed25519Signer()
        self.sources.register(self.desk_source.public_hex(), DESK_KINDS)
        self.cosigned: dict[str, tuple[dict, list[dict]]] = {}
        self.split_views: list[Refused] = []
        self.clusters: dict[str, dict] = {}
        self.devices: dict[str, Device] = {}
        self.events: list[dict] = []
        self.last_quorum_fp = "none"
        self.criterion = envelope("criterion", {"id": "crit-1", "version": 1,
                                                "summary": "demo criterion, placeholder"},
                                  [s.signer for s in self.seats[: p.k_order]])
        for msg in (self.roster_msg, envelope("log-policy", self.policy,
                                              [s.signer for s in self.seats[: p.k_order]]),
                    envelope("reference-fw", {"fw_measurements": sorted(self.reference_fw)}),
                    self.criterion):
            self.publish(msg)
        self.cosign()

    def _time_fp(self) -> str:
        return self.last_quorum_fp

    def _policy(self) -> dict:
        return {"epoch": 1,
                "logs": [{"log_id": lg.log_id, "key": lg.key, "jurisdiction": lg.jurisdiction,
                          "operator": f"operator-{lg.log_id}"} for lg in self.logs],
                "witnesses": [{"key": w.key, "custodian_state": w.custodian_state}
                              for w in self.witnesses],
                "k_witness": self.params.k_witness, "logs_min": self.params.logs_min}

    def now_ms(self) -> int:
        return ms(self.clock())

    # logs -------------------------------------------------------------------
    def publish(self, msg: dict, logs: list[TransparencyLog] | None = None) -> dict[str, int]:
        out = {}
        for log in logs or self.logs:
            log.submit(msg)
            idx = log.find(fingerprint("entry", msg))
            if idx is not None:
                out[log.log_id] = idx
        return out

    def cosign(self, logs: list[TransparencyLog] | None = None) -> None:
        for log in logs or self.logs:
            log.integrate()
            cp = log.checkpoint()
            cosigs = []
            for w in self.witnesses:
                prev = w.latest.get(log.log_id)
                old = prev["body"]["size"] if prev else 0
                proof = log.consistency(old, cp["body"]["size"]) if 0 < old < cp["body"][
                    "size"] else []
                try:
                    cosigs.append(w.cosign(cp, log.key, proof))
                except Refused as exc:
                    self.split_views.append(exc)
            self.cosigned[log.log_id] = (cp, cosigs)

    def bundles(self, msg: dict, dev: Device, logs: list[TransparencyLog] | None = None) -> list:
        fp, out = fingerprint("entry", msg), []
        for log in logs or self.logs:
            idx = log.find(fp)
            if idx is None or log.log_id not in self.cosigned:
                continue
            cp, cosigs = self.cosigned[log.log_id]
            if idx >= cp["body"]["size"]:
                continue
            from_size = dev.view.get(log.log_id, {}).get("size", 0)
            out.append(make_bundle(log, idx, cp, cosigs, from_size))
        return out

    # devices ----------------------------------------------------------------
    def trust(self) -> Trust:
        return Trust(self.policy, Roster(self.roster_msg), AppendOnlySet(self.reference_fw),
                     {s.server_id: s.key for s in self.time_servers},
                     {s.server_id: s.party for s in self.time_servers}, {},
                     {k.public_hex() for k in self.panel}, {self.inspector.public_hex()},
                     operator_keys={self.operator.public_hex()},
                     governance_keys={self.governance.public_hex()})

    def time_chain(self, dev: Device | None = None) -> list[dict]:
        """A chained time query. With a device, the chain starts from that
        device's own nonce, which is the only kind of chain a device accepts."""
        if dev is None:
            return query_chain(self.time_servers)
        return query_chain(self.time_servers, first_blind=bytes.fromhex(dev.new_time_nonce()))

    def add_device(self, backend, cluster_id: str, region: str = "region-1",
                   enforcer=None) -> Device:
        dev = Device(backend, self.params, self.trust(), region, enforcer)
        ok, reason = dev.accept_time(self.time_chain(dev))
        if not ok:
            raise RuntimeError(f"device could not get a time quorum: {reason}")
        self.last_quorum_fp = dev.quorum["fp"]
        self.devices[dev.key] = dev
        self.desk.register(dev.key, cluster_id, region, self.now_ms())
        return dev

    def provision_cluster(self, cluster_id: str, devices: list[Device]) -> dict:
        keys = sorted(d.key for d in devices)
        body = {"cluster_id": cluster_id, "device_keys": keys,
                "device_set_root": device_set_tree(keys).root().hex(),
                "operator_id": "operator-1"}
        msg = envelope("cluster", body, [self.operator])
        self.publish(msg)
        self.cosign()
        for dev in devices:
            res = verify_in_logs(msg, self.bundles(msg, dev), dev.trust.policy, dev.view)
            if not res.ok:
                raise RuntimeError(f"cluster record not accepted: {res.reason}")
            dev.trust.cluster = body
        self.clusters[cluster_id] = body
        return body

    def deliver(self, dev: Device) -> list[tuple[dict, dict]]:
        """The operator carries a device's outbox to the logs and the seats."""
        out = []
        for msg in dev.outbox:
            idx = self.publish(msg)
            for ev in self.desk.receive(msg, self.now_ms()):
                self.events.append({**ev, "at_ms": self.now_ms()})
            out.append((msg, idx))
        dev.outbox = []
        self.log_seat_silence()
        return out

    # seat silence (SPEC.md 7.3) ----------------------------------------------
    def log_seat_silence(self) -> list[dict]:
        """After T_REFUSE, log one entry per renewal root naming every seat that
        neither signed it nor logged a refusal of it. Withholding then leaves an
        attributable record even when no root is ever accepted."""
        out, now = [], self.now_ms()
        due = [r for r in self.open_roots
               if now - r["published_ms"] >= self.params.t_refuse * 1000]
        for root in due:
            refused = {lf["entry"]["body"].get("seat") for _i, lf in
                       self.logs[0].entries_of("renewal-refusal")
                       if lf["entry"]["body"].get("subject_fp") == root["subject_fp"]}
            silent = sorted(set(root["seats"]) - set(root["signed"]) - refused)
            entry = envelope("seat-silence", {"subject_fp": root["subject_fp"],
                                              "silent_seats": silent,
                                              "published_ms": root["published_ms"],
                                              "t_refuse_s": self.params.t_refuse},
                             [self.desk_source])
            self.publish(entry)
            self.open_roots.remove(root)
            out.append(entry)
        return out
