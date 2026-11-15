"""External organ adapters.

This module is the dependency-free seam for sibling tools. RAW, EMET, and
provenance-sensorium keep their own repos and emit their own JSON; the membrane
only witnesses those reports as bytes and projects compact facts into its native
Observation/CompositeObservation/ProvenanceGraph contracts.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from .composite import CompositeObservation
from .observation import Observation, Provenance, Status
from .provenance import OBSERVED_AFTER, ProvenanceGraph

_PASS = {"pass", "passed", "match", "valid", "corroborated", "coherent", "observed", "ok"}
_WARN = {"warn", "warning", "drift", "view_differs_from_source", "revertible", "degraded"}
_BLOCK = {
    "block",
    "blocked",
    "broken",
    "fail",
    "failed",
    "not_revertible",
    "quarantine_read_path_divergence",
}


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("ascii")


def _status(value: Any) -> Status:
    token = str(value or "").strip().lower().replace("-", "_")
    if token in _PASS:
        return Status.PASS
    if token in _WARN:
        return Status.WARN
    if token in _BLOCK:
        return Status.BLOCK
    return Status.UNVERIFIED


def _data(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _report_observation(
    report: Mapping[str, Any],
    *,
    organ: str,
    subject: str,
    summary: str,
    status_value: Any,
    data: Mapping[str, Any] | None = None,
    command: str | None = None,
) -> Observation:
    payload = _canonical_bytes(report)
    provenance = Provenance.witness_bytes(
        f"external-organ:{organ}",
        payload,
        "medium",
        command=command,
    )
    compact = _data(data)
    compact["report_sha256"] = provenance.digest
    if status_value is not None:
        compact["external_status"] = str(status_value)
    if "verdict" in report:
        compact["external_verdict"] = str(report["verdict"])
    return Observation(
        organ=organ,
        subject=subject,
        summary=summary,
        status=_status(status_value),
        provenance=provenance,
        data=compact,
    )


def external_report_observation(report: Mapping[str, Any]) -> Observation:
    """Convert a generic external JSON report into a compact Observation."""
    organ = str(report.get("organ") or report.get("sensor") or "external-organ")
    subject = str(report.get("subject") or report.get("path") or report.get("name") or organ)
    status_value = report.get("status") or report.get("verdict") or "unverified"
    summary = str(report.get("summary") or f"{organ} report: {status_value}")
    return _report_observation(
        report,
        organ=organ,
        subject=subject,
        summary=summary,
        status_value=status_value,
        data=report.get("data") if isinstance(report.get("data"), Mapping) else {},
        command=report.get("command") if isinstance(report.get("command"), str) else None,
    )


def raw_eye_observation(
    report: Mapping[str, Any],
    *,
    subject: str = "raw-eye:live",
) -> Observation:
    """Project a RAW `raw_eyes.py watch`-style report into an Observation."""
    frame_present = bool(report.get("frame_present"))
    has_samples = int(report.get("samples") or 0) > 0
    frame_error = report.get("frame_error")
    if frame_present and not frame_error:
        status_value = "pass"
    elif has_samples:
        status_value = "warn"
    else:
        status_value = "unverified"
    summary = (
        "raw eye report: frame present"
        if frame_present and not frame_error
        else "raw eye report: frame unavailable"
        if has_samples
        else "raw eye report: no live samples"
    )
    latest = report.get("latest") if isinstance(report.get("latest"), Mapping) else {}
    avg = report.get("avg") if isinstance(report.get("avg"), Mapping) else {}
    frame_metrics = (
        report.get("frame_metrics") if isinstance(report.get("frame_metrics"), Mapping) else {}
    )
    data = {
        "samples": int(report.get("samples") or 0),
        "frame_present": frame_present,
        "has_frame_metrics": bool(frame_metrics),
        "latest_keys": sorted(str(k) for k in latest),
        "avg_keys": sorted(str(k) for k in avg),
    }
    for key in ("width", "height", "quality_ok", "numeric_ok"):
        if key in frame_metrics:
            data[key] = frame_metrics[key]
    if frame_error:
        data["frame_error"] = str(frame_error)
    return _report_observation(
        report,
        organ="raw-eye",
        subject=subject,
        summary=summary,
        status_value=status_value,
        data=data,
        command="raw_eyes.py watch",
    )


def raw_health_observation(
    receipt: Mapping[str, Any],
    *,
    subject: str = "raw-health:live",
) -> Observation:
    """Project a RAW health receipt into a compact Observation."""
    runtime = receipt.get("runtime") if isinstance(receipt.get("runtime"), Mapping) else {}
    eyes = receipt.get("eyes") if isinstance(receipt.get("eyes"), Mapping) else {}
    watch = eyes.get("watch") if isinstance(eyes.get("watch"), Mapping) else {}
    gpu_trace = (
        receipt.get("gpu_trace") if isinstance(receipt.get("gpu_trace"), Mapping) else {}
    )
    status_value = receipt.get("status") or "unverified"
    data = {
        "receipt_version": str(receipt.get("receipt_version") or ""),
        "scope": str(receipt.get("scope") or ""),
        "runtime_verified": int(runtime.get("verified") or 0),
        "runtime_soft": int(runtime.get("soft") or 0),
        "runtime_attention": int(runtime.get("attention") or 0),
        "watch_status": str(eyes.get("watch_status") or ""),
        "frame_present": bool(watch.get("frame_present")),
        "watch_samples": int(watch.get("samples") or 0),
        "attribute_status": str(eyes.get("attribute_status") or ""),
        "gpu_trace_status": str(gpu_trace.get("status") or "not-applicable"),
    }
    assertions = (
        gpu_trace.get("assertions") if isinstance(gpu_trace.get("assertions"), Mapping) else {}
    )
    if assertions:
        data["gpu_trace_assertions"] = int(assertions.get("assertion_count") or 0)
        data["gpu_trace_failures"] = int(assertions.get("failure_count") or 0)
    return _report_observation(
        receipt,
        organ="raw-health",
        subject=subject,
        summary=str(receipt.get("summary") or f"raw health: {status_value}"),
        status_value=status_value,
        data=data,
        command="raw_health.py receipt",
    )


def _bundle_status(entries: list[Any]) -> str:
    statuses = [
        str(entry.get("status") or "unverified").lower()
        for entry in entries
        if isinstance(entry, Mapping)
    ]
    if any(status in {"deny", "fail"} for status in statuses):
        return "block"
    if any(status == "warn" for status in statuses):
        return "warn"
    if any(status in {"needs-human", "unknown", "unverified"} for status in statuses):
        return "unverified"
    if statuses and all(status in {"allow", "not-applicable", "pass"} for status in statuses):
        return "pass"
    return "unverified"


def organ_receipt_bundle_observation(
    bundle: Mapping[str, Any],
    *,
    subject: str | None = None,
) -> Observation:
    """Project a proof-surface OrganReceiptBundle into a compact Observation."""
    entries = bundle.get("entries") if isinstance(bundle.get("entries"), list) else []
    edges = bundle.get("edges") if isinstance(bundle.get("edges"), list) else []
    organ_ids = sorted(
        {
            str(entry.get("organ_id"))
            for entry in entries
            if isinstance(entry, Mapping) and entry.get("organ_id")
        }
    )
    receipt_kinds = sorted(
        {
            str(entry.get("receipt_kind"))
            for entry in entries
            if isinstance(entry, Mapping) and entry.get("receipt_kind")
        }
    )
    status_value = _bundle_status(entries)
    data = {
        "bundle_id": str(bundle.get("bundle_id") or ""),
        "version": str(bundle.get("organ_bundle_version") or ""),
        "entry_count": len(entries),
        "edge_count": len(edges),
        "organ_ids": organ_ids,
        "receipt_kinds": receipt_kinds,
    }
    return _report_observation(
        bundle,
        organ="organ-receipt-bundle",
        subject=subject or str(bundle.get("subject") or "organ-receipt-bundle"),
        summary=str(bundle.get("notes") or f"organ receipt bundle: {status_value}"),
        status_value=status_value,
        data=data,
        command="proof_surface validate_organ_receipt_bundle",
    )


def _emet_subject(receipt: Mapping[str, Any]) -> str:
    subjects = receipt.get("subject")
    if isinstance(subjects, list) and subjects:
        first = subjects[0]
        if isinstance(first, Mapping):
            return str(first.get("name") or receipt.get("receipt_id") or "emet-subject")
    return str(receipt.get("subject") or receipt.get("receipt_id") or "emet-subject")


def emet_receipt_observation(receipt: Mapping[str, Any]) -> Observation:
    """Convert an EMET proof-surface receipt into an advisory Observation."""
    verdict = str(receipt.get("verdict") or "UNVERIFIABLE")
    witness = receipt.get("witness") if isinstance(receipt.get("witness"), Mapping) else {}
    subjects = receipt.get("subject") if isinstance(receipt.get("subject"), list) else []
    data = {
        "verdict": verdict,
        "check": str(witness.get("check") or ""),
        "subject_count": len(subjects),
        "receipt_id": str(receipt.get("receipt_id") or ""),
    }
    if witness.get("self_sha256"):
        data["witness_self_sha256"] = str(witness["self_sha256"])
    return _report_observation(
        receipt,
        organ="emet",
        subject=_emet_subject(receipt),
        summary=f"emet receipt: {verdict}",
        status_value=verdict,
        data=data,
        command="emet proof_surface_receipt.py",
    )


def provenance_receipt_observations(receipt: Mapping[str, Any]) -> list[Observation]:
    """Convert provenance-sensorium receipt JSON without importing that package."""
    root = str(receipt.get("root") or "")
    observations: list[Observation] = []
    for item in receipt.get("observations", []):
        if not isinstance(item, Mapping):
            continue
        data = _data(item.get("data") if isinstance(item.get("data"), Mapping) else {})
        data["receipt_root"] = root
        observations.append(
            Observation(
                organ="provenance-sensorium:" + str(item.get("sensor") or "sensor"),
                subject=str(item.get("subject") or root or "provenance-subject"),
                summary=str(item.get("summary") or "provenance observation"),
                status=_status(item.get("status")),
                provenance=Provenance.from_dict(item["provenance"]),
                data=data,
            )
        )
    return observations


def external_composite(
    observations: Iterable[Observation],
    *,
    timestamp: str = "",
) -> CompositeObservation:
    return CompositeObservation(list(observations), timestamp=timestamp)


def build_external_graph(observations: Iterable[Observation]) -> ProvenanceGraph:
    graph = ProvenanceGraph()
    previous: str | None = None
    for index, observation in enumerate(observations):
        node_id = f"external-observation-{index}"
        parents = [previous] if previous is not None else []
        graph.add_observation(node_id, observation, parents=parents, edge_type=OBSERVED_AFTER)
        previous = node_id
    return graph
