"""Shared constants and primitive checks for standards registry profiles."""
from __future__ import annotations

from datetime import date
import re

from .scope import LEGACY_SCOPE_KEY, SCOPE_KEY

# v2 profiles and validation results name the coverage string `scope`. A v1
# profile carries the older key at the root and on each requirement, and stays
# valid; each version is checked against its own key only.
PROFILE_SCHEMA_V1 = "flywheel.standards-profile/v1"
PROFILE_SCHEMA = "flywheel.standards-profile/v2"
PROFILE_SCOPE_KEYS = {PROFILE_SCHEMA_V1: LEGACY_SCOPE_KEY, PROFILE_SCHEMA: SCOPE_KEY}
VALIDATION_SCHEMA_V1 = "flywheel.standards-profile-validation/v1"
VALIDATION_SCHEMA = "flywheel.standards-profile-validation/v2"

INSTRUMENT_KINDS = {
    "statute", "regulation", "binding_order", "contract",
    "procurement_clause", "incorporated_standard", "voluntary_standard",
    "guidance", "proposal", "internal_policy",
}
ISSUER_ROLES = {
    "legislature", "regulator", "standards_developer",
    "accreditation_body", "conformity_assessment_body", "customer",
    "internal_policy_owner",
}
BINDING_BASES = {
    "statute", "regulation", "binding_order", "contract_clause",
    "procurement_clause", "incorporation_by_reference",
    "voluntary_adoption", "guidance", "proposal", "internal_policy",
}
BINDING_REVIEWS = {
    "not_reviewed", "reviewed_for_named_scope", "accepted_pinned_basis",
}
SOURCE_STATUSES = {
    "discovered", "official_metadata_checked", "full_text_reviewed",
    "changed", "superseded",
}
REVIEW_STATUSES = {"not_reviewed", "metadata_checked", "reviewed"}
DISCLOSURE_TIERS = {
    "public_metadata", "public_full_text", "restricted_metadata",
    "restricted_full_text",
}
EVIDENCE_STATUSES = {
    "missing", "partial", "observed", "independently_reproduced",
    "stale", "disputed",
}

EXEC_KEYS = {
    "command", "cmd", "script", "eval", "exec", "import", "importlib",
    "__import__", "subprocess", "network", "url_fetch",
}
ROOT_FIELDS = {
    "schema", "profile_id", "title", "version", "owner", "instrument",
    "provenance", "effective", "applicability", "requirements",
}  # plus the scope key of the profile's version
INSTRUMENT_FIELDS = {
    "instrument_id", "title", "edition", "instrument_kind", "issuer_role",
    "binding_basis", "binding_review_status", "jurisdiction",
}
PROVENANCE_FIELDS = {
    "source_status", "source_ref", "source_url", "retrieved_at",
    "source_sha256", "raw_source_hash_null_reason", "language",
    "translation", "disclosure_tier", "review_status",
}
EFFECTIVE_FIELDS = {
    "published_on", "effective_from", "effective_to", "supersedes",
    "superseded_by",
}
APPLICABILITY_FIELDS = {"jurisdictions", "operator_roles", "covered_uses"}
REQUIREMENT_FIELDS = {
    "requirement_id", "requirement_ref", "summary", "text_hash",
    "selectors", "maps_to_controls", "maps_to_evidence_claims", "evidence",
    "review_required",
}  # plus the scope key of the profile's version
EVIDENCE_FIELDS = {"status", "artifact_sha256"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Collector:
    def __init__(self) -> None:
        self.errors: list[dict[str, str]] = []
        self.gaps: list[dict[str, str]] = []

    def error(self, path: str, code: str, message: str) -> None:
        self.errors.append({"path": path, "code": code, "message": message})

    def gap(self, path: str, code: str, message: str) -> None:
        self.gaps.append({"path": path, "code": code})


def parse_date(value: object, path: str, c: Collector) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        c.error(path, "type", "expected YYYY-MM-DD string")
        return None
    if not _DATE_RE.match(value):
        c.error(path, "date", "expected YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        c.error(path, "date", "expected valid YYYY-MM-DD")
        return None


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.match(value))
