"""store.py -- one record store per project, and the rule that keeps them apart.

Layout under a store root (default `~/.canon/store`, or `CANON_STORE`):

    projects/<project_id>/records.jsonl    accepted rows for that project
    projects/<project_id>/proposed.jsonl   proposed rows awaiting a decision
    projects/<project_id>/log.jsonl        every write, promotion and decision
    projects/<project_id>/project.json     the path-clean identity
    global/records.jsonl                   rows promoted to global scope
    global/log.jsonl                       every promotion into global

Isolation is enforced on read, not assumed from the directory name. Every row
names its project, and reading a file refuses the whole file when any row names
a different project: a misfiled row is corruption, so it is reported rather than
filtered out. Another project's records are reachable only through
`pool.visible_records(..., include_projects=...)`, which reads that project's
own file and tags every record with the project it came from.

New records land in `workspace` scope for the store's project. The store refuses
a `global` record on `put`; `moves.promote` is the only way into global scope,
and it writes a log entry in both the project log and the global log.

Writers take the run lock for the project (and for global during a promotion),
so two processes cannot interleave a read-modify-write on one file.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping

from canon.schema import SCOPE_WORKSPACE, Record
from canon.workspace.identity import ProjectIdentity, is_project_id
from canon.workspace.scrub import secrets_in
from canon.workspace.rows import (
    STATE_ACCEPTED,
    STATE_PROPOSED,
    ProjectRow,
    encode_rows,
)
from canon.workspace.store_io import (  # noqa: F401  (re-exported)
    LOG_SCHEMA,
    IsolationError,
    append_log,
    read_bound,
    record_digest,
    run_lock,
    write_atomic,
)

STORE_ENV = "CANON_STORE"
RECORDS_FILE = "records.jsonl"
PROPOSED_FILE = "proposed.jsonl"
LOG_FILE = "log.jsonl"
PROJECT_FILE = "project.json"


class StoreError(Exception):
    """The store cannot complete a write: an unknown record, a global record
    offered to `put`, or a project directory that names another project."""


class SecretRefused(StoreError):
    """A record offered to the store still carries a secret-shaped value."""


class AcceptConflict(StoreError):
    """The accepted record a proposal was built from has changed since, so
    accepting the proposal would erase the newer version."""


def default_store_root(environ: Mapping[str, str]) -> Path:
    configured = environ.get(STORE_ENV)
    return Path(configured) if configured else Path.home() / ".canon" / "store"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProjectStore:
    """The store for one project. Construct it with a ProjectIdentity to write;
    a bare project id gives a store that can read but never writes the
    identity manifest."""

    def __init__(self, root: str | Path, project: ProjectIdentity | str,
                 *, clock=_utc_now) -> None:
        self.root = Path(root)
        self.identity = project if isinstance(project, ProjectIdentity) else None
        pid = project.project_id if self.identity else project
        if not is_project_id(pid):
            raise StoreError(f"not a project id: {pid!r}")
        self.project_id: str = pid
        self.clock = clock
        self._manifest_checked = False

    # ---- paths ------------------------------------------------------------

    def project_dir(self) -> Path:
        return self.root / "projects" / self.project_id

    def global_dir(self) -> Path:
        return self.root / "global"

    # ---- reads ------------------------------------------------------------

    def rows(self, state: str = STATE_ACCEPTED) -> list[ProjectRow]:
        name = RECORDS_FILE if state == STATE_ACCEPTED else PROPOSED_FILE
        return read_bound(self.project_dir() / name, self.project_id,
                           label=f"projects/{self.project_id}/{name}")

    def records(self) -> list[Record]:
        return [row.record for row in self.rows(STATE_ACCEPTED)]

    def proposals(self) -> list[ProjectRow]:
        return self.rows(STATE_PROPOSED)

    def global_rows(self) -> list[ProjectRow]:
        return read_bound(self.global_dir() / RECORDS_FILE, None,
                           label=f"global/{RECORDS_FILE}")

    def log_entries(self) -> list[dict]:
        path = self.project_dir() / LOG_FILE
        if not path.is_file():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def next_ord(self) -> int:
        """One past every ordinal this project has used, including the records
        it promoted to global, so a promoted record's id is never issued again."""
        promoted = [r for r in self.global_rows() if r.promoted_from == self.project_id]
        ords = [r.record.provenance.create_ord for r in
                self.rows(STATE_ACCEPTED) + self.rows(STATE_PROPOSED) + promoted]
        known = [o for o in ords if isinstance(o, int)]
        return (max(known) + 1) if known else 1

    # ---- writes -----------------------------------------------------------

    def put(self, record: Record, *, state: str = STATE_ACCEPTED,
            origin: dict | None = None, action: str = "put") -> ProjectRow:
        """Store `record` for this project, replacing any row with the same
        (scope, id) in the same state file. A global record is refused."""
        if record.scope != SCOPE_WORKSPACE:
            raise StoreError(
                f"record {record.id!r} has scope {record.scope!r}; new records "
                "are workspace records, and promote is the only way to global")
        leaked = secrets_in([record.to_dict(), origin])
        if leaked:
            raise SecretRefused(
                f"record {record.id!r} carries secret-shaped values {leaked}; "
                "nothing was stored")
        row = ProjectRow(self.project_id, state, record, origin, None)
        with self.locked():
            self.ensure_manifest()
            self.replace_row(row)
            self.log(action, record, {"state": state})
        return row

    def decide(self, record_id: str, *, accept: bool, reason: str,
               force: bool = False) -> ProjectRow:
        """Accept a proposed row (move it to the accepted file) or reject it
        (drop it from the proposed file). Both are logged. An accept is refused
        when the accepted record the proposal was built from has changed since,
        unless `force` says to replace the newer version anyway."""
        with self.locked():
            proposed = self.rows(STATE_PROPOSED)
            match = [r for r in proposed if r.record.id == record_id]
            if not match:
                raise StoreError(f"no proposed record with id {record_id!r}")
            row = match[0]
            if accept and not force:
                self._refuse_stale_base(row)
            rest = [r for r in proposed if r is not row]
            write_atomic(self.project_dir() / PROPOSED_FILE, encode_rows(rest))
            if accept:
                row = replace(row, state=STATE_ACCEPTED)
                self.replace_row(row)
            action = "accept" if accept else "reject"
            self.log(action, row.record, {"reason": reason, "origin": row.origin})
        return row

    def accepted_digest(self, record_id: str) -> str | None:
        """The digest of the accepted record with this id, or None."""
        for row in self.rows(STATE_ACCEPTED):
            if row.record.id == record_id:
                return record_digest(row.record)
        return None

    def _refuse_stale_base(self, row: ProjectRow) -> None:
        origin = row.origin or {}
        if "base_record_sha256" not in origin:
            return
        current = self.accepted_digest(row.record.id)
        if current != origin["base_record_sha256"]:
            state = "was created" if origin["base_record_sha256"] is None else "changed"
            raise AcceptConflict(
                f"the accepted record {row.record.id!r} {state} since this proposal "
                "was made; accepting it would erase that version. Compare the two with "
                "canon workspace list, then accept with --force or reject the proposal")

    # ---- helpers ----------------------------------------------------------

    @contextmanager
    def locked(self) -> Iterator[None]:
        with run_lock(self.root, f"canon-project-{self.project_id}"):
            yield

    def replace_row(self, row: ProjectRow) -> None:
        name = RECORDS_FILE if row.state == STATE_ACCEPTED else PROPOSED_FILE
        current = [r for r in self.rows(row.state) if r.key != row.key]
        write_atomic(self.project_dir() / name, encode_rows(current + [row]))

    def ensure_manifest(self) -> None:
        """Check (once per store object) that the project directory names this
        project, writing the manifest on first use and adding this checkout's
        root digest to the manifest's `checkouts` list."""
        if self._manifest_checked:
            return
        stored = self._manifest()
        if stored is not None and stored.get("project_id") != self.project_id:
            raise StoreError("project directory names another project")
        if self.identity is not None:
            known = list(stored.get("checkouts", [])) if stored else []
            if stored is None or self.identity.checkout not in known:
                manifest = {**self.identity.to_public(),
                            "checkouts": sorted(set(known) | {self.identity.checkout})}
                write_atomic(self.project_dir() / PROJECT_FILE,
                             json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        elif stored is None:
            raise StoreError("a store opened by id alone does not write")
        self._manifest_checked = True

    def _manifest(self) -> dict | None:
        path = self.project_dir() / PROJECT_FILE
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def checkout_notice(self) -> str | None:
        """A one-line notice when this checkout is new to a project other
        checkouts already use, since two unrelated repositories can share a
        remote (two apps cloned from one starter) and would read each other's
        records. None when the checkout is known or the project is new."""
        stored = self._manifest() if self.identity is not None else None
        known = stored.get("checkouts", []) if stored else []
        if not known or self.identity.checkout in known:
            return None
        return (f"this checkout is new to project {self.project_id} ({self.identity.label}), "
                f"which {len(known)} other checkout(s) already use. If it is a different "
                "project, split it with `git config canon.project <name>` or a different "
                "remote; if it is the same project (a clone or a worktree), carry on")

    def log(self, action: str, record: Record, detail: dict) -> None:
        append_log(self.project_dir() / LOG_FILE, action, record,
                    {**detail, "project_id": self.project_id}, self.clock())
