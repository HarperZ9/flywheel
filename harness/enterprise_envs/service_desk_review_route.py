"""Gateway route for reviewing ServiceDesk incident evidence bundles."""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from harness.bundle import scan_for_secrets
from harness.enterprise_envs import compat
from harness.enterprise_envs.artifact_snapshot import (
    ArtifactSnapshotError,
    snapshotted_artifact_dir,
)
from harness.enterprise_envs.compat import EnterpriseEnvironmentProductMissing
from harness.evidence_public import (
    TransportError,
    admitted_root,
    error_response,
    exact_request,
    parse_json,
    within_root,
)

ROUTE_SCHEMA = "flywheel.enterprise-env-review/v1"
REPORT_SCHEMA = "service-desk-incident-env-review/v1"
VERIFICATION_SCHEMA = "service-desk-incident-env-artifact-verification/v1"
ENVIRONMENT_ID = "service-desk-incident/v1"
PATH = "/api/enterprise-envs/service-desk-incident/review"
RELEASE_URL = (
    "https://github.com/HarperZ9/flywheel/releases/tag/"
    "env-service-desk-incident-v0.2.0")
UPGRADE_MESSAGE = (
    "install flywheel-env-service-desk-incident 0.2.0 or later from "
    f"{RELEASE_URL}")

_LAYERS = (
    "source_integrity",
    "synthetic_task_check",
    "record_consistency",
    "externally_trusted_evidence",
)
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"(?:\\\\|//)[^\\/\s]+[\\/][^\s]+")
_POSIX_PATH = re.compile(r"(?:^|[\s=(\[{,:;])/(?!/)[^\s]+|/"
    r"(?:Users|home|private|tmp|var|etc|root|opt|mnt|srv|usr|bin|sbin|lib|"
    r"Applications|Volumes|dev|proc|sys|run)(?:/|$)")
_FILE_URI = re.compile(r"(?i)(?<![A-Za-z0-9+.-])file:")
_MAX_REPORT_STRING_BYTES = 16 * 1024
_MAX_REPORT_DECODE_ROUNDS = 4


def service_desk_review_post(
        path: str, raw: bytes | str, *, run_root: Path | str) -> tuple[dict, int]:
    try:
        if path != PATH:
            raise TransportError("NOT_FOUND", "unknown enterprise environment route", 404)
        req = exact_request(parse_json(raw), {"artifact_dir_ref"})
        artifact_ref = req["artifact_dir_ref"]
        root = admitted_root(Path(run_root))
        artifact_dir = within_root(root, artifact_ref, must_exist=True).resolve(
            strict=True)
        if not artifact_dir.is_dir():
            raise TransportError(
                "INVALID_REF", "artifact reference must name a directory", 422)
        product = _load_product()
        try:
            with snapshotted_artifact_dir(artifact_dir) as review_dir:
                report = product.review_artifacts(review_dir)
        except ArtifactSnapshotError as exc:
            raise TransportError(
                "UNSAFE_ARTIFACT_TREE",
                "artifact tree cannot be safely snapshotted",
                422,
            ) from exc
        sanitized = _sanitize_report(report, artifact_ref, artifact_dir.name)
        body = {
            "schema": ROUTE_SCHEMA,
            "environment_id": ENVIRONMENT_ID,
            "artifact_dir_ref": artifact_ref,
            "artifact_label": sanitized["artifact_label"],
            "report": sanitized,
        }
        _assert_safe_report_strings(body)
        return body, 200
    except TransportError as exc:
        return error_response(exc)


def _load_product():
    try:
        product = compat.load_service_desk_product()
    except EnterpriseEnvironmentProductMissing as exc:
        raise TransportError(
            "PRODUCT_UNAVAILABLE",
            f"{exc.environment_id} requires {exc.distribution}; {UPGRADE_MESSAGE}",
            503,
        ) from exc
    review_artifacts = getattr(product, "review_artifacts", None)
    if not callable(review_artifacts):
        raise TransportError(
            "PRODUCT_UPGRADE_REQUIRED",
            f"installed ServiceDesk product does not expose review_artifacts; {UPGRADE_MESSAGE}",
            503,
        )
    return product


def _sanitize_report(report: Any, artifact_ref: Any, artifact_label: str) -> dict:
    try:
        clean = json.loads(json.dumps(report))
    except (TypeError, ValueError, RecursionError) as exc:
        raise TransportError(
            "PRODUCT_UPGRADE_REQUIRED",
            f"installed ServiceDesk product returned a non-portable review report; {UPGRADE_MESSAGE}",
            503,
        ) from exc
    if type(clean) is not dict:
        raise TransportError(
            "PRODUCT_UPGRADE_REQUIRED",
            f"installed ServiceDesk product returned an incomplete review report; {UPGRADE_MESSAGE}",
            503,
        )
    clean.pop("artifact_dir", None)
    clean["artifact_dir_ref"] = artifact_ref
    clean["artifact_label"] = _string(clean.get("artifact_label")) or artifact_label
    verification = clean.get("verification")
    if type(verification) is dict:
        verification = dict(verification)
        verification.pop("artifact_dir", None)
        verification["artifact_dir_ref"] = artifact_ref
        clean["verification"] = verification
    _assert_complete_report(clean)
    return clean


def _assert_complete_report(report: dict) -> None:
    verification = report.get("verification")
    evidence_layers = report.get("evidence_layers")
    if (
        report.get("schema") != REPORT_SCHEMA
        or type(verification) is not dict
        or verification.get("schema") != VERIFICATION_SCHEMA
        or _string(verification.get("observed_state")) not in {"pass", "fail"}
        or not _string_list(verification.get("failure_codes"))
        or type(report.get("claimed_outcome")) is not dict
        or type(report.get("recomputed_outcome")) is not dict
        or type(evidence_layers) is not dict
        or not all(type(evidence_layers.get(layer)) is dict for layer in _LAYERS)
        or not _string_list(report.get("limits"), allow_empty=False)
    ):
        raise TransportError(
            "PRODUCT_UPGRADE_REQUIRED",
            f"installed ServiceDesk product does not expose the complete review report schema; {UPGRADE_MESSAGE}",
            503,
        )


def _assert_safe_report_strings(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                _assert_safe_report_text(key)
            _assert_safe_report_strings(item)
    elif isinstance(value, list):
        for item in value:
            _assert_safe_report_strings(item)
    elif isinstance(value, str):
        _assert_safe_report_text(value)


def _assert_safe_report_text(value: str) -> None:
    for variant in _decoded_variants(value):
        if (
            len(variant.encode("utf-8")) > _MAX_REPORT_STRING_BYTES
            or scan_for_secrets(variant)
            or _FILE_URI.search(variant)
            or _WINDOWS_PATH.search(variant)
            or _UNC_PATH.search(variant)
            or _POSIX_PATH.search(variant)
        ):
            _raise_unsafe_report()


def _decoded_variants(value: str) -> tuple[str, ...]:
    variants: list[str] = []
    seen: set[str] = set()
    current = value
    for _ in range(_MAX_REPORT_DECODE_ROUNDS):
        _append_decoded_candidates(variants, seen, current)
        decoded = unquote(unescape(current))
        if decoded == current:
            break
        current = decoded
    else:
        _append_decoded_candidates(variants, seen, current)
        if unquote(unescape(current)) != current:
            _raise_unsafe_report()
        return tuple(variants)
    _append_decoded_candidates(variants, seen, current)
    return tuple(variants)


def _append_decoded_candidates(
        variants: list[str], seen: set[str], current: str) -> None:
    for candidate in (current, unescape(current)):
        if candidate not in seen:
            variants.append(candidate)
            seen.add(candidate)


def _raise_unsafe_report() -> None:
    raise TransportError(
        "UNSAFE_REPORT",
        "ServiceDesk review report contains unsafe local content",
        422,
    )


def _string(value: Any) -> str:
    return value if type(value) is str else ""


def _string_list(value: Any, *, allow_empty: bool = True) -> bool:
    return (
        type(value) is list
        and (allow_empty or bool(value))
        and all(type(item) is str for item in value)
    )
