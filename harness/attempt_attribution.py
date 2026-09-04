"""Why a launched attempt never reached a grader.

An attempt that never got a score is not an attempt that scored zero, and the
failures behind it are not interchangeable either. In the 2026-09-04 run one
harness answered a task correctly and closed the document with one stray brace.
On another task the same harness streamed a quarter megabyte of reasoning and
never emitted a final answer at all. Both land in the scorecard as an unscored
row, and a readable rate on its own prices them identically.

The executor already records the failure class and detail on every row. Nothing
read them, so a published comparison could report a harness as producing
nothing readable without ever saying that it produced a correct answer in an
envelope one character wide of the contract. That reads as a verdict on the
harness when it is a verdict on its formatting.

This turns those fields into counts a reader can act on. It classifies and does
not judge. A class it does not recognise keeps its own name rather than being
folded into an "other" bucket, because a bucket is where a new failure mode
goes to stop being noticed.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

SCORED_STATES = ("pass", "fail")

# Plain words for the failure classes the executor emits. Two of them look alike
# and are not. `_MalformedAttempt` is refused at the envelope, before any
# checker sees it. `oracle_malformed` means the envelope was accepted and the
# artifact inside it was invalid, so a checker did run and did report. Folding
# those together would hide which layer a harness actually failed at.
LABELS = {
    "_MalformedAttempt": "refused at the envelope",
    "oracle_malformed": "artifact inside the envelope was invalid",
    "invalid_model_observation": "no provider attestation of which model answered",
    "malformed_jsonl": "the provider's own stream was unreadable",
    "malformed_provider_output": "the inner provider's output was unreadable",
    "BackendError": "the model endpoint did not answer",
    "timeout": "over the time budget",
    "internal_error": "failed inside the harness",
}

UNATTRIBUTED = "with no failure class recorded"


def label_for(failure_class: Any) -> str:
    """Plain words for one class, keeping an unknown class's own name."""
    raw = str(failure_class or "").strip()
    if not raw:
        return UNATTRIBUTED
    return LABELS.get(raw, raw)


def attribute(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Counts of why launched attempts went ungraded, largest first.

    Only launched attempts are counted. An attempt that never reached a
    provider is a gate or availability fact, which the launch rate already
    carries and which is not a statement about the answer.
    """
    counts: dict[str, int] = {}
    for row in rows:
        if not row.get("launched") or row.get("oracle_state") in SCORED_STATES:
            continue
        label = label_for(row.get("failure_class"))
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def summarize(counts: dict[str, int]) -> str:
    """One sentence naming the reasons, for a reader who sees only a rate."""
    if not counts:
        return ""
    parts = [f"{count} {label}" for label, count in counts.items()]
    return "; ".join(parts)


# The contract is one JSON object holding only `artifacts`. A candidate can be
# found by pattern instead of by trying to decode at every brace, which matters
# because a rejected output can be a quarter megabyte of streamed reasoning.
_ENVELOPE_START = re.compile(r'\{\s*"artifacts"\s*:')

REFUSED_AT_ENVELOPE = "_MalformedAttempt"


def envelope_recoverable(text: str) -> bool:
    """Is a complete answer envelope present anywhere in this output?

    Refusing the answer was right: the contract says the whole document is the
    envelope. But a refusal is not a diagnosis, and this separates the two
    things a refusal hides. One harness put a sentence of prose in front of a
    complete answer. Another streamed reasoning until the cap and never wrote
    an answer at all. Only the second is a capability gap.

    Nothing here grades the answer and nothing here accepts it. It reports
    whether there was an answer to accept.
    """
    for match in _ENVELOPE_START.finditer(text):
        try:
            value, _ = json.JSONDecoder().raw_decode(text[match.start():])
        except ValueError:
            continue
        if isinstance(value, dict) and set(value) == {"artifacts"} \
                and isinstance(value["artifacts"], dict):
            return True
    return False


def recovery(rows: list[dict[str, Any]], read_text: Callable[[str], str | None]) -> dict | None:
    """Of the answers refused at the envelope, how many held one anyway.

    Only envelope refusals are counted. An artifact that was invalid inside an
    accepted envelope already reached a checker and has its own verdict, and a
    timeout has no output to look at.

    `read_text` is injected so this stays a function of what it is handed. A
    path it cannot read is counted as unread and never guessed at, because a
    missing file and a missing envelope are not the same finding.
    """
    refused = [row for row in rows
               if row.get("launched") and row.get("failure_class") == REFUSED_AT_ENVELOPE]
    if not refused:
        return None
    held = unread = 0
    for row in refused:
        text = None
        for field in ("raw_output_path", "rejected_output_path"):
            text = read_text(str(row.get(field) or ""))
            if text is not None:
                break
        if text is None:
            unread += 1
        elif envelope_recoverable(text):
            held += 1
    return {"refused": len(refused), "held_an_envelope": held, "unread": unread}


def recovery_sentence(counts: dict | None) -> str:
    """The recovery counts as one clause, for a reader who sees only a rate."""
    if not counts or not counts.get("refused"):
        return ""
    tail = f", {counts['unread']} with no output to read" if counts["unread"] else ""
    return (f"{counts['held_an_envelope']} of {counts['refused']} refused answers held a "
            f"complete envelope behind other text{tail}")
