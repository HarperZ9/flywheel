"""The custody inventory: every place the tools keep trace-derived data (7.14).

One registry answers "where are my traces, what kind of data sits there, how
is it protected, how long is it kept, and can I export or delete it". Each
entry is a `Store`. A location that holds no trace-derived data (the gateway
token, UI settings) is an `Exemption` with its reason, so nothing written
under FLYWHEEL_HOME, `state/`, the run root or `lanes/` goes unnamed.

Data classes follow the design's section 2.1: C1 content, C2 tool I/O, C3
reasoning, C4 metadata, C5 hashes and derived ids, C6 credentials, C7
personal data, C8 derived forms. `classes=None` marks a store the code read so
far cannot classify; it shows as UNCLASSIFIED with the note that says why.
"""
from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import importlib
import re

SCHEMA = "flywheel.trace-inventory/v1"
DEFAULT_RETENTION = "keep until you delete"
CLASS_NAMES = {"C1": "content", "C2": "tool I/O", "C3": "reasoning",
               "C4": "metadata", "C5": "hashes and derived ids",
               "C6": "credentials", "C7": "personal data", "C8": "derived forms"}
ROOTS = ("home", "state", "run", "lanes", "env", "temp", "client")
PROTECTIONS = ("encrypted", "plaintext-exception", "metadata-only", "outside-custody")
OPERATIONS = ("inventory", "export", "delete")
PACKAGE = re.compile(r"(FW-[0-9]{2}[a-z0-9]*|MN-0[1-3]|CA-0[1-3]|7\.[0-9]{1,2}|D[0-9]{1,2})\Z")
FILES = "harness.trace_inventory_scan.file_inventory"


@dataclass(frozen=True)
class Gap:
    """An operation that does not exist yet: why, and which package closes it."""
    reason: str
    package: str


@dataclass(frozen=True)
class Protection:
    kind: str
    reason: str = ""
    package: str = ""


@dataclass(frozen=True)
class Cap:
    """A limit a store applies, what happens at it, and the test covering it."""
    what: str
    behavior: str
    test: str


@dataclass(frozen=True)
class Store:
    id: str
    name: str
    root: str
    patterns: tuple[str, ...]
    classes: tuple[str, ...] | None
    protection: Protection
    export: str | Gap
    delete: str | Gap
    shape: str = "dir"
    owner_binding: str = "none"
    retention: str = DEFAULT_RETENTION
    caps: tuple[Cap, ...] = ()
    inventory: str | Gap = FILES
    added_by_program: bool = False
    invalidate: bool = False
    env: tuple[str, ...] = ()
    note: str = ""
    evidence: str = "observed"


@dataclass(frozen=True)
class Exemption:
    root: str
    pattern: str
    reason: str


def stores() -> tuple[Store, ...]:
    from .trace_inventory_entries import STORES as core
    from .trace_inventory_entries_ext import STORES as ext
    return core + ext


def exemptions() -> tuple[Exemption, ...]:
    from .trace_inventory_entries_ext import EXEMPTIONS
    return EXEMPTIONS


def get(store_id: str) -> Store:
    for store in stores():
        if store.id == store_id:
            return store
    raise KeyError(store_id)


def classify(root: str, name: str) -> Store | Exemption | None:
    """The registered store or exemption a top-level name under `root` belongs to."""
    for store in stores():
        if store.root == root and any(fnmatch.fnmatchcase(name, p) for p in store.patterns):
            return store
    for exemption in exemptions():
        if exemption.root == root and fnmatch.fnmatchcase(name, exemption.pattern):
            return exemption
    return None


def explain_static(root: str, segment: str, module: str):
    """Why a statically found write location is allowed, or None if it is not.

    `root` "any" is a temporary-directory prefix whose parent the scan cannot
    name; it is explained when any store or exemption declares the prefix.
    """
    from .trace_inventory_entries_ext import STATIC_MODULE_EXEMPTIONS
    for key in (f"{module}:{segment}", module):
        if key in STATIC_MODULE_EXEMPTIONS:
            return STATIC_MODULE_EXEMPTIONS[key]
    if root != "any":
        return classify(root, segment)
    probe = segment.replace("*", "x")
    for candidate in ROOTS:
        found = classify(candidate, probe)
        if found is not None:
            return found
    return None


def resolve(dotted: str):
    """Import `package.module.attr` and return the attribute."""
    module_name, _, attr = dotted.rpartition(".")
    return getattr(importlib.import_module(module_name), attr)


def completeness_errors(entries) -> list[str]:
    """I2 completeness: program stores have real export and delete; every gap
    names a reason and the package that closes it."""
    errors = []
    for store in entries:
        for op in OPERATIONS:
            value = getattr(store, op)
            if isinstance(value, Gap):
                if store.added_by_program and op != "inventory":
                    errors.append(f"{store.id}: added by this program, {op} is a gap")
                if not value.reason.strip() or not PACKAGE.fullmatch(value.package or ""):
                    errors.append(f"{store.id}: {op} gap lacks a reason or package id")
                continue
            try:
                if not callable(resolve(value)):
                    errors.append(f"{store.id}: {op} does not resolve to a callable")
            except (ImportError, AttributeError, ValueError):
                errors.append(f"{store.id}: {op} adapter {value} does not resolve")
    return errors


def validate_document(doc) -> list[str]:
    """Check a `flywheel traces status --json` document against its schema."""
    from .trace_inventory_scan import validate_row
    if type(doc) is not dict or doc.get("schema") != SCHEMA:
        return ["schema is not flywheel.trace-inventory/v1"]
    errors = [f"missing key {k}" for k in ("generated_at", "retention_default",
              "stores", "unregistered", "unclassified", "ledger", "encryption")
              if k not in doc]
    for row in doc.get("stores", []) if type(doc.get("stores")) is list else []:
        errors.extend(validate_row(row))
    for row in doc.get("unregistered", []):
        if set(row) != {"root", "name", "files", "bytes"} or row.get("root") not in ROOTS:
            errors.append("unregistered row is malformed")
    return errors
