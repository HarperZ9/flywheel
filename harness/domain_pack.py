"""Domain pack manifest verification: a pack is admitted as a manifest
plus admitted data, never as executable authority. The verifier refuses
false accepts, dynamic imports, plugin discovery, commands, missing
license or owner or limits, and secret-shaped or host-path fields.
Executable packs stay execution_locked without accepted containment."""
from __future__ import annotations

from pathlib import Path

from .evidence_json import canonical_sha256

SCHEMA = "flywheel.domain-pack/v1"
QA_SCHEMA = "flywheel.domain-pack-qa/v1"
_REQUIRED = ("pack_id", "version", "domain_id", "claim_types",
             "journey_schema", "packet_schema", "oracle_bindings",
             "fixtures", "capabilities", "containment_class", "license",
             "resource_limits", "public_metadata_policy", "limitations",
             "does_not_prove", "owner", "review_due_at")
_SECRET_KEY = ("api_key", "token", "secret", "password", "credential",
               "authorization", "cookie", "private_key")
_CAPS = {"data", "executable", "network", "write", "secrets"}


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def _looks_like_host_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return (":\\" in value or value.startswith(("/", "\\\\")) or
            "c:" in lowered or len(value) > 255)


def _clean(value: object, depth: int = 0) -> None:
    if depth > 8:
        _refuse("pack metadata nests too deeply")
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(s in lowered for s in _SECRET_KEY):
                _refuse("pack metadata must not carry secrets")
            if lowered in ("path", "log_path", "host_path", "command"):
                _refuse("pack metadata must not carry paths or commands")
            if lowered == "file" and _looks_like_host_path(child):
                _refuse("a fixture name must stay pack-relative")
            _clean(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _clean(child, depth + 1)


def _fixture_verdict(fixture: dict) -> str:
    return str(fixture.get("expectation", ""))


def verify_pack_manifest(manifest: dict, *, fixtures_root: Path | str) -> dict:
    if manifest.get("schema") != SCHEMA:
        _refuse("the manifest is not a domain-pack/v1 document")
    missing = [f for f in _REQUIRED if f not in manifest]
    if missing:
        _refuse(f"the manifest is missing {sorted(missing)}")
    _clean(manifest)
    caps = manifest.get("capabilities")
    if (not isinstance(caps, list) or not caps
            or any(c not in _CAPS for c in caps)):
        _refuse("pack capabilities are missing or unknown")
    if any(c in caps for c in ("network", "write", "secrets")):
        _refuse("network, write, and secrets capabilities are never admitted")
    if "executable" in caps and manifest.get("containment_class") != \
            "process_contained":
        _refuse("executable packs require accepted process containment")
    license_text = str(manifest.get("license", ""))
    if "SPDX" not in license_text and not license_text.startswith("License-"):
        _refuse("the pack license must be an SPDX identifier or License- ref")
    limits = manifest.get("resource_limits")
    if not isinstance(limits, dict):
        _refuse("pack resource limits are missing")
    numeric = ("cpu_seconds", "memory_mb", "processes", "output_bytes",
               "time_seconds")
    if any(not isinstance(limits.get(k), int) or limits.get(k) < 0
           for k in numeric):
        _refuse("pack resource limits must be non-negative integers")
    if not isinstance(manifest.get("owner"), str) or not manifest["owner"]:
        _refuse("the pack names no owner")
    oracle_bindings = manifest.get("oracle_bindings")
    if not isinstance(oracle_bindings, list) or not oracle_bindings:
        _refuse("the pack binds no oracle")
    for binding in oracle_bindings:
        for field in ("oracle_id", "oracle_version", "source_sha256",
                      "evidence_kind", "deterministic"):
            if field not in binding:
                _refuse(f"the oracle binding lacks {field}")
        if binding.get("deterministic") is not True:
            _refuse("only deterministic oracles are admissible")
    for banned in ("importlib", "__import__", "plugin_discovery",
                   "subprocess"):
        if banned in str(manifest):
            _refuse(f"the manifest must not declare {banned}")
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        _refuse("the pack carries no fixtures")
    root = Path(fixtures_root)
    for fixture in fixtures:
        name = fixture.get("file", "")
        path = root / str(name)
        if not path.is_file():
            _refuse(f"fixture {name!r} is not in the fixtures root")
        if _fixture_verdict(fixture) not in ("correct", "incorrect",
                                             "ambiguous", "malformed",
                                             "stale", "contested",
                                             "unsupported"):
            _refuse("a fixture expectation is outside the typed verdicts")
    admitted = dict(manifest)
    admitted["pack_sha256"] = canonical_sha256(
        {k: v for k, v in manifest.items() if k != "pack_sha256"})
    admitted["state"] = ("available" if "executable" in caps
                         else "data_only")
    return admitted


def run_pack_qa(manifest: dict, fixtures: list[dict]) -> dict:
    """Score the pack's own QA fixtures: every planted false accept must
    be detected; the denominator, escapes, skips, and does_not_prove are
    part of the result."""
    if manifest.get("schema") != SCHEMA:
        _refuse("QA runs against a domain-pack/v1 manifest")
    expected = {f["file"]: f["expectation"] for f in
                manifest.get("fixtures", [])}
    detected = 0
    escaped = 0
    skipped = 0
    for fixture in fixtures:
        name = str(fixture.get("file", ""))
        expectation = expected.get(name)
        if expectation is None:
            _refuse(f"QA fixture {name!r} is not in the manifest")
        observed = fixture.get("observed")
        if observed == "skipped":
            skipped += 1
            continue
        if expectation == "incorrect" and observed == "accepted":
            escaped += 1
            continue
        if expectation == "incorrect" and observed == "refused":
            detected += 1
    total = len(fixtures)
    return {
        "schema": QA_SCHEMA,
        "pack_sha256": manifest.get("pack_sha256", ""),
        "denominator": total,
        "detected": detected,
        "escaped": escaped,
        "platform_skips": skipped,
        "resource_usage": {"within_limits": escaped == 0},
        "does_not_prove": (
            "a passing QA run says the pack refuses its own planted "
            "false accepts; it does not certify the pack's claims"),
    }
