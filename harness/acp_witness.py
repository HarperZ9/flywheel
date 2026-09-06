"""acp_witness.py -- keep a recheckable record of a delegated agent run.

Flywheel's claim about a delegated run is narrow and it should stay narrow: this
is what crossed the wire between the client and the agent, in this order, and
nobody has changed it since. That is worth something precisely because it is not
a claim about whether the agent was right.

The record is taken at the frame, not at the summary. Every message in either
direction becomes one link in the run's action chain, so an edit to any frame
breaks every link after it. The bytes stay with whoever holds the transcript; the
chain holds digests, so a run's log can travel where its prompts never could.

Policy decisions land in the same chain. A receipt that shows only what succeeded
is a worse record than one that shows what the agent asked for and was refused,
and the refusals are the part a reader cannot reconstruct from the outcome.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
import threading

from .action_witness import (ActionLog, CANONICAL_JSON, INPUT, OUTPUT,
                             does_not_prove as action_does_not_prove, observe)
from .acp_connection import SENT
from .acp_turn import Turn
from .evidence_json import canonical_bytes

FRAME_ACTION = "acp/frame"
DECISION_ACTION = "acp/decision"
TURN_ACTION = "acp/turn"

WITNESS_SCHEMA = "flywheel.acp-witness/v1"


class AcpWitness:
    """Binds one ACP connection to one run's action chain.

    Install `observe_frame` as the connection's observer. It is called from the
    reader thread and from whichever thread is sending, so the chain is taken
    under a lock: two links appended concurrently would each claim the same
    predecessor and the log would read as broken for a reason that had nothing
    to do with tampering.
    """

    def __init__(self, log: ActionLog, *,
                 transcript: str | Path | None = None) -> None:
        self.log = log
        self.frames = 0
        self.transcript = Path(transcript) if transcript is not None else None
        self._seq = itertools.count(0)
        self._lock = threading.Lock()
        self._decisions_written = 0

    def observe_frame(self, direction: str, message: dict) -> None:
        """The Observer a Connection calls for every frame in both directions."""
        kind = INPUT if direction == SENT else OUTPUT
        context = {"direction": direction, "method": message.get("method", ""),
                   "message_id": message.get("id"),
                   "outcome": _outcome_of(message)}
        with self._lock:
            self._witness(message, action=FRAME_ACTION, kind=kind,
                          context=context, keep={"direction": direction})
            self.frames += 1

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
                              action=DECISION_ACTION,
                              kind=OUTPUT if decision.allowed else INPUT,
                              context={"policy": getattr(policy, "name",
                                                         "unnamed"),
                                       "allowed": decision.allowed})
            self._decisions_written += len(fresh)
        return len(fresh)

    def record_turn(self, turn: Turn) -> dict:
        """Witness the folded turn beside the frames it was folded from."""
        summary = summarize(turn)
        with self._lock:
            witness = self._witness(summary, action=TURN_ACTION, kind=OUTPUT,
                                    context={"session_id": turn.session_id,
                                             "stop_reason": turn.stop_reason})
        return dict(summary, sha256=witness.sha256, link=witness.link())

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
        agent's output verbatim, which is exactly what an operator may not want
        written to disk, so it is a decision and not a default.
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
    """Whether a frame carried an answer, a refusal, or neither."""
    if "error" in message:
        return "error"
    if "result" in message:
        return "result"
    return ""


def summarize(turn: Turn) -> dict:
    """What the turn amounted to, in the shape a receipt carries.

    Text lengths rather than text. The chain already binds the frames that
    carried the words, and a summary that repeats them turns every receipt into
    a second copy of the conversation.
    """
    return {
        "schema": WITNESS_SCHEMA,
        "session_id": turn.session_id,
        "stop_reason": turn.stop_reason,
        "refused": turn.refused,
        "complete": turn.complete,
        "message_characters": len(turn.text),
        "thinking_characters": len(turn.thinking),
        "updates": len(turn.updates),
        "unrecognized_updates": len(turn.unrecognized),
        "tool_calls": [{"id": call.tool_call_id, "title": call.title,
                        "kind": call.kind, "status": call.status,
                        "output_characters": len(call.text)}
                       for call in turn.tool_calls.values()],
        "usage": dict(turn.usage),
        "does_not_prove": turn.does_not_prove(),
    }


def does_not_prove() -> list[str]:
    """What an ACP run record leaves open. Never empty."""
    return action_does_not_prove() + [
        "the chain covers frames that crossed this connection, so work the "
        "agent did through a channel this client did not carry leaves nothing "
        "behind to break a link",
        "a tool call in the record is what the agent reported, not an "
        "independent observation that the tool ran",
        "the chain shows the frames were not altered after the run and says "
        "nothing about whether the agent's answer was correct",
    ]
