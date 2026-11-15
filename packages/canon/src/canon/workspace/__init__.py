"""canon.workspace -- per-project state that survives a change of model or tool.

A developer who moves a repository from one agent to another loses the working
state that lived in the old tool's session: what they were doing, what is still
open, what was decided and what was tried and dropped, and which quirks of the
environment bite. This package keeps that state as canon records bound to one
project, and renders it for the next tool.

  identity.py   a stable project id from the repository's remote or its path
  rows.py       the stored row that binds a record to its project
  store.py      one store per project, and the read rule that keeps them apart
  pool.py       the records one project's render may read
  moves.py      promotion to global and adoption from another project

Nothing here reads a provider's private database, and nothing crosses from one
project into another without being named by the caller.
"""
from __future__ import annotations

from canon.workspace.identity import (
    ProjectIdentity,
    ProjectIdentityError,
    derive_identity,
    normalize_remote,
)
from canon.workspace.rows import (
    STATE_ACCEPTED,
    STATE_PROPOSED,
    ProjectRow,
    RowError,
)
from canon.workspace.moves import adopt, promote
from canon.workspace.pool import project_pool, visible_records
from canon.workspace.store import (
    IsolationError,
    ProjectStore,
    StoreError,
    default_store_root,
)

__all__ = [
    "IsolationError",
    "ProjectIdentity",
    "ProjectIdentityError",
    "ProjectRow",
    "ProjectStore",
    "RowError",
    "STATE_ACCEPTED",
    "STATE_PROPOSED",
    "StoreError",
    "adopt",
    "default_store_root",
    "derive_identity",
    "normalize_remote",
    "project_pool",
    "promote",
    "visible_records",
]
