from __future__ import annotations

from .canonical_json import canonical_json_bytes, canonical_json_text, canonical_sha256, sha256_bytes, sha256_text
from .cli_artifacts import SourceBytes
from .rescue_output import RESCUE_ARTIFACT_NAMES

TRANSCRIPT_TRUST = "imported-untrusted"
RESCUE_SCHEMA = "canon.rescue-evidence/v1"
RESCUE_DOES_NOT_PROVE = (
    "This rescue result is offline/degraded handoff metadata; it does not prove host readiness or provider enforcement.",
)


def build_artifact_bytes(bundle: object, request: object, transcript: dict[str, object] | None, offline: bool) -> dict[str, bytes]:
    canon_md = bundle.canon_md.encode("utf-8")  # type: ignore[attr-defined]
    manifest = bundle.manifest_bytes  # type: ignore[attr-defined]
    readiness = canonical_json_text(bundle.readiness_probe.to_dict()).encode("utf-8")  # type: ignore[attr-defined]
    evidence = _evidence(bundle, request, transcript, offline, canon_md, manifest, readiness)
    return {
        "CANON.md": canon_md,
        "canon.capsule.json": manifest,
        "readiness-probe.json": readiness,
        "rescue.evidence.json": canonical_json_bytes(evidence),
    }


def result_data(bundle: object, request: object, records: SourceBytes, atoms: SourceBytes, transcript: dict[str, object] | None, offline: bool) -> dict[str, object]:
    data = {
        "adapter_id": bundle.capsule.target.adapter,  # type: ignore[attr-defined]
        "artifact_names": list(RESCUE_ARTIFACT_NAMES),
        "canon_md_sha256": sha256_text(bundle.canon_md),  # type: ignore[attr-defined]
        "capsule_id": bundle.capsule.capsule_id,  # type: ignore[attr-defined]
        "does_not_prove": rescue_does_not_prove(bundle),
        "manifest_sha256": sha256_bytes(bundle.manifest_bytes),  # type: ignore[attr-defined]
        "offline": offline,
        "out": None,
        "profile": request.profile,  # type: ignore[attr-defined]
        "readiness_probe_id": bundle.readiness_probe.probe_id,  # type: ignore[attr-defined]
        "source_inputs": [records.path, atoms.path],
        "source_state": bundle.capsule.source_state.to_dict(),  # type: ignore[attr-defined]
        "target": bundle.capsule.target.to_dict(),  # type: ignore[attr-defined]
        "transcript_included": transcript is not None,
        "transcript_trust": None,
        "write_status": "none",
    }
    if transcript is not None:
        data.update({key: transcript[key] for key in ("transcript_sha256", "transcript_size", "transcript_trust")})
    return data


def transcript_metadata(source: SourceBytes | None) -> dict[str, object] | None:
    if source is None:
        return None
    return {
        "transcript_sha256": sha256_bytes(source.data),
        "transcript_size": len(source.data),
        "transcript_source": source.path,
        "transcript_trust": TRANSCRIPT_TRUST,
    }


def rescue_does_not_prove(bundle: object) -> list[str]:
    return list(bundle.capsule.does_not_prove) + list(RESCUE_DOES_NOT_PROVE)  # type: ignore[attr-defined]


def _evidence(
    bundle: object,
    request: object,
    transcript: dict[str, object] | None,
    offline: bool,
    canon_md: bytes,
    manifest: bytes,
    readiness: bytes,
) -> dict[str, object]:
    identity = _identity(bundle, request, transcript, offline, canon_md, manifest, readiness)
    return {
        "schema": RESCUE_SCHEMA,
        "rescue_id": "rescue-" + canonical_sha256(identity).removeprefix("sha256:"),
        **identity,
        "artifacts": {
            "CANON.md": _hash_size(canon_md),
            "canon.capsule.json": _hash_size(manifest),
            "readiness-probe.json": _hash_size(readiness),
        },
    }


def _identity(
    bundle: object,
    request: object,
    transcript: dict[str, object] | None,
    offline: bool,
    canon_md: bytes,
    manifest: bytes,
    readiness: bytes,
) -> dict[str, object]:
    return {
        "budget": request.budget.to_dict(),  # type: ignore[attr-defined]
        "canon_md_sha256": sha256_bytes(canon_md),
        "capsule_id": bundle.capsule.capsule_id,  # type: ignore[attr-defined]
        "does_not_prove": rescue_does_not_prove(bundle),
        "manifest_sha256": sha256_bytes(manifest),
        "offline": offline,
        "profile": request.profile,  # type: ignore[attr-defined]
        "readiness_probe_id": bundle.readiness_probe.probe_id,  # type: ignore[attr-defined]
        "readiness_probe_sha256": sha256_bytes(readiness),
        "source_state": bundle.capsule.source_state.to_dict(),  # type: ignore[attr-defined]
        "target": bundle.capsule.target.to_dict(),  # type: ignore[attr-defined]
        "transcript": transcript,
    }


def _hash_size(data: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(data), "size": len(data)}


__all__ = ["build_artifact_bytes", "result_data", "rescue_does_not_prove", "transcript_metadata"]
