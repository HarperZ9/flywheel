"""The alert pipeline and its clocks (SPEC.md section 13).

Record: the signal goes to the logs and every seat, with a delivery entry.
Alert: each seat logs a triage verdict. Notify: a triaged notice is logged.
Escalate: a convergence set hands off to evaluators and refers to
governance. Each clock is read from log entry times, widened by TIME_TOL at
each end, as MET, MISSED or UNVERIFIABLE.
"""

from __future__ import annotations

from .canon import fingerprint
from .crypto import envelope
from .signals import HW, find_convergence
from .world import World

RECIPIENTS = ["seat-0", "seat-1", "seat-2", "seat-3", "seat-4", "seat-5", "seat-6",
              "operator", "developer", "host-csirt", "registered-dependents"]


def clock_verdict(start_ms: int, end_ms: int | None, deadline_s: int, tol_s: int) -> str:
    if end_ms is None:
        return "UNVERIFIABLE"
    gap, widen, limit = end_ms - start_ms, 2 * tol_s * 1000, deadline_s * 1000
    if gap + widen <= limit:
        return "MET"
    if gap - widen > limit:
        return "MISSED"
    return "UNVERIFIABLE"


class AlertPipeline:
    def __init__(self, world: World) -> None:
        self.world = world
        self.records: list[dict] = []
        self.admitted: list[dict] = []
        self.rejected: list[dict] = []

    def _logged_ms(self, idx: dict) -> int:
        return self.world.logs[0].leaves[idx["log-0"]]["logged_ms"]

    def record(self, sig: dict, received_ms: int) -> dict | None:
        w = self.world
        adm = w.sources.admit(sig, w.now_ms())
        if not adm.ok:
            self.rejected.append({"reason": adm.reason, "fp": fingerprint("entry", sig)})
            return None
        idx = w.publish(sig)
        logged = self._logged_ms(idx)
        fp = fingerprint("entry", sig)
        delivery = envelope("delivery", {"signal_fp": fp, "recipients": RECIPIENTS,
                                         "at_ms": w.now_ms()}, [s.signer for s in w.seats])
        w.publish(delivery)
        body = sig["body"]
        entry = {"logged_ms": logged, "body": body, "counted": adm.counted,
                 "ref": {"log_index": idx["log-0"], "entry_fp": fp, "family": body["family"]}}
        self.admitted.append(entry)
        rec = {"signal_fp": fp, "kind": body["kind"], "family": body["family"],
               "cluster_id": body["scope"]["cluster_id"], "received_ms": received_ms,
               "record_ms": logged, "time_fp": w.logs[0].leaves[idx["log-0"]]["time_fp"],
               "seats_reached": len(w.seats), "counted": adm.counted, "verdicts": {},
               "notify_ms": None, "log_index": idx["log-0"]}
        self.records.append(rec)
        return rec

    def triage(self, rec: dict, seat_indices=None) -> None:
        w = self.world
        for i in seat_indices if seat_indices is not None else range(len(w.seats)):
            seat = w.seats[i]
            msg = envelope("triage", {"signal_fp": rec["signal_fp"], "seat": seat.key,
                                      "verdict": "credible"}, [seat.signer])
            rec["verdicts"][i] = self._logged_ms(w.publish(msg))

    def notify(self, rec: dict) -> None:
        w = self.world
        msg = envelope("triaged-notice", {"signal_fp": rec["signal_fp"],
                                          "verdicts": len(rec["verdicts"])},
                       [w.seats[0].signer])
        rec["notify_ms"] = self._logged_ms(w.publish(msg))

    def convergence(self, cluster_id: str) -> dict | None:
        return find_convergence(self.admitted, cluster_id, self.world.params.t_converge)

    def escalate(self, conv: dict) -> dict:
        w = self.world
        hand = w.publish(envelope("evaluator-handoff", {"convergence": conv},
                                  [w.seats[0].signer]))
        ref = w.publish(envelope("governance-referral", {"convergence": conv},
                                 [w.seats[0].signer]))
        return {"handoff_ms": self._logged_ms(hand), "referral_ms": self._logged_ms(ref)}

    def clock_rows(self, rec: dict) -> list[dict]:
        p = self.world.params
        notify_s = p.t_notify_hw if rec["family"] == HW else p.t_notify_other
        last_verdict = max(rec["verdicts"].values()) if len(rec["verdicts"]) == len(
            self.world.seats) else None
        return [
            {"step": "record", "deadline_s": p.t_record,
             "verdict": clock_verdict(rec["received_ms"], rec["record_ms"], p.t_record,
                                      p.time_tol)},
            {"step": "alert", "deadline_s": p.t_alert,
             "verdict": clock_verdict(rec["record_ms"], last_verdict, p.t_alert, p.time_tol)},
            {"step": "notify", "deadline_s": notify_s,
             "verdict": clock_verdict(rec["record_ms"], rec["notify_ms"], notify_s,
                                      p.time_tol)},
        ]
