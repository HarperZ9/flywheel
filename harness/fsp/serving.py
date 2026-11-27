"""Scheduled serving-stack reports; a missed report is itself a signal (APPENDIX Part 2).

A demo serving stack signs a report on a fixed schedule and sends it to the
seats. The watch logs a missed_serving_report signal when a report is more
than one interval late. The report carries a fingerprint of its content and
no workload detail.
"""

from __future__ import annotations

from .canon import fingerprint
from .crypto import Ed25519Signer, envelope, signed_by


class ServingStack:
    def __init__(self, stack_id: str, interval_s: int) -> None:
        self.stack_id, self.interval_s = stack_id, interval_s
        self.signer = Ed25519Signer()
        self.seq = 0

    def report(self, now_ms: int) -> dict:
        self.seq += 1
        body = {"stack_id": self.stack_id, "seq": self.seq, "at_ms": now_ms,
                "content_fp": fingerprint("serving-report", {"seq": self.seq})}
        return envelope("serving-report", body, [self.signer])


class ReportWatch:
    def __init__(self, stack: ServingStack) -> None:
        self.key, self.interval_ms = stack.signer.public_hex(), stack.interval_s * 1000
        self.last_ms: int | None = None
        self.flagged = False

    def receive(self, report: dict, now_ms: int) -> bool:
        if not signed_by(report, self.key):
            return False
        self.last_ms, self.flagged = now_ms, False
        return True

    def scan(self, now_ms: int) -> dict | None:
        if self.last_ms is None or self.flagged:
            return None
        if now_ms - self.last_ms > 2 * self.interval_ms:
            self.flagged = True
            return {"kind": "missed_serving_report", "last_ms": self.last_ms, "at_ms": now_ms}
        return None
