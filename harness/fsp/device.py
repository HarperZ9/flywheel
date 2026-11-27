"""The device model (SPEC.md sections 3, 4, 6, 7 and 12).

A device runs on a hardware backend. It signs heartbeats, keeps a monotonic
counter and a heartbeat chain, holds a time quorum and a renewal, and fails
itself closed on conditions it detects itself: tamper, attestation failure,
counter regression, a broken heartbeat chain, renewal lapse and time lapse.
No remote message can fail it closed. Order handling lives in shim.py, the
time rule in devtime.py and maintenance windows in maintenance.py.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from . import devsupport, devtime, maintenance
from .canon import fingerprint
from .crypto import envelope, valid_signers
from .params import Params
from .proofs import verify_in_logs
from .renewal import leaf_valid
from .seats import Roster
from .enforce import Enforcer, NullEnforcer

HARD = ("tamper", "attestation", "counter_regression", "chain_break")
LAPSE = ("renewal_lapse", "time_lapse")


class AppendOnlySet(set):
    """The published reference firmware set (SPEC.md 3.2, rule R1).

    Measurements can be added and never removed. Withdrawing a measurement is a
    logged deprecation the seats vote on under a published criterion; it never
    reaches a device as a local attestation failure.
    """

    def _refuse(self, *_a, **_k):
        raise TypeError("the reference set is append-only; deprecation is a logged seat vote")

    remove = discard = pop = clear = difference_update = intersection_update = _refuse
    symmetric_difference_update = __isub__ = __iand__ = __ixor__ = _refuse


@dataclass
class Trust:
    """What a device was provisioned with or accepted from the logs."""
    policy: dict
    roster: Roster
    reference_fw: set
    time_keys: dict
    time_parties: dict
    cluster: dict
    panel_keys: set = field(default_factory=set)
    inspector_keys: set = field(default_factory=set)
    operator_keys: set = field(default_factory=set)
    governance_keys: set = field(default_factory=set)


class Device:
    def __init__(self, backend, params: Params, trust: Trust, region: str,
                 enforcer: Enforcer | None = None) -> None:
        self.backend, self.params, self.trust, self.region = backend, params, trust, region
        self.enforcer = enforcer or NullEnforcer()
        self.signer = backend.device_signer()
        self.view: dict = {}
        self.quorum: dict | None = None
        self.renewal: dict | None = None
        self.own_fps: deque = deque(maxlen=64)
        self.prev_fp = "genesis"
        self.high_water = backend.counter_read()
        self.location_fp = "none"
        self.outbox: list[dict] = []
        self.failed: str | None = None
        self.tamper_counter: int | None = None
        self.orders: dict[str, dict] = {}      # order_id -> body, in force
        self.applied: set[str] = set()
        self.pending: dict[str, dict] = {}     # order_id -> package, checks 1-6 passed
        self.lifted: set[str] = set()          # order ids a lift ended, pending ones too
        self.rate: dict[str, list[int]] = {}
        self.time_nonces: deque = deque(maxlen=8)
        self.windows: list[dict] = []          # accepted maintenance windows
        self.maint_log: list[int] = []
        # The firmware installed under the reference set in force at install time.
        fw = backend.fw_measurement
        self.installed_fw: str | None = fw if fw in trust.reference_fw else None

    @property
    def key(self) -> str:
        return self.signer.public_hex()

    def sign(self, msg_type: str, body: dict) -> dict:
        return envelope(msg_type, body, [self.signer])

    # time -----------------------------------------------------------------
    def t_work(self) -> int | None:
        q = self.quorum
        if q is None or q["boot"] != self.backend.boot_id():
            return None
        return q["t_ms"] + (self.backend.elapsed_ms() - q["elapsed_ms"])

    def new_time_nonce(self) -> str:
        return devtime.new_nonce(self)

    def accept_time(self, chain: list[dict]) -> tuple[bool, str]:
        ok, why = devtime.accept_time(self, chain)
        if ok and self.failed == "time_lapse":
            self._try_restore()
        return ok, why

    # renewal --------------------------------------------------------------
    def accept_renewal(self, msg: dict, bundles: list[dict], leaf_pkg: dict) -> tuple[bool, str]:
        signers = [k for k in valid_signers(msg) if k in self.trust.roster.seats]
        if msg.get("type") != "renewal" or len(signers) < self.params.k_renew:
            return False, f"{len(signers)} of {self.params.k_renew} seat signatures"
        span = len({self.trust.roster.seats[k].get("region") for k in signers})
        if span < self.params.min_signer_regions:
            return False, f"renewal signers span {span} of {self.params.min_signer_regions} regions"
        if self.renewal and msg["body"]["epoch"] <= self.renewal["epoch"]:
            return False, "not a newer epoch"
        why = devsupport.renewal_span_refusal(self, msg["body"])
        if why is not None:
            return False, why
        res = verify_in_logs(msg, bundles, self.trust.policy, self.view)
        if not res.ok:
            return False, res.reason
        if leaf_pkg is None or not leaf_valid(msg, self.key, leaf_pkg, list(self.own_fps)):
            return False, "this device's leaf is not in the renewal root"
        self.renewal = dict(msg["body"])
        if self.failed == "renewal_lapse":
            self._try_restore()
        return True, "ok"

    # roster, maintenance and location (devsupport.py, maintenance.py) -------
    def adopt_roster(self, msg: dict, bundles: list[dict]) -> tuple[bool, str]:
        return devsupport.adopt_roster(self, msg, bundles)

    def accept_maintenance(self, msg: dict, bundles: list[dict]) -> tuple[bool, str]:
        return maintenance.accept_window(self, msg, bundles)

    def restore_after_maintenance(self, inspection: dict) -> tuple[bool, str]:
        return maintenance.restore(self, inspection)

    def note_location(self, records: list[dict]) -> str:
        return devsupport.note_location(self, records)

    # heartbeat ------------------------------------------------------------
    def heartbeat(self, profile: str = "conforming") -> dict:
        counter = self.backend.counter_increment()
        self.high_water = counter
        body = {
            "device_key": self.key, "counter": counter,
            "fw_measurement": self.backend.fw_measurement,
            "tamper_state": ("clear" if self.tamper_counter is None
                             else {"fired_at_counter": self.tamper_counter}),
            "time_view": self._time_view(),
            "checkpoints": [{"log_id": k, "size": v["size"], "root": v["root"],
                             "log_sigs": v.get("cp", {}).get("sigs", [])}
                            for k, v in sorted(self.view.items())],
            "location": self.location_fp,
            "enforcement": self.enforcement(),
            "renewal_epoch": self.renewal["epoch"] if self.renewal else None,
            "prev_fp": self.prev_fp,
        }
        if profile == "telemetry":
            body["usage"] = self.backend.telemetry()
            body["profile"] = "telemetry-nonconforming"
        msg = self.sign("heartbeat", body)
        self.prev_fp = fingerprint("heartbeat", body)
        self.own_fps.append(self.prev_fp)
        devtime.raise_floor(self)
        return msg

    def _time_view(self) -> dict:
        if self.quorum is None:
            return {"quorum_fp": "none", "elapsed_s": 0}
        elapsed = (self.backend.elapsed_ms() - self.quorum["elapsed_ms"]) // 1000
        return {"quorum_fp": self.quorum["fp"], "elapsed_s": max(0, elapsed)}

    def enforcement(self) -> dict:
        if self.failed:
            return {"state": "failed_closed", "reason": self.failed, "level": 0, "tags": [],
                    "orders_in_force": sorted(self.orders)}
        try:
            level, tags = self.desired()
        except (KeyError, TypeError, ValueError) as exc:
            # SPEC.md Finding S46: a fault in enforcement must never stop the heartbeat.
            return {"state": "enforcement_error", "reason": type(exc).__name__, "level": None,
                    "tags": [], "orders_in_force": sorted(self.orders)}
        state = "halted" if tags else ("throttled" if level < 100 else "normal")
        return {"state": state, "reason": None, "level": level, "tags": sorted(tags),
                "orders_in_force": sorted(self.orders)}

    def desired(self) -> tuple[int, set]:
        level, tags = 100, set()
        for body in self.orders.values():
            if body["action"] == "throttle":
                level = min(level, body["level"])
            elif body["action"] == "halt":
                tags |= set(body["scope"]["workload_tags"])
        return level, tags

    # self-checks and fail-closed -----------------------------------------
    def boot_check(self, last_logged_heartbeat: dict | None) -> None:
        """Compare storage with the device's own last logged heartbeat."""
        if last_logged_heartbeat is None or self.key not in valid_signers(last_logged_heartbeat):
            return
        body = last_logged_heartbeat["body"]
        stored = self.backend.counter_read()
        if stored < body["counter"]:
            self.fail_closed("counter_regression")
        elif stored == body["counter"] and self.prev_fp != fingerprint("heartbeat", body):
            # SPEC.md Finding S40: the chain head was rolled back while the counter held.
            self.fail_closed("chain_break")

    def self_check(self) -> None:
        devtime.raise_floor(self)
        if self.backend.tamper_fired():
            if self.tamper_counter is None:
                self.tamper_counter = self.backend.counter_read()
            if maintenance.in_window(self, self.t_work()) and self.failed not in HARD:
                self.fail_closed("maintenance_tamper")
            else:
                self.fail_closed("tamper")
        elif not self._firmware_ok():
            self.fail_closed("attestation")
        elif self.backend.counter_read() < self.high_water:
            self.fail_closed("counter_regression")
        if self.failed in HARD or self.failed == "maintenance_tamper":
            return
        now = self.t_work()
        if now is None or now - self.quorum["t_ms"] > self.params.time_allowance * 1000:
            self.fail_closed("time_lapse")
        elif self.renewal is None or now > self.renewal["valid_until_ms"]:
            self.fail_closed("renewal_lapse")

    def _firmware_ok(self) -> bool:
        """Running firmware is the installed one, or a newer one in the reference set.

        A measurement later withdrawn from the set does not fail a device that
        installed it while it was listed (SPEC.md 3.2, rule R1).
        """
        fw = self.backend.fw_measurement
        if fw is not None and fw == self.installed_fw:
            return True
        if fw in self.trust.reference_fw:
            self.installed_fw = fw
            return True
        return False

    def fail_closed(self, reason: str) -> None:
        if self.failed == reason or self.failed in HARD:
            return
        self.failed = reason
        self.enforcer.apply({"level": 0, "halted_tags": set(), "failed_closed": True})
        self.outbox.append(self.sign("failclosed", {
            "device_key": self.key, "reason": reason, "counter": self.backend.counter_read(),
            "at_ms": self.t_work(), "hard": reason in HARD}))

    def _try_restore(self) -> None:
        now = self.t_work()
        if self.failed not in LAPSE or self.backend.tamper_fired() or now is None:
            return
        if self.renewal is None or now > self.renewal["valid_until_ms"]:
            return
        if now - self.quorum["t_ms"] > self.params.time_allowance * 1000:
            return
        reason, self.failed = self.failed, None
        self._enforce()
        self.outbox.append(self.sign("restored", {"device_key": self.key, "from": reason,
                                                  "at_ms": now,
                                                  "counter": self.backend.counter_read()}))

    def restore_after_inspection(self, inspection: dict, restoration: dict) -> tuple[bool, str]:
        """Hard-signal restoration: an inspection record and K_RESTORE seats."""
        if self.failed not in HARD:
            return False, "not failed closed on a hard signal"
        inspectors = set(valid_signers(inspection)) & self.trust.inspector_keys
        if inspection.get("type") != "inspection" or not inspectors:
            return False, "no inspection record signed by a registered inspector"
        if self.backend.tamper_fired():
            return False, "tamper sensor still reads fired"
        seats = self.trust.roster.signers(restoration)
        subject = fingerprint("inspection", inspection["body"])
        if restoration["body"].get("inspection_fp") != subject or len(seats) < self.params.k_restore:
            return False, f"{len(seats)} of {self.params.k_restore} seats signed restoration"
        self.failed, self.tamper_counter = None, None
        self._enforce()
        return True, "ok"

    def _enforce(self) -> list[str]:
        level, tags = self.desired()
        return self.enforcer.apply({"level": level, "halted_tags": tags,
                                    "failed_closed": self.failed is not None})
