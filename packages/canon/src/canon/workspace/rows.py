"""rows.py -- the stored form of a record: a row bound to one project.

The record envelope stays exactly what F0 defined, byte for byte, so every
existing reader keeps reading it. The project binding lives one level up, in the
row that wraps a record in the store:

    {"schema": "canon.project-row/v1", "project_id": "prj_...", "state":
     "accepted", "record": {...}, "origin": null, "promoted_from": null}

A row names its project. A row copied into another project's file therefore
still names the project it came from, and the store refuses it there instead of
serving it as local. `project_id` is null only in the global file, where a row
arrives by explicit promotion and carries the project it was promoted from.

`state` separates what a person accepted from what a tool proposed. Importers
and drift back-flow only ever write `proposed` rows, and nothing renders a
proposed row until someone accepts it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from canon.schema import Record
from canon.validator import validate_record
from canon.versions import PIN_PROJECT_ROW
from canon.workspace.identity import is_project_id

ROW_SCHEMA = PIN_PROJECT_ROW.kind_tag
STATE_ACCEPTED = "accepted"
STATE_PROPOSED = "proposed"
STATES = (STATE_ACCEPTED, STATE_PROPOSED)
_ROW_KEYS = frozenset({"schema", "project_id", "state", "record", "origin",
                       "promoted_from"})


class RowError(ValueError):
    """A stored row is malformed. Raised with the file and line so a broken
    store is reported where it broke, never skipped."""


@dataclass(frozen=True, slots=True)
class ProjectRow:
    """One stored record and its binding. `origin` is set on a proposed row and
    says where the proposal came from (source name, digest, line, rule)."""

    project_id: str | None
    state: str
    record: Record
    origin: dict | None = None
    promoted_from: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.record.scope, self.record.id)

    def to_dict(self) -> dict:
        return {
            "schema": ROW_SCHEMA,
            "project_id": self.project_id,
            "state": self.state,
            "record": self.record.to_dict(),
            "origin": self.origin,
            "promoted_from": self.promoted_from,
        }

    @classmethod
    def from_dict(cls, d: object) -> "ProjectRow":
        _check_shape(d)
        record = Record.from_dict(d["record"])
        problems = validate_record(record)
        if problems:
            raise RowError(f"row record {record.id!r} is invalid: {problems}")
        return cls(d["project_id"], d["state"], record, d["origin"],
                   d["promoted_from"])


def _check_shape(d: object) -> None:
    if not isinstance(d, dict) or set(d) != _ROW_KEYS:
        raise RowError("row must carry exactly the project-row keys")
    if d["schema"] != ROW_SCHEMA:
        raise RowError(f"expected schema {ROW_SCHEMA!r}, got {d['schema']!r}")
    pid = d["project_id"]
    if pid is not None and not is_project_id(pid):
        raise RowError(f"row project_id is not a project id: {pid!r}")
    if d["state"] not in STATES:
        raise RowError(f"row state must be one of {list(STATES)}")
    if d["origin"] is not None and not isinstance(d["origin"], dict):
        raise RowError("row origin must be an object or null")
    promoted = d["promoted_from"]
    if promoted is not None and not is_project_id(promoted):
        raise RowError("row promoted_from must be a project id or null")
    if not isinstance(d["record"], dict):
        raise RowError("row record must be an object")


def encode_rows(rows: list[ProjectRow]) -> str:
    """One sorted-key JSON object per line, ordered by (scope, id), so the same
    row set always writes the same bytes."""
    ordered = sorted(rows, key=lambda r: r.key)
    return "".join(json.dumps(r.to_dict(), sort_keys=True, ensure_ascii=False)
                   + "\n" for r in ordered)


def decode_rows(text: str, *, source: str) -> list[ProjectRow]:
    """Parse a row file. A malformed line raises RowError naming `source` and
    the line number; a blank line is ignored."""
    rows: list[ProjectRow] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(ProjectRow.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise RowError(f"{source}:{number}: {exc}") from exc
    return rows
