"""validator.py -- semantic validation for a canonical Record.

schema.py keeps Record a pure envelope: its constructor rejects only a wrong
`canon_schema` and a missing structural key. Everything else -- an unknown
kind, a temporal block on a kind that forbids one, a personality-block with no
body, a research-artifact-ref whose digest is not a sha256 -- is a semantic
error, and this module is where those live.

`validate_record(rec)` returns a list of human-readable problem strings. An
empty list means the record is valid. The list form (rather than raise-on-
first) is deliberate: a fixture or an importer wants every problem at once,
not a fix-one-rerun loop.

The per-kind required-field tables are the F0 contract for what each kind
must carry. They are intentionally small; a downstream slice may add optional
fields to `data` without touching the validator, but it may not remove a
required one without editing this table and its fixtures together.
"""
from __future__ import annotations

from .schema import (
    ADR_STATUSES,
    ALL_KINDS,
    EPISODIC_LAYERS,
    WORKSPACE_KINDS,
    KIND_ADR_DECISION,
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    KIND_RESEARCH_ARTIFACT_REF,
    KIND_SYNTHESIZED_PERSONA_L3,
    PERSONA_LAYER,
    SCOPES,
    TEMPORAL_KINDS,
    Record,
    is_sha256,
)
from .validator_workspace import (
    REQUIRED as _WORKSPACE_REQUIRED,
    check_applies_to,
    check_rejected_alternatives,
    check_workspace_kind,
)

# Per-kind required keys in `data`, each with the type(s) the value must have.
# str means "a non-empty string"; the emptiness check is applied below.
_REQUIRED: dict[str, dict[str, type | tuple[type, ...]]] = {
    KIND_PERSONALITY_BLOCK: {
        "title": str,
        "body": str,
    },
    KIND_EPISODIC_MEMORY: {
        "layer": str,
        "text": str,
        "source_ids": list,
    },
    KIND_SYNTHESIZED_PERSONA_L3: {
        "layer": str,
        "text": str,
        "source_ids": list,
    },
    KIND_ADR_DECISION: {
        "title": str,
        "status": str,
        "context": str,
        "decision": str,
    },
    KIND_RESEARCH_ARTIFACT_REF: {
        "artifact_hash": str,
        "locator": str,
    },
    **_WORKSPACE_REQUIRED,
}


def _check_required(kind: str, data: dict) -> list[str]:
    problems: list[str] = []
    spec = _REQUIRED[kind]
    for key, typ in spec.items():
        if key not in data:
            problems.append(f"{kind}: data missing required field {key!r}")
            continue
        value = data[key]
        if not isinstance(value, typ):
            want = typ.__name__ if isinstance(typ, type) else "/".join(t.__name__ for t in typ)
            problems.append(f"{kind}: data field {key!r} must be {want}, got {type(value).__name__}")
            continue
        if isinstance(value, str) and value == "":
            problems.append(f"{kind}: data field {key!r} must not be empty")
    return problems


def validate_record(rec: Record) -> list[str]:
    """Return a list of problem strings for `rec`; empty means valid."""
    problems: list[str] = []

    # Envelope checks. None of scope, id, or data-is-dict depends on the kind,
    # so all of them run even when the kind is unknown -- a caller wants every
    # problem at once, not a fix-one-rerun loop.
    known_kind = rec.kind in ALL_KINDS
    if not known_kind:
        problems.append(f"unknown kind {rec.kind!r}; expected one of {list(ALL_KINDS)}")

    if rec.scope not in SCOPES:
        problems.append(f"unknown scope {rec.scope!r}; expected one of {list(SCOPES)}")

    if not isinstance(rec.id, str) or rec.id == "":
        problems.append("id must be a non-empty string")

    data_is_dict = isinstance(rec.data, dict)
    if not data_is_dict:
        problems.append(f"data must be a dict, got {type(rec.data).__name__}")

    # Provenance receipt and temporal block. Both are checked for shape here;
    # neither check needs a known kind, except the temporal kind-support rule.
    _check_common(rec, problems)
    problems.extend(_check_temporal(rec, known_kind))

    # Per-kind required fields and kind-specific constraints need both a known
    # kind (to index the _REQUIRED table) and a dict payload to run at all.
    if known_kind and data_is_dict:
        problems.extend(_check_required(rec.kind, rec.data))
        problems.extend(_check_kind_specific(rec))

    return problems


def _check_temporal(rec: Record, known_kind: bool) -> list[str]:
    """Temporal-block checks. The kind-support rule needs a known kind; the
    `valid_until` and `supersedes` value checks are kind-independent and run for
    any record that carries a temporal block."""
    problems: list[str] = []
    temporal = rec.temporal
    if temporal is None:
        return problems
    if known_kind and rec.kind not in TEMPORAL_KINDS:
        problems.append(
            f"{rec.kind}: carries a temporal block but this kind does not support one"
        )
    vt = temporal.valid_until
    if vt is not None and (not isinstance(vt, int) or isinstance(vt, bool) or vt < 0):
        problems.append(f"{rec.kind}: temporal.valid_until must be a non-negative int or None")
    sup = temporal.supersedes
    if sup is not None and (not isinstance(sup, str) or sup == ""):
        problems.append(f"{rec.kind}: temporal.supersedes must be a non-empty string or None")
    return problems


def _check_kind_specific(rec: Record) -> list[str]:
    """Constraints that apply to a single kind (enum-valued fields, digests)."""
    problems: list[str] = []
    data = rec.data
    if rec.kind == KIND_PERSONALITY_BLOCK:
        problems.extend(check_applies_to(data))
    elif rec.kind == KIND_EPISODIC_MEMORY:
        layer = data.get("layer")
        if layer not in EPISODIC_LAYERS:
            problems.append(
                f"episodic-memory: layer must be one of {list(EPISODIC_LAYERS)}, got {layer!r}"
            )
    elif rec.kind == KIND_SYNTHESIZED_PERSONA_L3:
        layer = data.get("layer")
        if layer != PERSONA_LAYER:
            problems.append(
                f"synthesized-persona-l3: layer must be {PERSONA_LAYER!r}, got {layer!r}"
            )
    elif rec.kind == KIND_ADR_DECISION:
        status = data.get("status")
        if status not in ADR_STATUSES:
            problems.append(
                f"adr-decision: status must be one of {list(ADR_STATUSES)}, got {status!r}"
            )
        problems.extend(check_rejected_alternatives(data))
    elif rec.kind in WORKSPACE_KINDS:
        problems.extend(check_workspace_kind(rec))
    elif rec.kind == KIND_RESEARCH_ARTIFACT_REF:
        digest = data.get("artifact_hash")
        if digest is not None and not is_sha256(digest):
            problems.append(
                "research-artifact-ref: artifact_hash must be a lowercase 64-hex sha256 digest"
            )
    return problems


def _check_common(rec: Record, problems: list[str]) -> None:
    """Provenance checks that apply to every kind."""
    prov = rec.provenance
    if not isinstance(prov.harness, str) or prov.harness == "":
        problems.append("provenance.harness must be a non-empty string")
    if not is_sha256(prov.source_hash):
        problems.append("provenance.source_hash must be a lowercase 64-hex sha256 digest")
    if prov.create_ord is not None and (
        not isinstance(prov.create_ord, int) or isinstance(prov.create_ord, bool) or prov.create_ord < 0
    ):
        problems.append("provenance.create_ord must be a non-negative int or None")
    # The four nullable string fields carry the same envelope-type contract as
    # harness; an int here is an envelope violation the validator should catch.
    for name in ("native_id", "session_id", "create_time", "model_slug"):
        value = getattr(prov, name)
        if value is not None and not isinstance(value, str):
            problems.append(f"provenance.{name} must be a string or None")


def is_valid(rec: Record) -> bool:
    return not validate_record(rec)
