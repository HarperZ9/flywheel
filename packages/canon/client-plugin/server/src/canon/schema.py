"""schema.py -- the one canonical record for the memory-bank container.

F0 fixes a single record envelope that every backend adapter and every
render target aims at, so no downstream slice invents its own shape. A
record is provider-neutral: it does not know whether it came from a Claude
transcript, a ChatGPT export, a Hermes SOUL.md, or an authored block, and it
does not know which store will hold it. Five kinds share one envelope:

  personality-block        an authored block of the operator's canon
  episodic-memory          a raw turn or an extracted fact (mneme L0/L1/L2)
  synthesized-persona-l3   a persona profile synthesized from facts (mneme L3)
  adr-decision             a decision record (shape here; placement in F3)
  research-artifact-ref    a content-addressed reference to external research

W1 adds three workspace-state kinds on the same envelope, stamped
`canon.workspace-state/v1` instead of `canon.record/v1`:

  workspace-focus          what the project is doing now: goal, areas, branch
  work-item                one open or closed piece of work and its status
  environment-constraint   a constraint or a quirk of the environment

A decision record may also carry `rejected_alternatives`, each an option and
the reason it was dropped. Every record of the five F0 kinds keeps its v1 tag
and its bytes.

The envelope carries a provenance receipt on every record and a temporal
block on the kinds that support supersede/valid_until. Ordering prefers a
clock-free ordinal (`create_ord`) over the wall clock so a rebuild from the
same inputs is byte-identical; `create_time` is kept only as a nullable,
non-authoritative convenience.

This module is pure data. It imports no store and writes no file. The
storage seam (the MemoryBackend Protocol and its adapters) is F1; the
declared drops each backend must announce are recorded in
project-docs/F0-DECLARED-DROPS.md and enforced there, not here.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, replace

# The five record kinds. Order is stable and load-bearing for fixtures.
KIND_PERSONALITY_BLOCK = "personality-block"
KIND_EPISODIC_MEMORY = "episodic-memory"
KIND_SYNTHESIZED_PERSONA_L3 = "synthesized-persona-l3"
KIND_ADR_DECISION = "adr-decision"
KIND_RESEARCH_ARTIFACT_REF = "research-artifact-ref"

KINDS = (
    KIND_PERSONALITY_BLOCK,
    KIND_EPISODIC_MEMORY,
    KIND_SYNTHESIZED_PERSONA_L3,
    KIND_ADR_DECISION,
    KIND_RESEARCH_ARTIFACT_REF,
)

# W1: the workspace-state kinds. They share the one envelope but carry their own
# schema tag, canon.workspace-state/v1, so a reader that knows only the five
# canon.record/v1 kinds refuses them by tag rather than misreading them, and
# every canon.record/v1 record stays byte-identical. KINDS stays the v1
# vocabulary; ALL_KINDS is what the validator admits.
KIND_WORKSPACE_FOCUS = "workspace-focus"
KIND_WORK_ITEM = "work-item"
KIND_ENVIRONMENT_CONSTRAINT = "environment-constraint"
WORKSPACE_KINDS = (
    KIND_WORKSPACE_FOCUS,
    KIND_WORK_ITEM,
    KIND_ENVIRONMENT_CONSTRAINT,
)
ALL_KINDS = KINDS + WORKSPACE_KINDS
WORK_ITEM_STATUSES = ("open", "in-progress", "blocked", "done", "dropped")
OPEN_WORK_STATUSES = ("open", "in-progress", "blocked")
CONSTRAINT_CATEGORIES = ("constraint", "quirk")

# The kinds that carry a temporal (supersede/valid_until) block. A
# research-artifact-ref is a content-addressed pointer to an immutable
# artifact; it is not superseded in place (a new artifact is a new ref), so it
# is the one kind for which a temporal block is a schema error. This asymmetry
# is deliberate and is exercised by a negative fixture.
TEMPORAL_KINDS = frozenset({
    KIND_PERSONALITY_BLOCK,
    KIND_EPISODIC_MEMORY,
    KIND_SYNTHESIZED_PERSONA_L3,
    KIND_ADR_DECISION,
    *WORKSPACE_KINDS,
})

# The two render scopes F0 admits. "repo" is deliberately absent: the ~90
# per-repo instruction files stay hand-authored (self-contained-repo
# invariant), so no record is ever scoped to a repo.
SCOPE_GLOBAL = "global"
SCOPE_WORKSPACE = "workspace"
SCOPES = (SCOPE_GLOBAL, SCOPE_WORKSPACE)

# mneme's four memory layers. L0-L2 are episodic; L3 is the synthesized
# persona and lives under its own kind.
EPISODIC_LAYERS = ("L0", "L1", "L2")
PERSONA_LAYER = "L3"

ADR_STATUSES = ("proposed", "accepted", "superseded", "rejected")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def is_sha256(value: object) -> bool:
    """True iff `value` is a lowercase 64-hex sha256 digest string."""
    return isinstance(value, str) and bool(_SHA256_RE.match(value))


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a record came from. `harness` and `source_hash` are the two
    fields a record cannot omit; the rest are nullable because not every
    source supplies them. `create_ord` is the clock-free ordinal used for
    deterministic ordering; `create_time` is a nullable wall-clock convenience
    that is never authoritative."""

    harness: str
    source_hash: str
    native_id: str | None = None
    session_id: str | None = None
    create_ord: int | None = None
    create_time: str | None = None
    model_slug: str | None = None

    def to_dict(self) -> dict:
        return {
            "harness": self.harness,
            "source_hash": self.source_hash,
            "native_id": self.native_id,
            "session_id": self.session_id,
            "create_ord": self.create_ord,
            "create_time": self.create_time,
            "model_slug": self.model_slug,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Provenance":
        return cls(
            harness=d["harness"],
            source_hash=d["source_hash"],
            native_id=d.get("native_id"),
            session_id=d.get("session_id"),
            create_ord=d.get("create_ord"),
            create_time=d.get("create_time"),
            model_slug=d.get("model_slug"),
        )


@dataclass(frozen=True, slots=True)
class Temporal:
    """The supersede/valid_until block. `valid_until` is the ordinal at which
    this record stopped being current (None means it is current); `supersedes`
    is the id of the record this one replaces (None means it replaces nothing).
    Both mirror mneme's temporal columns. The supersession pairing round-trips
    through the mneme backend; the ordinal does not carry a caller-supplied
    value, because mneme assigns `valid_until` from its own clock on supersede.
    The mneme backend refuses an incoming `valid_until` rather than storing it
    as current (see F1-BACKENDS.md). A zero-drop store (SqliteBackend) holds
    both fields verbatim."""

    valid_until: int | None = None
    supersedes: str | None = None

    def to_dict(self) -> dict:
        return {"valid_until": self.valid_until, "supersedes": self.supersedes}

    @classmethod
    def from_dict(cls, d: dict) -> "Temporal":
        return cls(valid_until=d.get("valid_until"), supersedes=d.get("supersedes"))


@dataclass(frozen=True, slots=True)
class Record:
    """One canonical record. `data` is the kind-specific typed payload (a
    plain JSON-able dict); the per-kind required fields are enforced by
    canon.validator, not here, so this dataclass stays a pure envelope.
    `temporal` is present only on the temporal kinds and is None otherwise."""

    kind: str
    id: str
    scope: str
    data: dict
    provenance: Provenance
    temporal: Temporal | None = None

    def to_dict(self) -> dict:
        """Serialize to a plain JSON-able dict. The inverse is from_dict; the
        pair is field-identical for every kind (proved in
        tests/test_schema_roundtrip.py). `data` is deep-copied so the returned
        dict is independent of this frozen record's payload."""
        return {
            "canon_schema": schema_tag_for(self.kind),
            "kind": self.kind,
            "id": self.id,
            "scope": self.scope,
            "data": copy.deepcopy(self.data),
            "provenance": self.provenance.to_dict(),
            "temporal": self.temporal.to_dict() if self.temporal is not None else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Record":
        """Reconstruct a Record from a to_dict() (or json.loads of one). Raises
        KeyError on a missing structural key; semantic validity is the
        validator's job, not this constructor's. `data` is deep-copied so the
        record does not alias the caller's input dict."""
        got = d.get("canon_schema")
        expected = schema_tag_for(d.get("kind"))
        if got != expected:
            raise ValueError(f"expected canon_schema {expected!r}, got {got!r}")
        temporal = d.get("temporal")
        return cls(
            kind=d["kind"],
            id=d["id"],
            scope=d["scope"],
            data=copy.deepcopy(d["data"]),
            provenance=Provenance.from_dict(d["provenance"]),
            temporal=Temporal.from_dict(temporal) if temporal is not None else None,
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Record":
        return cls.from_dict(json.loads(text))

    def with_temporal(self, temporal: Temporal | None) -> "Record":
        return replace(self, temporal=temporal)


def schema_tag_for(kind: object) -> str:
    """The canon_schema tag a record of `kind` carries: the workspace-state tag
    for a workspace-state kind, canon.record/v1 for every other kind. An unknown
    kind gets canon.record/v1, so the validator reports it by name rather than
    the tag check refusing it with a less useful message."""
    return WORKSPACE_STATE_SCHEMA if kind in WORKSPACE_KINDS else SCHEMA


# D-94: canon.record/v1 lives as PIN_RECORD.kind_tag in versions.py; schema
# aliases it here so every downstream reader of `SCHEMA` reads the same bytes,
# and a drift between the pin and the wire literal fails loud at import time.
# The bottom-of-module late import keeps the top-of-file surface clean and
# avoids a cycle (versions.py imports nothing from canon.schema).
from canon.versions import PIN_RECORD, PIN_WORKSPACE_STATE  # noqa: E402

SCHEMA = PIN_RECORD.kind_tag
WORKSPACE_STATE_SCHEMA = PIN_WORKSPACE_STATE.kind_tag
assert SCHEMA == "canon.record/v1", (
    f"PIN_RECORD.kind_tag drifted from the canon.record/v1 wire literal; "
    f"got {SCHEMA!r}")
