"""The signal table and the convergence rule (SPEC.md section 11).

Each signal kind has one class, one family and one response. A registered
source may sign only the kinds it registered for, and the family comes from
the table, never from the source. At most RATE_SOURCE signals per source per
hour enter the convergence count; the rest are logged and not counted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canon import fingerprint
from .crypto import envelope, signed_by

HW, PROG, HUMAN = "hardware_network", "program_behavior", "human_evaluation"

# kind: (class, family, response)
TABLE = {
    "tamper": ("hard", HW, "fail closed one device; alert"),
    "attestation_failure": ("hard", HW, "fail closed one device; alert"),
    "counter_regression": ("hard", HW, "fail closed one device; alert"),
    "renewal_lapse": ("lapse", None, "fail closed one device; dependents warned first"),
    "time_lapse": ("lapse", None, "fail closed one device until a new quorum"),
    "clone_proof": ("proof", HW, "alert; routine renewal suspended for that key"),
    "split_view_proof": ("proof", HW, "alert; seats vote on removing the log"),
    "time_malfeasance_proof": ("proof", HW, "alert; seats review the time servers"),
    "missed_heartbeats": ("soft", HW, "record, alert; drop from next renewal root"),
    "counter_gap": ("soft", HW, "record, alert"),
    "location_fail": ("soft", HW, "record, alert"),
    "missing_receipt": ("soft", HW, "record, alert"),
    "network_egress": ("soft", HW, "record, alert"),
    "facility_power": ("soft", HW, "record, alert"),
    "missed_serving_report": ("soft", PROG, "record, alert"),
    "program_tripwire": ("soft", PROG, "record, alert"),
    "usage_anomaly": ("soft", PROG, "record, alert"),
    "outside_monitor": ("soft", PROG, "record, alert"),
    "whistleblower": ("soft", HUMAN, "record the fingerprint, alert"),
    "researcher_finding": ("soft", HUMAN, "record, alert"),
    "evaluation_finding": ("soft", HUMAN, "record, alert"),
}


def make_signal(source, kind: str, cluster_id: str, observed_ms: int, evidence: dict,
                device_key: str | None = None, tag: str | None = None) -> dict:
    cls, family, _ = TABLE[kind]
    body = {"kind": kind, "class": cls, "family": family,
            "scope": {"cluster_id": cluster_id, "device_key": device_key, "tag": tag},
            "source": source.public_hex(), "evidence_fp": fingerprint("evidence", evidence),
            "observed_ms": observed_ms}
    return envelope("signal", body, [source])


@dataclass
class Admitted:
    ok: bool
    counted: bool
    reason: str


class SourceRegistry:
    def __init__(self, rate_per_hour: int) -> None:
        self.sources: dict[str, set[str]] = {}
        self.rate = rate_per_hour
        self.counted_at: dict[str, list[int]] = {}

    def register(self, key: str, kinds: set[str]) -> None:
        self.sources[key] = set(kinds)

    def admit(self, sig: dict, logged_ms: int) -> Admitted:
        body = sig.get("body", {})
        key = body.get("source", "")
        if sig.get("type") != "signal" or key not in self.sources or not signed_by(sig, key):
            return Admitted(False, False, "unregistered source or bad signature")
        kind = body.get("kind")
        if kind not in self.sources[key]:
            return Admitted(False, False, f"source not registered for {kind}")
        cls, family, _ = TABLE[kind]
        if body.get("family") != family or body.get("class") != cls:
            return Admitted(False, False, "family or class does not match the table")
        recent = [t for t in self.counted_at.get(key, []) if logged_ms - t < 3_600_000]
        if len(recent) >= self.rate:
            return Admitted(True, False, "logged; over RATE_SOURCE, not counted")
        self.counted_at[key] = recent + [logged_ms]
        return Admitted(True, True, "counted")


def find_convergence(entries: list[dict], cluster_id: str, window_s: int) -> dict | None:
    """entries: {logged_ms, body, counted, ref}. Two soft families within one window.

    Only soft signals count. A hard signal fails its own device closed and
    stops nothing else, as the appendix's convergence rule says (SPEC.md
    Finding S17; README Finding P18). Proof and lapse signals do not count
    (Finding P5).
    """
    usable = []
    for e in sorted(entries, key=lambda x: x["logged_ms"]):
        body = e["body"]
        if body["scope"]["cluster_id"] != cluster_id or not e["counted"]:
            continue
        if body["class"] != "soft":
            continue
        usable.append(e)
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            if b["logged_ms"] - a["logged_ms"] > window_s * 1000:
                break
            if a["body"]["family"] != b["body"]["family"]:
                return {"families": sorted({a["body"]["family"], b["body"]["family"]}),
                        "window_start_ms": a["logged_ms"], "window_end_ms": b["logged_ms"],
                        "evidence": [a["ref"], b["ref"]]}
    return None
