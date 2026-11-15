"""canon.backends -- the storage seam (F1).

One Protocol, MemoryBackend, and four adapters that satisfy it:

  FilesBackend      one JSON file per record; drops audit-chain
  SqliteBackend     single-file SQLite + hash-chained audit; drops nothing
  MnemeBackend      the two memory kinds over an injected mneme Store; the
                    temporal home; drops arbitrary-kind, relations,
                    foreign-provenance
  FlywheelBackend   authored/graph kinds over an injected flywheel store;
                    drops temporal

Every backend declares what a round-trip through it loses (`declared_drops()`)
and refuses -- rather than silently flattening -- a record that would lose a
record-enforceable capability it dropped. See project-docs/F1-BACKENDS.md.
"""
from __future__ import annotations

from .base import (
    CAP_ARBITRARY_KIND,
    CAP_AUDIT_CHAIN,
    CAP_FOREIGN_PROVENANCE,
    CAP_RELATIONS,
    CAP_TEMPORAL,
    CAPABILITIES,
    RECORD_ENFORCEABLE,
    BackendError,
    DropError,
    MemoryBackend,
    MissingSupersedeTarget,
    UnsupportedKind,
    capabilities_required,
    flatten_for_drops,
    guard_put,
    record_key,
    split_key,
    temporal_in_use,
)
from .files import FilesBackend
from .flywheel import FlywheelBackend
from .mneme import MnemeBackend
from .sqlite import SqliteBackend

__all__ = [
    "MemoryBackend",
    "BackendError",
    "UnsupportedKind",
    "DropError",
    "MissingSupersedeTarget",
    "FilesBackend",
    "SqliteBackend",
    "MnemeBackend",
    "FlywheelBackend",
    "CAPABILITIES",
    "RECORD_ENFORCEABLE",
    "CAP_TEMPORAL",
    "CAP_AUDIT_CHAIN",
    "CAP_RELATIONS",
    "CAP_ARBITRARY_KIND",
    "CAP_FOREIGN_PROVENANCE",
    "record_key",
    "split_key",
    "temporal_in_use",
    "capabilities_required",
    "flatten_for_drops",
    "guard_put",
]
