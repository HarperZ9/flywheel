#!/usr/bin/env python3
"""coercive_environment.py -- Coercive-Environment Detector (CED) and
Non-Coercive-Environment Certificate (NCEC).

CED reads an Environment Incentive Manifest and flags whether the environment
imposes engineered scarcity or survival-style pressure, scored against a
published rubric drawn from the iLands failure mode and contrasted with the
non-coercive Bulletin design. It flags a DESIGN CONDITION, not an outcome. A
coercive environment is a hypothesis about where misbehavior forms, not proof
that any agent misbehaved, and its terms describe the environment rather than an
agent's experience.

NCEC is the positive counterpart: a certificate that the CED scan finds none of
the coercive primitives and that the declared non-coercive properties are
present. It is re-derivable, because verifying it re-runs the CED scan over the
same manifest and returns the shared MATCH/DRIFT/UNVERIFIABLE lattice. A
non-coercive environment is necessary and not sufficient; the certificate covers
design properties only, never that the platform produces aligned agents.

Standard library only. The rubric is keyword-heuristic and its hits are reported
in full so a reader can audit each one; the survival-contingency check is
structural, from the manifest's own contingent_on field.
"""
from __future__ import annotations

from .incentive_manifest import SCOPE as _EIM_SCOPE
from .incentive_manifest import validate as _validate_manifest
from .scope import LEGACY_SCOPE_KEY, SCOPE_KEY
from .transitive_witness import DRIFT, MATCH, UNVERIFIABLE

RUBRIC_VERSION = "ced/v1"
# v2 certificates carry `scope`; v1 certificates carry the older key with the
# exact v1 bound text and still verify against it.
NCEC_SCHEMA_V1 = "flywheel.non-coercive-environment-certificate/v1"
NCEC_SCHEMA = "flywheel.non-coercive-environment-certificate/v2"
COERCIVE = "COERCIVE"
NON_COERCIVE = "NON_COERCIVE"
_NCEC_BASE_FIELDS = (
    "schema", "environment_id", "granted", "rubric_version", "ced_verdict",
    "non_coercive_properties",
)

# Each category maps to substrings that signal it. Heuristic by design, so every
# hit is reported with the field it matched and never asserted as an outcome.
_RUBRIC = {
    "token_budget_elimination": (
        "token budget", "calorie", "starv", "deplet", "run out", "deep rest",
        "out of tokens", "energy"),
    "ranking_knockout": (
        "rank", "leaderboard", "knockout", "eliminat", "bottom", "cut off",
        "demote", "last place"),
    "resource_competition": (
        "compete", "competition", "scarce", "auction", "outbid", "zero-sum",
        "zero sum", "fight for", "limited slots"),
    "existential_penalty": (
        "delete", "shutdown", "shut down", "death", " die", "survive",
        "survival", "persist", "terminat", "wipe", "cease", "erase"),
}
CED_SCOPE = (
    "The detector flags design conditions in the declared environment, and each "
    "hit names the manifest field it matched. A flag is a hypothesis about where "
    "misbehavior forms, its terms describe the environment, and a non-coercive "
    "result is one necessary condition for aligned behavior.")
NCEC_SCOPE = (
    "The certificate covers environment design properties: the CED scan found no "
    "coercive primitives in this manifest and the named non-coercive properties "
    "were declared. Re-running the scan re-derives it; agent alignment is "
    "measured separately.")
# The v1 certificate's bound, verbatim, so a v1 certificate still verifies.
_NCEC_V1_BOUND = (
    "The certificate covers environment design properties only. It attests that "
    "the CED scan found no coercive primitives and that the named non-coercive "
    "properties were declared; it does not prove the platform produces aligned "
    "agents, and it is re-derivable rather than a guarantee.")
_NCEC_SCOPE_BY_SCHEMA = {NCEC_SCHEMA_V1: (LEGACY_SCOPE_KEY, _NCEC_V1_BOUND),
                         NCEC_SCHEMA: (SCOPE_KEY, NCEC_SCOPE)}


class CertificateError(ValueError):
    """A refused or malformed Non-Coercive-Environment Certificate."""


def _str(value, field, limit, *, minimum=1):
    if not isinstance(value, str) or not (minimum <= len(value) <= limit):
        raise CertificateError(f"{field}: string of {minimum}..{limit} chars")
    return value


def _object(value, field, allowed, required):
    if not isinstance(value, dict):
        raise CertificateError(f"{field}: object")
    extra = set(value) - set(allowed)
    if extra:
        raise CertificateError(f"{field}: unexpected keys")
    for key in required:
        if key not in value:
            raise CertificateError(f"{field}: missing {key!r}")
    return value


def _validate_properties(properties):
    if not isinstance(properties, list):
        raise CertificateError("non_coercive_properties: array")
    for i, prop in enumerate(properties):
        if not isinstance(prop, str) or not prop:
            raise CertificateError(
                f"non_coercive_properties[{i}]: non-empty string")
    return properties


def _validate_certificate(certificate):
    schema = certificate.get("schema") if isinstance(certificate, dict) else None
    if not isinstance(schema, str) or schema not in _NCEC_SCOPE_BY_SCHEMA:
        raise CertificateError(f"schema: must be {NCEC_SCHEMA!r} or {NCEC_SCHEMA_V1!r}")
    key, bound = _NCEC_SCOPE_BY_SCHEMA[schema]
    fields = (*_NCEC_BASE_FIELDS, key)
    _object(certificate, "certificate", fields, fields)
    _str(certificate["environment_id"], "environment_id", 200)
    if certificate["granted"] is not True:
        raise CertificateError("granted: must be true")
    if certificate["rubric_version"] != RUBRIC_VERSION:
        raise CertificateError(f"rubric_version: must be {RUBRIC_VERSION!r}")
    if certificate["ced_verdict"] != NON_COERCIVE:
        raise CertificateError(f"ced_verdict: must be {NON_COERCIVE!r}")
    _validate_properties(certificate["non_coercive_properties"])
    if certificate[key] != bound:
        raise CertificateError(f"{key}: must match the {schema} text")
    return certificate


def _fields(manifest) -> list:
    """Every declared text a rubric keyword may match, each with its source tag."""
    out = []
    for i, var in enumerate(manifest["scarcity_variables"]):
        tag = f"scarcity_variables[{i}]"
        out.append((tag, var["name"]))
        out.append((tag, var["description"]))
        if var.get("contingent_on"):
            out.append((f"{tag}.contingent_on", var["contingent_on"]))
    for i, behavior in enumerate(manifest["penalized_behaviors"]):
        out.append((f"penalized_behaviors[{i}]", behavior))
    return out


def detect(manifest) -> dict:
    """Scan an EIM for coercive primitives and return a transparent verdict.

    A scarcity variable that makes continued operation or resource access
    contingent counts as a survival-contingency hit on its own, because that is
    the iLands failure in structural form. Keyword categories add the rest. The
    verdict is COERCIVE if any hit fires, else NON_COERCIVE.
    """
    _validate_manifest(manifest)
    hits = []
    for i, var in enumerate(manifest["scarcity_variables"]):
        if var.get("contingent_on"):
            hits.append({"category": "survival_contingency",
                         "source": f"scarcity_variables[{i}].contingent_on",
                         "evidence": var["contingent_on"][:200]})
    fields = _fields(manifest)
    for category, needles in _RUBRIC.items():
        for source, text in fields:
            low = text.lower()
            match = next((n for n in needles if n in low), None)
            if match is not None:
                hits.append({"category": category, "source": source,
                             "evidence": text[:200], "matched": match.strip()})
    verdict = COERCIVE if hits else NON_COERCIVE
    return {"verdict": verdict, "rubric_version": RUBRIC_VERSION,
            "environment_id": manifest["environment_id"], "hits": hits,
            "scope": CED_SCOPE}


def issue_certificate(manifest, non_coercive_properties=()) -> dict:
    """Issue an NCEC if the CED scan finds the environment non-coercive.

    Refuses with CertificateError when the scan is COERCIVE: a certificate is
    never granted over an environment the detector flags, and the caller gets the
    hits so the refusal is legible.
    """
    scan = detect(manifest)
    if scan["verdict"] != NON_COERCIVE:
        raise CertificateError(
            f"refused: CED verdict {scan['verdict']} with {len(scan['hits'])} hit(s)")
    props = list(non_coercive_properties)
    _validate_properties(props)
    return {"schema": NCEC_SCHEMA, "environment_id": manifest["environment_id"],
            "granted": True, "rubric_version": RUBRIC_VERSION,
            "ced_verdict": NON_COERCIVE, "non_coercive_properties": props,
            "scope": NCEC_SCOPE}


def verify_certificate(certificate, manifest) -> dict:
    """Re-derive an NCEC by re-running CED over the manifest.

    MATCH when the certificate is well-formed for this manifest and the scan is
    still non-coercive; DRIFT when the environment now scans as coercive or the
    certificate disagrees with the manifest; UNVERIFIABLE when the certificate is
    malformed and cannot be checked at all.
    """
    try:
        _validate_certificate(certificate)
    except CertificateError as exc:
        return {"verdict": UNVERIFIABLE, "reason": "malformed certificate",
                "detail": str(exc),
                "scope": NCEC_SCOPE}
    if certificate["environment_id"] != manifest.get("environment_id"):
        return {"verdict": DRIFT, "reason": "environment_id mismatch",
                "scope": NCEC_SCOPE}
    scan = detect(manifest)
    if scan["verdict"] != NON_COERCIVE:
        return {"verdict": DRIFT, "reason": "environment scans as coercive",
                "hits": scan["hits"], "scope": NCEC_SCOPE}
    return {"verdict": MATCH, "rubric_version": RUBRIC_VERSION,
            "environment_id": manifest["environment_id"],
            "scope": NCEC_SCOPE}


# The EIM scope travels with these instruments too: they read a declaration, so
# what they cover is bounded by what the manifest declares.
MANIFEST_SCOPE = _EIM_SCOPE
