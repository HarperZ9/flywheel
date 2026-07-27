"""trainer_diagnostics.py -- the frozen trainer-diagnostics contract, as code.

The frozen preregistration deliberately does not implement RL training:
PolicyOptimizer stays an unimplemented Protocol (harness/rl_from_oracle.py).
This module does not change that. It implements the schema and validator that
project-docs/prereg/2026-07-27-trainer-diagnostics-addendum.md freezes, so a
future trainer cannot pick which diagnostics to report after seeing its own
result. The addendum's Section 2 is the source of truth; this module mirrors
it and binds to it by hash so a run can cite the exact frozen text it was
checked against.

The two literature findings behind the contract (arXiv:2601.11061,
arXiv:2512.16912, arXiv:2605.18864, cited in full in the addendum) are that a
verified-reward gain and a spurious-reward gain look identical on pass@1
alone. policy_entropy exposes an entropy-collapse gain; pass_at_k across k
exposes an elicitation gain. Both are required fields, not optional ones.

A missing field is a bug in the writer: the addendum requires every field be
emitted, with an honest null where a measurement could not be taken, so a
missing measurement stays distinguishable from a missing writer. Four fields
carry no honest null (arm, rung, step, n_eval): a record with no arm identity
or no denominator is not a record. Stdlib only.
"""
from __future__ import annotations

from pathlib import Path

from scripts.rung_pins import blob_sha256

# Per addendum Section 2, in the order the addendum lists them.
REQUIRED_FIELDS = (
    "arm",
    "rung",
    "step",
    "policy_entropy",
    "answer_perplexity",
    "pass_at_k",
    "reward_mean",
    "reward_std",
    "kl_to_ref",
    "grad_norm",
    "n_eval",
)

# The seven arms the addendum names. "pass_at_k" is deliberately both an arm
# name (a scoring mode) and a field name (a per-record measurement); the
# addendum keeps both and so does this module.
FROZEN_ARMS = (
    "single",
    "best_of_k",
    "random_of_k",
    "placebo_of_k",
    "pass_at_k",
    "random_reward",
    "format_only_reward",
)

RUNGS = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9")

# arm/rung: no arm identity is not a record. step: no training step is not a
# checkpoint. n_eval: no denominator, every mean/std above it is unreadable.
NON_NULLABLE_FIELDS = ("arm", "rung", "step", "n_eval")
NULLABLE_FIELDS = tuple(f for f in REQUIRED_FIELDS if f not in NON_NULLABLE_FIELDS)

ADDENDUM_RELPATH = Path("project-docs") / "prereg" / "2026-07-27-trainer-diagnostics-addendum.md"


class DiagnosticsError(ValueError):
    """A diagnostics record violates the frozen trainer-diagnostics contract."""


def _is_int_not_bool(value) -> bool:
    # bool is an int subclass in Python; a step or an eval count is never a flag.
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number_not_bool(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_valid_pass_at_k(value) -> bool:
    """A dict of {int-or-int-string k: number}. Any other shape is malformed."""
    if not isinstance(value, dict):
        return False
    for k, v in value.items():
        if isinstance(k, bool):
            return False
        if isinstance(k, int):
            pass
        elif isinstance(k, str):
            try:
                int(k)
            except ValueError:
                return False
        else:
            return False
        if not _is_number_not_bool(v):
            return False
    return True


def validate_record(rec: dict) -> None:
    """Raise DiagnosticsError on any structural violation of Section 2.

    A key ABSENT from rec is the error a writer bug produces; a key present
    with value None is the honest null the addendum asks for and is not by
    itself an error, EXCEPT for arm/rung/step/n_eval, which must be non-null.
    This function only raises; it never returns a value. Whether a null
    nullable field has a recorded reason is a separate concern, handled by
    null_reasons_missing.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in rec]
    if missing:
        raise DiagnosticsError(
            f"missing required field(s): {', '.join(missing)}"
        )

    for field in NON_NULLABLE_FIELDS:
        if rec[field] is None:
            raise DiagnosticsError(
                f"{field!r} must not be null: a record with no {field} is "
                "not a usable diagnostics record"
            )

    if rec["arm"] not in FROZEN_ARMS:
        raise DiagnosticsError(
            f"arm {rec['arm']!r} is not one of the frozen arms {FROZEN_ARMS}"
        )

    if rec["rung"] not in RUNGS:
        raise DiagnosticsError(f"rung {rec['rung']!r} is not one of {RUNGS}")

    if not _is_int_not_bool(rec["step"]) or rec["step"] < 0:
        raise DiagnosticsError(
            f"step must be a non-negative int, got {rec['step']!r}"
        )

    if rec["pass_at_k"] is not None and not _is_valid_pass_at_k(rec["pass_at_k"]):
        raise DiagnosticsError(
            "pass_at_k must be a dict of {int-or-int-string: number}, got "
            f"{rec['pass_at_k']!r}"
        )

    if not _is_int_not_bool(rec["n_eval"]) or rec["n_eval"] <= 0:
        raise DiagnosticsError(
            f"n_eval must be a positive int, got {rec['n_eval']!r}"
        )


def null_reasons_missing(rec: dict) -> list[str]:
    """Nullable fields that are null in rec but unexplained in null_reasons.

    Structural validity is validate_record's job; this is the separate,
    softer concern of whether an honest null carries its reason. A caller
    that wants to REQUIRE reasons calls both; a caller that only wants
    structural validity calls validate_record alone.
    """
    reasons = rec.get("null_reasons") or {}
    return [
        field for field in NULLABLE_FIELDS
        if field in rec and rec[field] is None and field not in reasons
    ]


def cites_addendum_sha256(repo) -> str:
    """sha256 of the addendum file, LF-normalized git-blob form.

    Reuses scripts.rung_pins.blob_sha256, the same hash primitive
    scripts/rung_pins.py's frozen_prereg() checks the parent preregistration
    against, so a diagnostics run binds to this addendum by the identical
    method the parent freeze already uses. Bytes are normalized CRLF -> LF
    first: the frozen value is "sha256 of the git blob content (LF)", and a
    CRLF checkout (autocrlf=true is this repo's default) must still hash to
    the value that was committed.
    """
    path = Path(repo) / ADDENDUM_RELPATH
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return blob_sha256(raw)
