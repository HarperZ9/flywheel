"""channel.py -- access classes, reasoning channels, gap codes and the two record types.

A ReasoningRecord is one model turn as an outside observer saw it. A GapRecord
is a quantity that could not be measured with the access the run had. Every
field is a string, a digest or a count, so either record can enter a sealed
receipt with no floats. Reasoning text itself never enters a record: the
record holds {sha256, bytes}, and the caller keeps the text in its own custody.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# Access ladder (MODULE-DESIGN section 1). A component declares the minimum it needs.
A0, A1R, A1S, A1C, A2, A3, A4, A5 = "A0", "A1r", "A1s", "A1c", "A2", "A3", "A4", "A5"
ACCESS_CLASSES = (A0, A1R, A1S, A1C, A2, A3, A4, A5)
ACCESS_MEANING = {
    A0: "black box: prompt in, final output and tool calls out",
    A1R: "the model's own reasoning text, untransformed",
    A1S: "reasoning text written by a separate summarizer or post-processor",
    A1C: "reasoning an agent chose to emit over a protocol",
    A2: "truncate, edit, prefill and resample the reasoning",
    A3: "token log probabilities and hidden states",
    A4: "add or ablate directions in activations",
    A5: "fine-tune, RL, train probes on the model's own data",
}

# Reasoning channels.
RAW = "raw"
SUMMARY_SEPARATE = "summary_separate_model"
SUMMARY_UNKNOWN = "summary_unknown_origin"
UNSPECIFIED = "unspecified_trace"
MODEL_CHOSEN = "model_chosen"
PROGRESS = "progress_updates"
NONE = "none"
CHANNELS = (RAW, SUMMARY_SEPARATE, SUMMARY_UNKNOWN, UNSPECIFIED, MODEL_CHOSEN, PROGRESS, NONE)
CHANNEL_CLASS = {RAW: A1R, SUMMARY_SEPARATE: A1S, SUMMARY_UNKNOWN: A1S, UNSPECIFIED: A1S,
                 MODEL_CHOSEN: A1C, PROGRESS: A1S, NONE: A0}

OUTSIDE, LOCAL = "outside_observability", "local_setup"
# Gap codes (MODULE-DESIGN section 6). The first two are existing Flywheel codes.
GAP_CODES = {
    "HIDDEN_REASONING_UNAVAILABLE": OUTSIDE,
    "PROVIDER_REASONING_NOT_RETAINED": LOCAL,
    "NOT_OBSERVABLE_FROM_OUTSIDE": OUTSIDE,
    "PROVIDER_ENCRYPTED": OUTSIDE,
    "SUMMARY_ONLY_CHANNEL": OUTSIDE,
    "REASONING_OMITTED_BY_DEFAULT": LOCAL,
    "REASONING_WRITE_UNAVAILABLE": OUTSIDE,
    "SAMPLING_CONTROL_UNAVAILABLE": OUTSIDE,
    "LOGPROBS_UNAVAILABLE": OUTSIDE,
    "INTERNALS_UNAVAILABLE": OUTSIDE,
    "TRAINING_ACCESS_UNAVAILABLE": OUTSIDE,
    "ACCESS_CLASS_UNAVAILABLE_LOCALLY": LOCAL,
    "INSUFFICIENT_SAMPLE": LOCAL,
    "NOT_DISCLOSED": OUTSIDE,
    "REASONING_TRUNCATED": LOCAL,
    "DOCUMENTATION_UNREAD": LOCAL,
    "DOCUMENTATION_STALE": LOCAL,
    "CONTROL_FAILED": LOCAL,
}

UNOBSERVABLE = "UNOBSERVABLE"
MATCH, DRIFT, UNVERIFIABLE = "MATCH", "DRIFT", "UNVERIFIABLE"

RECORD_DOES_NOT_PROVE = (
    "A record shows what this run could read. Raw reasoning text is sampled output, "
    "not the computation; a summary is a second model's writing about the first "
    "model's reasoning; an opaque field is stored by digest and was never read.")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8", "surrogatepass")


def content_ref(text) -> dict:
    """{sha256, bytes} for a string, or for any JSON value by canonical bytes."""
    if text is None:
        return {"sha256": "", "bytes": "0"}
    data = text.encode("utf-8", "surrogatepass") if isinstance(text, str) else canonical_bytes(text)
    return {"sha256": sha256_hex(data), "bytes": str(len(data))}


def count_str(value) -> str:
    """A provider count as a digit string, or 'unknown'. Never a float."""
    if isinstance(value, bool) or value is None:
        return "unknown"
    if isinstance(value, int) and value >= 0:
        return str(value)
    if isinstance(value, str) and value.isdigit():
        return value
    return "unknown"


@dataclass
class GapRecord:
    gap_code: str
    component: str
    required_class: str = ""
    available_class: str = ""
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.gap_code not in GAP_CODES:
            raise ValueError(f"unknown gap code {self.gap_code!r}")

    @property
    def scope(self) -> str:
        return GAP_CODES[self.gap_code]

    def to_dict(self) -> dict:
        return {"gap_code": self.gap_code, "component": self.component,
                "required_class": self.required_class, "available_class": self.available_class,
                "evidence": self.evidence, "scope": self.scope}


@dataclass
class ReasoningRecord:
    run_id: str
    turn_index: int
    provider: str
    endpoint: str = ""
    requested_model: str = ""
    served_model: str = ""
    channel: str = NONE
    display_mode: str = "unset"
    summarizer: str = "not_applicable"
    reasoning_text: str | None = None          # custody of the caller; digested in to_dict
    reasoning_tokens_reported: str = "unknown"
    truncated: bool = False
    logprobs: list | None = None               # custody of the caller; digested in to_dict
    opaque_fields: list = field(default_factory=list)
    answer: str | None = None
    tool_calls: list = field(default_factory=list)
    sampling: dict = field(default_factory=dict)
    extra_classes: tuple = ()                  # for example A3 when logprobs cover the reasoning

    @property
    def access_class(self) -> str:
        return CHANNEL_CLASS.get(self.channel, A0) if self.reasoning_text else A0

    def classes(self) -> tuple:
        return tuple(dict.fromkeys((self.access_class,) + tuple(self.extra_classes)))

    def record_id(self) -> str:
        return "rr_" + sha256_hex(canonical_bytes(self.to_dict(with_id=False)))[:16]

    def to_dict(self, *, with_id: bool = True) -> dict:
        out = {
            "run_id": self.run_id, "turn_index": str(self.turn_index),
            "provider": self.provider, "endpoint": self.endpoint,
            "requested_model": self.requested_model, "served_model": self.served_model,
            "access_class": self.access_class, "access_classes": list(self.classes()),
            "channel": self.channel if self.reasoning_text else NONE,
            "display_mode": self.display_mode, "summarizer": self.summarizer,
            "reasoning_text": content_ref(self.reasoning_text or None),
            "reasoning_tokens_reported": self.reasoning_tokens_reported,
            "truncated": "true" if self.truncated else "false",
            "logprobs_ref": content_ref(self.logprobs) if self.logprobs else "absent",
            "opaque_fields": list(self.opaque_fields),
            "answer": content_ref(self.answer or None),
            "tool_calls": [content_ref(t) for t in self.tool_calls],
            "sampling": {k: str(v) for k, v in sorted(self.sampling.items())},
            "does_not_prove": RECORD_DOES_NOT_PROVE,
        }
        if with_id:
            out = {"record_id": self.record_id(), **out}
        return out


def has_class(records, needed: str) -> bool:
    return any(needed in r.classes() for r in records)
