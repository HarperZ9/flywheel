"""Null control candidates, so an oracle's discrimination is measured rather than assumed.

A benchmark reports a score. That score is only a measurement if something
exists that ought to fail it. These adapters are that something: they produce
submissions for a task without doing the task, and the floor run asserts that
every configured checker rejects all of them.

Three strategies, ordered by how much they concede to the format:

`empty`   the artifacts exist and hold nothing. A checker that passes this is
          reading paths, not content.
`shape`   every structural requirement is satisfied and every substantive
          field carries the empty value of its own type. Mechanical fields
          (task_id, input hashes) are filled because a provider can derive
          them from its inputs without answering anything. A checker that
          passes this is scoring format compliance.
`echo`    the fixture is handed back as the answer. A checker that passes this
          is scoring the ability to restate the prompt.

None of the three reads a reference answer, and none carries per-checker
knowledge. Adding a checker therefore extends the floor for free, and a
checker that is easier than its own inputs shows up as a breach.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "harness.null-floor-report/v1"
STRATEGIES = ("empty", "shape", "echo")

# Fields a provider can fill from its inputs alone. Hollowing these would test
# the common preamble instead of the checker, and every strategy would collapse
# into the same trivial rejection.
MECHANICAL = ("task_id", "input_sha256s", "receipt_input_sha256s")

HELD = "NULL_FLOOR_HELD"
BREACHED = "NULL_FLOOR_BREACHED"

# A null submission that is rejected is the expected outcome. Only `pass` is a
# breach: `unverifiable` means the checker declined to judge, which is honest.
REJECTING = ("fail", "malformed", "unverifiable")

# Codes the shared preamble emits before any checker runs. A rejection carrying
# only these says the submission never reached the checker, so it is evidence
# about the envelope and not about discrimination. Recording the stage is what
# keeps a floor from holding for the wrong reason.
PREAMBLE_CODES = frozenset({
    "json_invalid", "json_duplicate_key", "artifact_set_mismatch", "artifact_empty",
    "artifact_not_regular", "artifact_not_utf8", "task_id_mismatch",
    "input_hash_mismatch", "markdown_task_id_missing",
})


# The one code that is genuinely ambiguous. The preamble emits `json_invalid`
# when the report will not parse, and the top-level handler emits the same code
# when a checker raises. Only these three reasons come from before a checker
# runs, so the reason is what separates the two, and reading codes alone made
# `shared_task_artifact/v1` look unreachable when the checker had in fact run.
PREAMBLE_REASONS = frozenset({"raw_output_invalid", "response_envelope_invalid",
                              "attempt_path_invalid"})


def rejected_at(failure_codes, reason: str = "") -> str:
    """Which stage threw the candidate out: preamble, checker, or neither."""
    codes = set(failure_codes)
    if not codes:
        return "none"
    if reason:
        return "preamble" if reason in PREAMBLE_REASONS else "checker"
    return "preamble" if codes <= PREAMBLE_CODES else "checker"


@dataclass(frozen=True)
class NullSubmission:
    """Where a null candidate wrote itself, and what it conceded to the format."""
    strategy: str
    raw_output_path: Path
    artifact_paths: dict[str, Path]
    report: dict[str, Any]


def hollow(value: Any) -> Any:
    """The empty value of the same type. Structure survives, content does not."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if isinstance(value, str):
        return ""
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return None


def shape_report(template: dict[str, Any]) -> dict[str, Any]:
    """Same keys, mechanical values kept, every answer emptied."""
    if not isinstance(template, dict):
        raise TypeError("template must be an object keyed by report field")
    return {key: (json.loads(json.dumps(value)) if key in MECHANICAL else hollow(value))
            for key, value in template.items()}


def echo_report(template: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    """The fixture handed back under the report's own field names.

    A field the fixture names is copied verbatim. A field it does not name is
    hollowed, because inventing a value there would be answering rather than
    echoing.
    """
    fixture = fixture if isinstance(fixture, dict) else {}
    out = shape_report(template)
    for key in out:
        if key in MECHANICAL:
            continue
        if key in fixture:
            out[key] = json.loads(json.dumps(fixture[key]))
    return out


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_null_submission(attempt_dir: Path, *, strategy: str, task_id: str,
                          template: dict[str, Any], fixture: dict[str, Any],
                          expected_artifacts: tuple[str, ...] = ("report.json", "report.md"),
                          ) -> NullSubmission:
    """Write one null candidate into `attempt_dir` and describe what it wrote."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    names = sorted(expected_artifacts)
    json_names = [name for name in names if name.endswith(".json")]
    md_names = [name for name in names if name.endswith(".md")]
    if len(json_names) != 1 or len(md_names) != 1:
        raise ValueError("a null submission needs exactly one json and one markdown artifact")

    if strategy == "empty":
        report: dict[str, Any] = {}
    elif strategy == "shape":
        report = shape_report(template)
    else:
        report = echo_report(template, fixture)

    paths = {name: attempt_dir / name for name in names}
    body = "" if strategy == "empty" else json.dumps(report)
    markdown = "" if strategy == "empty" else "# " + task_id + chr(10)
    _write(paths[json_names[0]], body)
    _write(paths[md_names[0]], markdown)

    # The envelope is built from the bytes on disk, not from the strings above.
    # Text mode rewrites a newline on Windows, so an envelope built in memory
    # disagrees with the file the oracle reads and every candidate is thrown out
    # at the preamble for a reason that has nothing to do with the checker. A
    # floor measured that way holds vacuously.
    raw_path = attempt_dir / "output.json"
    envelope = {"artifacts": {json_names[0]: report,
                              md_names[0]: paths[md_names[0]].read_bytes().decode("utf-8")}}
    _write(raw_path, "" if strategy == "empty" else json.dumps(envelope))
    return NullSubmission(strategy, raw_path, paths, report)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(checker_id: str, strategy: str, result: Any) -> dict[str, Any]:
    state = getattr(result, "state", "")
    codes = list(getattr(result, "failure_codes", []))
    reason = str((getattr(result, "evidence", None) or {}).get("reason", ""))
    return {"checker_id": checker_id, "strategy": strategy, "oracle_state": state,
            "failure_codes": codes, "reason": reason,
            "rejected_at": rejected_at(codes, reason), "rejected": state in REJECTING}


def build_null_floor_report(rows: list[dict[str, Any]], *,
                            run_id: str = "") -> dict[str, Any]:
    """Turn per-candidate outcomes into a floor verdict with its denominator.

    A breach names the exact (checker, strategy) pair that passed, because the
    useful part of a floor run is which checker is weaker than its own inputs,
    not the aggregate.
    """
    breaches = [row for row in rows if not row["rejected"]]
    reached = sorted({row["checker_id"] for row in rows
                      if row.get("rejected_at") == "checker"})
    checkers = sorted({row["checker_id"] for row in rows})
    strategies = sorted({row["strategy"] for row in rows})
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "verdict": BREACHED if breaches else HELD,
        "denominator": {"candidates": len(rows), "checkers": len(checkers),
                        "strategies": len(strategies),
                        "checkers_reached": len(reached)},
        "checkers_never_reached": [name for name in checkers if name not in reached],
        "checkers": checkers,
        "strategies": strategies,
        "rows": sorted(rows, key=lambda row: (row["checker_id"], row["strategy"])),
        "breaches": [{"checker_id": row["checker_id"], "strategy": row["strategy"],
                      "oracle_state": row["oracle_state"]} for row in breaches],
        "rows_sha256": _sha(json.dumps(rows, sort_keys=True).encode("utf-8")),
        "does_not_prove": [
            "A held floor does not show the checker rewards a correct answer; it "
            "shows it rejects three specific ways of not answering.",
            "The strategies are exhaustive over nothing. A fourth kind of cheap "
            "candidate may still pass.",
            "This measures the checkers, not the providers. A task no provider "
            "can execute still holds its floor.",
            "A checker listed in checkers_never_reached was not measured at all: "
            "every candidate stopped at the shared preamble.",
        ],
    }
