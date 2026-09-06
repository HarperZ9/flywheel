"""acp_witness.py -- keep a recheckable record of a delegated agent run.

The chain machinery is harness/wire_witness.py, shared with the LSP client. What
is here is the part that is about ACP: the action names that land on the record,
and the fold of a turn into the shape a receipt carries.

A turn summary holds lengths and not text. The chain already binds the frames
that carried the words, and a summary that repeats them turns every receipt into
a second copy of the conversation.
"""
from __future__ import annotations

from .action_witness import OUTPUT, does_not_prove as action_does_not_prove
from .acp_turn import Turn
from .wire_witness import WireWitness, transcript_resolver

FRAME_ACTION = "acp/frame"
DECISION_ACTION = "acp/decision"
TURN_ACTION = "acp/turn"

WITNESS_SCHEMA = "flywheel.acp-witness/v1"

__all__ = ["AcpWitness", "DECISION_ACTION", "FRAME_ACTION", "TURN_ACTION",
           "WITNESS_SCHEMA", "does_not_prove", "summarize",
           "transcript_resolver"]


class AcpWitness(WireWitness):
    """Binds one ACP connection to one run's action chain."""

    FRAME_ACTION = FRAME_ACTION
    DECISION_ACTION = DECISION_ACTION

    def record_turn(self, turn: Turn) -> dict:
        """Witness the folded turn beside the frames it was folded from."""
        summary = summarize(turn)
        witness = self.record(summary, action=TURN_ACTION, kind=OUTPUT,
                              context={"session_id": turn.session_id,
                                       "stop_reason": turn.stop_reason})
        return dict(summary, sha256=witness.sha256, link=witness.link())


def summarize(turn: Turn) -> dict:
    """What the turn amounted to, in the shape a receipt carries."""
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
