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

from .incentive_manifest import DOES_NOT_PROVE as _EIM_BOUND
from .incentive_manifest import validate as _validate_manifest
from .transitive_witness import DRIFT, MATCH, UNVERIFIABLE

RUBRIC_VERSION = "ced/v1"
NCEC_SCHEMA = "flywheel.non-coercive-environment-certificate/v1"
COERCIVE = "COERCIVE"
NON_COERCIVE = "NON_COERCIVE"

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
CED_DOES_NOT_PROVE = (
    "The detector flags a design condition, not an outcome. Present scarcity does "
    "not prove misbehavior in any deployment, its terms describe the environment "
    "and not an agent's experience, and a non-coercive result is necessary and "
    "not sufficient for aligned behavior.")
NCEC_DOES_NOT_PROVE = (
    "The certificate covers environment design properties only. It attests that "
    "the CED scan found no coercive primitives and that the named non-coercive "
    "properties were declared; it does not prove the platform produces aligned "
    "agents, and it is re-derivable rather than a guarantee.")


class CertificateError(ValueError):
    """A refused or malformed Non-Coercive-Environment Certificate."""


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
            "does_not_prove": CED_DOES_NOT_PROVE}


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
    if any(not isinstance(p, str) or not p for p in props):
        raise CertificateError("non_coercive_properties: non-empty strings only")
    return {"schema": NCEC_SCHEMA, "environment_id": manifest["environment_id"],
            "granted": True, "rubric_version": RUBRIC_VERSION,
            "ced_verdict": NON_COERCIVE, "non_coercive_properties": props,
            "does_not_prove": NCEC_DOES_NOT_PROVE}


def verify_certificate(certificate, manifest) -> dict:
    """Re-derive an NCEC by re-running CED over the manifest.

    MATCH when the certificate is well-formed for this manifest and the scan is
    still non-coercive; DRIFT when the environment now scans as coercive or the
    certificate disagrees with the manifest; UNVERIFIABLE when the certificate is
    malformed and cannot be checked at all.
    """
    if (not isinstance(certificate, dict) or
            certificate.get("schema") != NCEC_SCHEMA or
            not isinstance(certificate.get("environment_id"), str)):
        return {"verdict": UNVERIFIABLE, "reason": "malformed certificate",
                "does_not_prove": NCEC_DOES_NOT_PROVE}
    if certificate["environment_id"] != manifest.get("environment_id"):
        return {"verdict": DRIFT, "reason": "environment_id mismatch",
                "does_not_prove": NCEC_DOES_NOT_PROVE}
    scan = detect(manifest)
    if scan["verdict"] != NON_COERCIVE or certificate.get("ced_verdict") != NON_COERCIVE:
        return {"verdict": DRIFT, "reason": "environment scans as coercive",
                "hits": scan["hits"], "does_not_prove": NCEC_DOES_NOT_PROVE}
    return {"verdict": MATCH, "rubric_version": RUBRIC_VERSION,
            "environment_id": manifest["environment_id"],
            "does_not_prove": NCEC_DOES_NOT_PROVE}


# The EIM bound travels with these instruments too: they read a declaration, so
# they inherit its limit that a declared incentive structure is not a behavior.
MANIFEST_BOUND = _EIM_BOUND
