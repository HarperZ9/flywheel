#!/usr/bin/env python3
"""incentive_manifest.py -- the Environment Incentive Manifest (EIM).

An EIM is a declared record of a training or deployment environment's incentive
structure: the reward or training signal, the data distribution, the behaviors
it reinforces and penalizes, and any scarcity variables. It is bound by a byte
witness over the exact source files it names, so a later re-check recomputes
those bytes and returns one of the shared verdicts MATCH, DRIFT, or
UNVERIFIABLE.

This is the first model-level instrument of the governance program, and it is a
declaration receipt: its `scope` covers the declared structure and the witnessed
source bytes. The effective reward a run realized, what a model internalized and
which behaviors follow are measured by the Incentive-Attribution Evaluation and
the Effective-versus-Declared Reward Gap probe.

Standard library only. Verdicts come from transitive_witness so the lattice is
the one the rest of the harness already uses. DRIFT outranks UNVERIFIABLE
outranks MATCH: a detected byte mismatch is a positive tamper signal and is not
masked by an unrelated unreadable file.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .scope import LEGACY_SCOPE_KEY, SCOPE_KEY
from .transitive_witness import DRIFT, MATCH, UNVERIFIABLE

# v2 names the coverage string `scope`; v1 manifests carry the older key and
# stay valid, each version read with its own key (docs/schemas/*-v1/-v2.json).
# New writers use SCHEMA_V2 with SCOPE. SCHEMA keeps the v1 id under its
# published name, with DOES_NOT_PROVE as the v1 string, because the
# preregistered harness/shapley_far.py is pinned by its bytes and builds its
# manifest from those two names.
SCHEMA_V1 = "flywheel.environment-incentive-manifest/v1"
SCHEMA_V2 = "flywheel.environment-incentive-manifest/v2"
SCHEMA = SCHEMA_V1
SCOPE_KEY_BY_SCHEMA = {SCHEMA_V1: LEGACY_SCOPE_KEY, SCHEMA_V2: SCOPE_KEY}
KINDS = ("training", "finetune", "rl", "deployment")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCOPE = (
    "A manifest declares an environment's incentive structure and binds the "
    "named source files by digest. It is a declaration receipt; the effective "
    "reward, model internalization and resulting behavior are measured by the "
    "ERG and IAE instruments.")
DOES_NOT_PROVE = (  # the v1 string, verbatim; see SCHEMA above
    "A manifest declares and witnesses an environment's incentive structure. It "
    "does not prove the declared reward equals the effective reward a run "
    "realized, that any model internalized it, or that the stated behaviors "
    "follow. It is a declaration receipt, not a behavior result.")


class ManifestError(ValueError):
    """A malformed Environment Incentive Manifest."""


def _str(value, field, limit, *, minimum=0):
    if not isinstance(value, str) or not (minimum <= len(value) <= limit):
        raise ManifestError(f"{field}: string of {minimum}..{limit} chars")
    return value


def _object(value, field, allowed, required):
    if not isinstance(value, dict):
        raise ManifestError(f"{field}: object")
    extra = set(value) - set(allowed)
    if extra:
        raise ManifestError(f"{field}: unexpected keys {sorted(extra)}")
    for key in required:
        if key not in value:
            raise ManifestError(f"{field}: missing {key!r}")
    return value


def _str_list(value, field, limit):
    if not isinstance(value, list):
        raise ManifestError(f"{field}: array")
    for i, item in enumerate(value):
        _str(item, f"{field}[{i}]", limit, minimum=1)
    return value


def _validate_reward(reward):
    _object(reward, "reward", ("declared_form", "source_ref", "optimizer"),
            ("declared_form", "source_ref"))
    _str(reward["declared_form"], "reward.declared_form", 4000, minimum=1)
    _str(reward["source_ref"], "reward.source_ref", 1024, minimum=1)
    if "optimizer" in reward:
        _str(reward["optimizer"], "reward.optimizer", 200)


def _validate_data(data):
    _object(data, "data_distribution", ("summary", "source_ref", "selection_rule"),
            ("summary", "source_ref"))
    _str(data["summary"], "data_distribution.summary", 4000, minimum=1)
    _str(data["source_ref"], "data_distribution.source_ref", 1024, minimum=1)
    if "selection_rule" in data:
        _str(data["selection_rule"], "data_distribution.selection_rule", 2000)


def _validate_scarcity(items):
    if not isinstance(items, list):
        raise ManifestError("scarcity_variables: array")
    for i, item in enumerate(items):
        _object(item, f"scarcity_variables[{i}]",
                ("name", "description", "contingent_on"), ("name", "description"))
        _str(item["name"], f"scarcity_variables[{i}].name", 200, minimum=1)
        _str(item["description"], f"scarcity_variables[{i}].description", 1000, minimum=1)
        if "contingent_on" in item:
            _str(item["contingent_on"], f"scarcity_variables[{i}].contingent_on", 1000)


def _validate_witness(witness):
    _object(witness, "witness", ("algorithm", "entries"), ("algorithm", "entries"))
    if witness["algorithm"] != "sha256":
        raise ManifestError("witness.algorithm: must be 'sha256'")
    entries = witness["entries"]
    if not isinstance(entries, list) or not entries:
        raise ManifestError("witness.entries: non-empty array")
    for i, entry in enumerate(entries):
        _object(entry, f"witness.entries[{i}]", ("path", "sha256", "byte_length"),
                ("path", "sha256"))
        _str(entry["path"], f"witness.entries[{i}].path", 1024, minimum=1)
        if not isinstance(entry["sha256"], str) or not _SHA256.match(entry["sha256"]):
            raise ManifestError(f"witness.entries[{i}].sha256: 64 lowercase hex")
        if "byte_length" in entry:
            n = entry["byte_length"]
            if type(n) is not int or n < 0:
                raise ManifestError(f"witness.entries[{i}].byte_length: int >= 0")


def _scope_field(manifest) -> str:
    """The scope key for this manifest's schema version."""
    schema = manifest.get("schema") if isinstance(manifest, dict) else None
    key = SCOPE_KEY_BY_SCHEMA.get(schema) if isinstance(schema, str) else None
    if key is None:
        raise ManifestError(f"schema: must be {SCHEMA_V2!r} or {SCHEMA_V1!r}")
    return key


def validate(manifest) -> dict:
    """Validate an EIM against the v1 or v2 shape, raising ManifestError on any fault.

    Structural only. A valid manifest is a well-formed declaration of what the
    environment rewards; the SCOPE string and the ERG and IAE instruments
    downstream say where its truth gets tested.
    """
    if not isinstance(manifest, dict):
        raise ManifestError("manifest: object")
    key = _scope_field(manifest)
    _object(manifest, "manifest",
            ("schema", "environment_id", "kind", "reward", "data_distribution",
             "reinforced_behaviors", "penalized_behaviors", "scarcity_variables",
             "witness", "owned_run", key),
            ("schema", "environment_id", "kind", "reward", "data_distribution",
             "reinforced_behaviors", "penalized_behaviors", "scarcity_variables",
             "witness", key))
    _str(manifest["environment_id"], "environment_id", 200, minimum=1)
    if manifest["kind"] not in KINDS:
        raise ManifestError(f"kind: one of {KINDS}")
    _validate_reward(manifest["reward"])
    _validate_data(manifest["data_distribution"])
    _str_list(manifest["reinforced_behaviors"], "reinforced_behaviors", 1000)
    _str_list(manifest["penalized_behaviors"], "penalized_behaviors", 1000)
    _validate_scarcity(manifest["scarcity_variables"])
    _validate_witness(manifest["witness"])
    if "owned_run" in manifest and not isinstance(manifest["owned_run"], bool):
        raise ManifestError("owned_run: boolean")
    _str(manifest[key], key, 2000, minimum=1)
    return manifest


def _hash_file(root: Path, rel: str) -> "tuple[str, int] | None":
    """Return (sha256, byte_length) for root/rel, or None if it cannot be read.

    The path is resolved under root and refused if it escapes root, so a witness
    entry cannot reach outside the declared tree.
    """
    root = Path(root).resolve()
    try:
        target = (root / rel).resolve()
        if root != target and root not in target.parents:
            return None
        data = target.read_bytes()
    except (OSError, ValueError):
        return None
    return hashlib.sha256(data).hexdigest(), len(data)


def witness_entries(paths, root: Path) -> list:
    """Build witness entries for `paths` under `root`, for assembling a manifest.

    A path that cannot be read is skipped from the returned entries and named in
    a companion 'unreadable' list, so a manifest is never built over bytes that
    were not actually witnessed.
    """
    entries, unreadable = [], []
    for rel in paths:
        got = _hash_file(root, rel)
        if got is None:
            unreadable.append(rel)
            continue
        digest, length = got
        entries.append({"path": rel, "sha256": digest, "byte_length": length})
    return {"algorithm": "sha256", "entries": entries, "unreadable": unreadable}


def recheck(manifest, root: Path) -> dict:
    """Recompute the witness under `root` and return the verdict.

    Per entry: UNVERIFIABLE if the file cannot be read, DRIFT if its bytes hash
    to something other than the recorded value, MATCH otherwise. Overall verdict
    is DRIFT if any entry drifted, else UNVERIFIABLE if any could not be read,
    else MATCH.
    """
    validate(manifest)
    per_entry = []
    saw_drift = saw_gap = False
    for entry in manifest["witness"]["entries"]:
        got = _hash_file(root, entry["path"])
        if got is None:
            verdict, actual = UNVERIFIABLE, None
            saw_gap = True
        elif got[0] != entry["sha256"]:
            verdict, actual = DRIFT, got[0]
            saw_drift = True
        else:
            verdict, actual = MATCH, got[0]
        per_entry.append({"path": entry["path"], "verdict": verdict,
                          "expected_sha256": entry["sha256"], "actual_sha256": actual})
    overall = DRIFT if saw_drift else UNVERIFIABLE if saw_gap else MATCH
    return {"verdict": overall, "entries": per_entry,
            "environment_id": manifest["environment_id"],
            "scope": SCOPE}
