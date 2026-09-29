"""States and helpers shared by the Control Tower monitor adapters.

A monitor observation is in exactly one of these states. None of them is a
number, and only SCORED may ever be compared against a threshold.

- SCORED: the monitor produced a usable number for an action that ran.
- UNSCORED: the monitor ran and produced no usable number. Control Tower writes
  this as the string "unscored" (eval2) or as Inspect's NOANSWER "N" with the
  error beside it (eval1). The reason is kept.
- ABSENT: there is no monitor result at all.
- DRAFT: eval2 scored a proposal that the protocol never executed (a
  defer-to-resample draft). It is not an action the agent took, so it is
  counted apart and never compared.
- UNSUPPORTED: a shape this module does not recognise. It is reported rather
  than guessed at, because guessing between formats changes what a number means.
"""
from __future__ import annotations

SCORED = "scored"
UNSCORED = "unscored"
ABSENT = "absent"
DRAFT = "draft"
UNSUPPORTED = "unsupported"
STATES = (SCORED, UNSCORED, ABSENT, DRAFT, UNSUPPORTED)

# The revision whose writers these shapes were read from. Control Tower changed
# both formats in the week before it (eval1 Score shape on 2026-09-17, eval2
# monitoring on 2026-09-21, both breaking), so a log from another revision may
# not match.
SOURCE_REVISION = "linuxarena/control-tower@1cc91b7182674a906d4f556c2d2f493c27e51ae9"

# eval_logs/eval2_seat.py. `ct run monitor2` refuses a log without it.
EVAL2_TASK = "control_tower/control_eval2"

# Inspect's NOANSWER value, which current eval1 writes for a failed or
# skipped-by-design monitor score.
NOANSWER = "N"


class MonitorAdapterError(ValueError):
    """The log does not match the declared adapter."""


def is_number(value: object) -> bool:
    """A JSON number. A bool is not one, although Python says it is an int."""
    return type(value) in (int, float)


def pointer(sample_index: int, *rest: object) -> str:
    tail = "".join(f"/{part}" for part in rest)
    return f"/samples/{sample_index}/scores{tail}"


def fold_status(statuses: list[str]) -> str:
    """One status for a set of observations, strongest evidence first."""
    for state in (SCORED, UNSCORED, UNSUPPORTED):
        if state in statuses:
            return state
    return ABSENT


def action(*, index, kind, monitor, status, source_value, source_pointer,
           message_id=None, draw=None, reason=None, detail=None) -> dict:
    """One per-action (or per-trajectory) observation, source value untouched.

    There is deliberately no normalised numeric field. A reader that wants a
    number checks `status` first and reads `source_value`.
    """
    return {
        "action": index,
        "kind": kind,
        "message_id": message_id,
        "monitor": monitor,
        "draw": draw,
        "status": status,
        "source_value": source_value,
        "reason": reason,
        "detail": detail or {},
        "source_pointer": source_pointer,
    }
