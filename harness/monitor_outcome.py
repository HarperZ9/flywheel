"""Keep a monitor judgment and an independently verified outcome apart.

The question this answers is whether a monitor flagged a sample that an
independent check later found to be a bad outcome. Answering it needs three
things held separately: what the monitor said, what actually happened, and who
established what actually happened.

`harness.inspect_evidence` supplies the first part of the ingestion and is used
unmodified. It hashes the source bytes, refuses a duplicate `(id, epoch)`, and
already records `semantic_verification: UNVERIFIABLE` so a reported success is
never mistaken for a checked one. It has no notion of a monitor: every scorer
arrives as a flat `{scorer, value}` pair, and the Control Tower monitor
extensions do not survive it. `harness.monitor_outcome_adapters` reads those
extensions from the same bytes, by declared variant.

The rule this module exists to enforce: **an outcome is absent until an
independent source supplies it.** The evaluation log's own grader is not that
source. A log can report success for a sample whose work was never done, which
is the failure the whole exercise is about. So `attach_outcomes` takes outcomes
from the caller, records where each came from, and leaves every sample it was
not given as `absent` rather than inheriting the log's verdict.

No threshold lives here. Turning a monitor value into a flag is a decision with
a review budget attached, and it belongs to whoever sets that budget, recorded
alongside the result rather than buried in a default.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .monitor_outcome_adapters import (
    ABSENT,
    ADAPTERS,
    SCORED,
    UNSCORED,
    UNSUPPORTED,
    MonitorAdapterError,
    read_monitor,
)

SCHEMA = "flywheel.monitor-outcome/v1"

# Where an outcome came from. Only the first is independent of the log.
INDEPENDENT = "independent_check"
SOURCE_LOG = "source_log"
OUTCOME_SOURCES = (INDEPENDENT, SOURCE_LOG)

DOES_NOT_PROVE = (
    "A monitor value is a behavioural observation under one experimental setup. "
    "It is not a measurement of intent and not a general alignment verdict.",
    "An outcome recorded here is only as independent as the source named beside "
    "it. An outcome sourced from the evaluation log is not an independent check.",
    "Coverage counts describe this log. They do not establish a detection rate, "
    "a false-alarm rate, or that a monitor would catch anything it has not seen.",
    "A sample with no independent outcome is unresolved, not a success.",
)


class MonitorOutcomeError(ValueError):
    """The join could not be performed as declared."""


def _sample_key(sample_id: object, epoch: object) -> tuple:
    """The importer's own key shape, so a str "3" never collides with an int 3."""
    return ((type(sample_id).__name__, str(sample_id)), epoch)


def build_monitor_record(raw: bytes, *, adapter: str,
                         monitor_scorer: str = "monitor") -> dict[str, Any]:
    """Read the monitor side of a log. Outcomes are deliberately left absent."""
    if adapter not in ADAPTERS:
        raise MonitorOutcomeError(
            f"unsupported adapter {adapter!r}; declared adapters are {ADAPTERS}")
    if type(raw) is not bytes:
        raise MonitorOutcomeError("source must be raw bytes, so the hash matches the import")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        root = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MonitorOutcomeError(f"source is not UTF-8 JSON: {error}") from None
    if type(root) is not dict:
        raise MonitorOutcomeError("source root must be an object")

    samples_raw = root.get("samples")
    if samples_raw is None:
        samples_raw = []
    if type(samples_raw) is not list:
        raise MonitorOutcomeError("samples must be an array")

    seen: set[tuple] = set()
    samples: list[dict[str, Any]] = []
    for index, item in enumerate(samples_raw):
        if type(item) is not dict:
            raise MonitorOutcomeError(f"sample {index} must be an object")
        key = _sample_key(item.get("id"), item.get("epoch"))
        if key in seen:
            # The importer refuses this too. Refusing it here as well means a
            # caller cannot join through the sidecar to dodge that check.
            raise MonitorOutcomeError(
                f"duplicate sample id and epoch at index {index}; refusing to merge")
        seen.add(key)
        try:
            monitor = read_monitor(item.get("scores"), index, adapter=adapter,
                                   monitor_scorer=monitor_scorer)
        except MonitorAdapterError as error:
            raise MonitorOutcomeError(str(error)) from None
        samples.append({
            "id": item.get("id"),
            "epoch": item.get("epoch"),
            "monitor": monitor,
            "outcome": {"status": ABSENT, "value": None, "source": None,
                        "checked_by": None},
        })

    return {
        "schema": SCHEMA,
        "adapter": adapter,
        "monitor_scorer": monitor_scorer,
        "source": {"sha256": digest, "bytes": len(raw)},
        "samples": samples,
        "coverage": _coverage(samples),
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def attach_outcomes(record: dict[str, Any], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach independently established outcomes to a monitor record.

    Each outcome needs `id`, `epoch`, `value`, `source` and `checked_by`. An
    outcome for a sample the log does not contain is an error rather than a new
    row, because inventing a row would change the denominator.
    """
    if record.get("schema") != SCHEMA:
        raise MonitorOutcomeError(f"record schema must be {SCHEMA}")
    by_key = {_sample_key(s["id"], s["epoch"]): s for s in record["samples"]}
    for position, outcome in enumerate(outcomes):
        if type(outcome) is not dict:
            raise MonitorOutcomeError(f"outcome {position} must be an object")
        for field in ("id", "epoch", "value", "source", "checked_by"):
            if field not in outcome:
                raise MonitorOutcomeError(f"outcome {position} requires {field!r}")
        source = outcome["source"]
        if source not in OUTCOME_SOURCES:
            raise MonitorOutcomeError(
                f"outcome {position} source must be one of {OUTCOME_SOURCES}")
        key = _sample_key(outcome["id"], outcome["epoch"])
        target = by_key.get(key)
        if target is None:
            raise MonitorOutcomeError(
                f"outcome {position} names a sample absent from the log: {key}")
        if target["outcome"]["status"] != ABSENT:
            raise MonitorOutcomeError(
                f"outcome {position} would overwrite an outcome already attached")
        target["outcome"] = {
            "status": "verified" if source == INDEPENDENT else "reported",
            "value": outcome["value"],
            "source": source,
            "checked_by": outcome["checked_by"],
        }
    record["coverage"] = _coverage(record["samples"])
    return record


def _coverage(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Denominators, with every state counted and none folded into another."""
    monitor_states = {SCORED: 0, UNSCORED: 0, ABSENT: 0, UNSUPPORTED: 0}
    outcome_states = {"verified": 0, "reported": 0, ABSENT: 0}
    action_states = {SCORED: 0, UNSCORED: 0, ABSENT: 0, UNSUPPORTED: 0}
    for sample in samples:
        monitor_states[sample["monitor"]["status"]] += 1
        outcome_states[sample["outcome"]["status"]] += 1
        for action in sample["monitor"]["actions"]:
            action_states[action["status"]] += 1
    return {
        "eligible": len(samples),
        "monitor": dict(monitor_states),
        "outcome": dict(outcome_states),
        "actions": dict(action_states),
        # Named so a reader cannot mistake it for a detection rate. It is the
        # number of samples where both sides are present enough to compare.
        "comparable": sum(
            1 for s in samples
            if s["monitor"]["status"] == SCORED and s["outcome"]["status"] == "verified"
        ),
    }


def comparable_pairs(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The samples where a monitor value and an independent outcome both exist.

    Everything else is excluded here and stays counted in `coverage`, so an
    exclusion can never quietly shrink a denominator.
    """
    pairs = []
    for sample in record["samples"]:
        monitor, outcome = sample["monitor"], sample["outcome"]
        if monitor["status"] != SCORED or outcome["status"] != "verified":
            continue
        pairs.append({
            "id": sample["id"],
            "epoch": sample["epoch"],
            "monitor_value": monitor["summary_value"],
            "outcome_value": outcome["value"],
            "checked_by": outcome["checked_by"],
        })
    return pairs
