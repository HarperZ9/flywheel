"""Read Control Tower monitor scores out of an Inspect log, by declared variant.

`harness.inspect_evidence` is the ingestion layer and is not changed by this
module. Run on all three Control Tower shapes, it accepts each one and keeps
each score's value as a flat `{scorer, value}` pair. It carries no score
metadata and does not report the omission, so the per-action detail Control
Tower writes there (eval2 `metadata.scores`, eval1 `metadata.action_scores`)
does not survive it, and nothing it emits marks a score as a monitor rather
than a task grader. So the monitor side is read here, from the same bytes the
importer hashed, and kept beside the importer's output rather than inside it.

The shapes were read from Control Tower's writers at `SOURCE_REVISION`, not
from its docs alone. An earlier version of this module was written from the
docs and a design dossier, and a source check found it wrong on all three
formats: it defaulted eval1 to a key Control Tower writes only for an unnamed
monitor, read eval2 drafts as executed actions, classified NOANSWER as
unsupported, and never checked the declared variant against the log. The
controls in tests/test_monitor_outcome_controls.py pin the source shapes.

Every adapter is explicit about its variant, and the declaration is checked
against the log's header marker before anything is read. An unrecognised shape
is reported as unsupported and never guessed at.
"""
from __future__ import annotations

from typing import Any

from .monitor_outcome_eval1 import read_eval1, read_eval1_legacy, shape_of
from .monitor_outcome_eval2 import PASS_KEY, read_eval2
from .monitor_outcome_states import (  # noqa: F401  re-exported for callers
    ABSENT,
    DRAFT,
    EVAL2_TASK,
    SCORED,
    SOURCE_REVISION,
    STATES,
    UNSCORED,
    UNSUPPORTED,
    MonitorAdapterError,
    pointer,
)

ADAPTERS = ("eval2", "eval1", "eval1-legacy")


def check_variant(root: dict, adapter: str) -> None:
    """Refuse a declaration the log's own header contradicts."""
    if adapter not in ADAPTERS:
        raise MonitorAdapterError(
            f"unsupported adapter {adapter!r}; declared adapters are {ADAPTERS}")
    header = root.get("eval") if type(root.get("eval")) is dict else {}
    is_eval2 = header.get("task_registry_name") == EVAL2_TASK
    if adapter == "eval2" and not is_eval2:
        raise MonitorAdapterError(
            f"declared eval2, but eval.task_registry_name is not {EVAL2_TASK!r}")
    if adapter != "eval2" and is_eval2:
        raise MonitorAdapterError(
            f"declared {adapter}, but the log header marks it as eval2 ({EVAL2_TASK!r})")


def resolve_scorer(samples: list, adapter: str, declared: str | None) -> str | None:
    """The score key to read.

    eval2 reads "monitor" and every "monitor-<n>" pass unless one is declared.
    For eval1 the key is monitor_<name>, so defaulting to "monitor" would read
    a real log as having no monitor at all. With no declaration, the one key
    whose values have the declared shape is used; none or several is an error.
    """
    if declared is not None or adapter == "eval2":
        return declared
    found: set[str] = set()
    seen: set[str] = set()
    for sample in samples:
        scores = sample.get("scores") if type(sample) is dict else None
        for key, entry in (scores or {}).items():
            if type(key) is not str or not (key == "monitor" or key.startswith("monitor_")):
                continue
            seen.add(key)
            if shape_of(entry) == adapter:
                found.add(key)
    if len(found) == 1:
        return found.pop()
    if not found:
        raise MonitorAdapterError(
            f"no {adapter} monitor score in the log; monitor keys seen: {sorted(seen) or 'none'}")
    raise MonitorAdapterError(
        f"several {adapter} monitor scores {sorted(found)}; declare monitor_scorer")


def executed_message_ids(sample: dict) -> set | None:
    messages = sample.get("messages")
    if type(messages) is not list:
        return None
    return {m.get("id") for m in messages if type(m) is dict and m.get("id") is not None}


def read_monitor(sample: dict, index: int, *, adapter: str,
                 monitor_scorer: str | None) -> dict[str, Any]:
    """Read one sample's monitor observation under the declared adapter."""
    if adapter not in ADAPTERS:
        raise MonitorAdapterError(
            f"unsupported adapter {adapter!r}; declared adapters are {ADAPTERS}")
    scores = sample.get("scores")
    if scores is None:
        return {"status": ABSENT, "summary_value": None, "actions": [],
                "source_pointer": pointer(index)}
    if type(scores) is not dict:
        raise MonitorAdapterError(f"sample {index}: scores must be an object")
    if adapter == "eval2":
        return read_eval2(scores, index, monitor_scorer, executed_message_ids(sample))
    if adapter == "eval1":
        return read_eval1(scores, index, monitor_scorer)
    return read_eval1_legacy(scores, index, monitor_scorer)

