"""wire_witness.py -- keep a recheckable record of what crossed a JSON-RPC wire.

Flywheel's claim about a delegated run is narrow and it should stay narrow: this
is what crossed between the two sides, in this order, and nobody has changed it
since. That is worth something precisely because it is not a claim about whether
the far side was right.

The record is taken at the message, not at the summary. Every message in either
direction becomes one link in the run's action chain, so an edit to any message
breaks every link after it. The bytes stay with whoever holds the transcript; the
chain holds digests, so a run's log can travel where its prompts never could.

Policy decisions land in the same chain. A receipt that shows only what succeeded
is a worse record than one that shows what the far side asked for and was
refused, and the refusals are the part a reader cannot reconstruct from the
outcome.

Shared by the ACP and LSP witnesses. What differs between them is the vocabulary
of actions and what a folded result looks like, so those live in the two
subclasses and the chain machinery lives here.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
import threading

from .action_witness import ActionLog, CANONICAL_JSON, INPUT, OUTPUT, observe
from .evidence_json import canonical_bytes
from .jsonrpc_peer import SENT


class WireWitness:
    """Binds one JSON-RPC connection to one run's action chain.

    Install `observe_frame` as the connection's observer. It is called from the
    reader thread and from whichever thread is sending, so the chain is taken
    under a lock: two links appended concurrently would each claim the same
    predecessor and the log would read as broken for a reason that had nothing
    to do with tampering.

    A subclass names its own actions. The strings are on the record, so a
    reader can tell an ACP frame from an LSP one without being told which tool
    wrote the log.
    """

    FRAME_ACTION = "wire/frame"
    DECISION_ACTION = "wire/decision"

    def __init__(self, log: ActionLog, *,
                 transcript: str | Path | None = None) -> None:
        self.log = log
        self.frames = 0
        self.transcript = Path(transcript) if transcript is not None else None
        self._seq = itertools.count(0)
        self._lock = threading.Lock()
        self._decisions_written = 0

    def observe_frame(self, direction: str, message: dict) -> None:
        """The Observer a peer calls for every message in both directions."""
        kind = INPUT if direction == SENT else OUTPUT
        context = {"direction": direction, "method": message.get("method", ""),
                   "message_id": message.get("id"),
                   "outcome": _outcome_of(message)}
        with self._lock:
            self._witness(message, action=self.FRAME_ACTION, kind=kind,
                          context=context, keep={"direction": direction})
            self.frames += 1

    def record(self, payload: dict, *, action: str, context: dict,
               kind: str = OUTPUT, keep: dict | None = None):
        """Witness one payload of this side's own making, under the same lock."""
        with self._lock:
            return self._witness(payload, action=action, kind=kind,
                                 context=context, keep=keep)

    def record_decisions(self, policy) -> int:
        """Witness what the policy answered. Returns how many were new.

        Reads the policy's own list rather than hooking each call, so a policy
        that answered while nothing was watching still lands in the record.
        """
        decisions = list(getattr(policy, "decisions", ()))
        with self._lock:
            fresh = decisions[self._decisions_written:]
            for decision in fresh:
                self._witness({"method": decision.method,
                               "detail": decision.detail,
                               "allowed": decision.allowed,
                               "reason": decision.reason},
                              action=self.DECISION_ACTION,
                              kind=OUTPUT if decision.allowed else INPUT,
                              context={"policy": getattr(policy, "name",
                                                         "unnamed"),
                                       "allowed": decision.allowed})
            self._decisions_written += len(fresh)
        return len(fresh)

    def _witness(self, payload: dict, *, action: str, kind: str,
                 context: dict, keep: dict | None = None):
        """Append one link, and keep the value the digest was taken over."""
        witness = observe(self.log, canonical_bytes(payload), action=action,
                          kind=kind, seq=next(self._seq),
                          encoding=CANONICAL_JSON, context=context)
        self._keep(dict(keep or {}, sha256=witness.sha256, action=action,
                        payload=payload))
        return witness

    def _keep(self, entry: dict) -> None:
        """Write what a digest was taken over, when the caller asked for it.

        Off unless a path is given. A transcript holds the prompt text and the
        far side's output verbatim, which is exactly what an operator may not
        want written to disk, so it is a decision and not a default.
        """
        if self.transcript is None:
            return
        try:
            self.transcript.parent.mkdir(parents=True, exist_ok=True)
            with self.transcript.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # The chain is the record. A transcript that could not be written
            # makes the run harder to recheck by hand, not unverifiable.
            pass


def transcript_resolver(path: str | Path):
    """A sha256 -> bytes lookup over a run's transcript.

    The chain carries digests and the transcript carries what they were taken
    over. Hand `verify_log` both, and a machine that never saw the run can
    check it. Hand it the chain alone and the honest answer is UNVERIFIABLE.
    """
    table: dict[str, bytes] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            table[entry["sha256"]] = canonical_bytes(entry["payload"])
    return table.get


def _outcome_of(message: dict) -> str:
    """Whether a message carried an answer, a refusal, or neither."""
    if "error" in message:
        return "error"
    if "result" in message:
        return "result"
    return ""
