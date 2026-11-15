"""versions_pin.py -- the pin type and the closed seam vocabulary.

Split out of versions.py so the registry module stays under the size gate as
bands add seams. versions.py re-exports every name here, so a caller keeps
importing from `canon.versions`. This module imports nothing from canon.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class VersionError(Exception):
    """Runtime pin-lookup or compat error. Never leaked from a bad
    constructor (that is `ValueError`)."""


class UnknownPin(VersionError):
    """`pin_for` on a short-name not in `SEAM_PINS`, or
    `pin_from_schema_field` on a kind_tag no registered pin matches."""


class IncompatiblePin(VersionError):
    """`is_compatible` returned False when the caller required equality, or
    `migrate` on a (from, to) pair with no registered migrator."""


class MalformedPin(VersionError):
    """`is_compatible` called on a non-SchemaPin, or `pin_from_schema_field`
    called on a string that fails the kind_tag grammar."""


SEAM_PINS: frozenset[str] = frozenset({
    "record",
    "backend-seam",
    "textblock-grammar",
    "region-marker",
    "frontmatter",
    "vault-note",
    "vault-identity-digest",
    "vault-hub-marker",
    "drift-verdict",
    "writing-gate-register",
    "persona-thesis-payload",
    "reconcile-gate-policy",
    "run-witness",
    "transport-seam",
    "vault-frontend",
    "textutil",
    "project-id",
    "project-row",
    "workspace-state",
    "handoff-receipt",
    "import-report",
    "render-ledger",
})

_WAVE_ONE_NAMES: frozenset[str] = frozenset({
    "atom", "capsule", "omission", "transform-receipt",
    "readiness-probe", "bootstrap-witness", "adapter",
})
assert SEAM_PINS.isdisjoint(_WAVE_ONE_NAMES), \
    "Wave 1 short-names leaked into SEAM_PINS"

_VERSION_RE = re.compile(r"^v(0|[1-9]\d*)(\.(0|[1-9]\d*))?$")
_KIND_TAG_RE = re.compile(r"^canon\.[a-z0-9-]+/v(0|[1-9]\d*)(\.(0|[1-9]\d*))?$")


@dataclass(frozen=True, slots=True)
class SchemaPin:
    """One version-tagged seam. `name` is a short-name inside `SEAM_PINS`;
    `version` matches `_VERSION_RE` and refuses `v0.0`; `kind_tag` has the
    shape `canon.<slug>/v<n>` and its version suffix has to equal `version`;
    `adr_ref` names the decision that fixed this pin."""

    name: str
    version: str
    kind_tag: str
    adr_ref: str

    def __post_init__(self) -> None:
        self._validate_name()
        self._validate_version()
        self._validate_kind_tag()
        self._validate_adr_ref()

    def _validate_name(self) -> None:
        if not isinstance(self.name, str):
            raise ValueError(f"SchemaPin.name must be str, got {type(self.name)!r}")
        if self.name not in SEAM_PINS:
            raise ValueError(
                f"SchemaPin.name {self.name!r} is not in SEAM_PINS; add it "
                f"there first (closed vocabulary, D-92)")

    def _validate_version(self) -> None:
        if not isinstance(self.version, str):
            raise ValueError(
                f"SchemaPin.version must be str, got {type(self.version)!r}")
        if not _VERSION_RE.match(self.version):
            raise ValueError(
                f"SchemaPin.version {self.version!r} fails semver-lite "
                f"regex {_VERSION_RE.pattern!r}")
        if self.version == "v0.0":
            raise ValueError(
                "SchemaPin.version 'v0.0' is refused; use 'v0' as the "
                "canonical zero (D-91)")

    def _validate_kind_tag(self) -> None:
        if not isinstance(self.kind_tag, str):
            raise ValueError(
                f"SchemaPin.kind_tag must be str, got {type(self.kind_tag)!r}")
        if not _KIND_TAG_RE.match(self.kind_tag):
            raise ValueError(
                f"SchemaPin.kind_tag {self.kind_tag!r} fails the "
                f"canon.<slug>/v<n> grammar")
        suffix = self.kind_tag.rsplit("/", 1)[1]
        if suffix != self.version:
            raise ValueError(
                f"SchemaPin.kind_tag version suffix {suffix!r} does not "
                f"equal SchemaPin.version {self.version!r}")

    def _validate_adr_ref(self) -> None:
        if not isinstance(self.adr_ref, str):
            raise ValueError(
                f"SchemaPin.adr_ref must be str, got {type(self.adr_ref)!r}")
        if not self.adr_ref:
            raise ValueError("SchemaPin.adr_ref must be non-empty")
