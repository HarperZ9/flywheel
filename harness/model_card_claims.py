"""Non-executing model-card claim table for benchmark candidates."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "harness.model-card-claim-table/v1"
DEFAULT_ARTIFACT_DIR = "C:/tmp/model_card_claims"
CLAIM_STATUS_VALUES = [
    "verified_primary_source",
    "verified_secondary_source",
    "operator_relayed_unverified",
    "contradicted",
    "not_checked",
]
CLAIM_FIELDS = [
    "model_identity",
    "primary_model_card_url",
    "modality_claims",
    "context_window_claims",
    "license",
    "provenance_or_distillation",
    "local_execution_constraints",
    "publication_constraints",
]


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_claim_table(
    contract: dict[str, Any],
    *,
    contract_path: str,
    contract_sha256: str,
    evidence: dict[str, Any] | None = None,
    evidence_path: str = "",
    evidence_sha256: str = "",
    artifact_dir: str = DEFAULT_ARTIFACT_DIR,
    run_id: str = "",
) -> dict[str, Any]:
    candidates = _candidate_models(contract)
    evidence_by_model = _evidence_by_model(evidence or {})
    rows = [
        _model_row(model_id, evidence_by_model.get(model_id, {}), artifact_dir=artifact_dir)
        for model_id in candidates
    ]
    field_rows = [
        field
        for row in rows
        for field in row["claim_fields"]
    ]
    status_counts = {
        status: sum(1 for field in field_rows if field.get("status") == status)
        for status in CLAIM_STATUS_VALUES
    }
    unresolved_fields = [
        {
            "model_id": row["model_id"],
            "field": field["field"],
            "status": field["status"],
        }
        for row in rows
        for field in row["claim_fields"]
        if field["status"] not in {"verified_primary_source", "verified_secondary_source"}
    ]
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "run_id": run_id,
        "status": "planned_not_executed",
        "contract_path": contract_path,
        "contract_sha256": contract_sha256,
        "evidence_path": evidence_path,
        "evidence_sha256": evidence_sha256,
        "artifact_dir": artifact_dir,
        "source_label": _source_label(contract),
        "verified_facts_from_contract": _string_list(contract.get("verified_facts")),
        "assumptions_to_verify_before_result_claims": _string_list(
            contract.get("assumptions_to_verify_before_result_claims")
        ),
        "claim_status_values": CLAIM_STATUS_VALUES,
        "required_claim_fields": CLAIM_FIELDS,
        "model_rows": rows,
        "summary": {
            "model_candidates": len(rows),
            "claim_fields": len(field_rows),
            "verified_primary_source_fields": status_counts["verified_primary_source"],
            "verified_secondary_source_fields": status_counts["verified_secondary_source"],
            "operator_relayed_unverified_fields": status_counts["operator_relayed_unverified"],
            "contradicted_fields": status_counts["contradicted"],
            "not_checked_fields": status_counts["not_checked"],
            "unresolved_fields": len(unresolved_fields),
            "all_primary_sourced": bool(field_rows) and all(
                field.get("status") == "verified_primary_source" for field in field_rows
            ),
            "provider_execution": False,
            "endpoint_probe": False,
            "model_weight_read": False,
            "network_fetch": False,
        },
        "unresolved_fields": unresolved_fields,
        "non_execution_guards": [
            "This table must not call providers, probe endpoints, download weights, or browse the web.",
            "Relayed community claims remain unverified until a source URL, retrieval date, and claim field are recorded.",
            "Benchmark result reports must not promote unchecked or relayed claims into model-card facts.",
        ],
    }


def render_markdown(table: dict[str, Any]) -> str:
    summary = table["summary"]
    lines = [
        "# Model-card claim table",
        "",
        f"- Schema: `{table['schema']}`",
        f"- Status: `{table['status']}`",
        f"- Contract: `{table['contract_path']}`",
        f"- Contract sha256: `{table['contract_sha256']}`",
        f"- Evidence path: `{table.get('evidence_path', '')}`",
        f"- Model candidates: `{summary['model_candidates']}`",
        f"- Claim fields: `{summary['claim_fields']}`",
        f"- Unresolved fields: `{summary['unresolved_fields']}`",
        f"- Provider execution: `{str(summary['provider_execution']).lower()}`",
        f"- Endpoint probe: `{str(summary['endpoint_probe']).lower()}`",
        f"- Model weight read: `{str(summary['model_weight_read']).lower()}`",
        f"- Network fetch: `{str(summary['network_fetch']).lower()}`",
        "",
        "## Model rows",
        "",
        "| Model | Overall status | Primary URL | Unresolved fields |",
        "|---|---|---|---:|",
    ]
    for row in table["model_rows"]:
        lines.append(
            "| {model} | {status} | {url} | {unresolved} |".format(
                model=row["model_id"],
                status=row["overall_claim_status"],
                url=row.get("primary_model_card_url", ""),
                unresolved=sum(
                    1
                    for field in row["claim_fields"]
                    if field["status"] not in {"verified_primary_source", "verified_secondary_source"}
                ),
            )
        )
    lines.extend(["", "## Required claim fields", ""])
    for row in table["model_rows"]:
        lines.append(f"### {row['model_id']}")
        lines.append("")
        lines.append("| Field | Status | Source URL | Retrieved at |")
        lines.append("|---|---|---|---|")
        for field in row["claim_fields"]:
            lines.append(
                "| {field} | {status} | {url} | {retrieved} |".format(
                    field=field["field"],
                    status=field["status"],
                    url=field.get("source_url", ""),
                    retrieved=field.get("retrieved_at", ""),
                )
            )
        lines.append("")
    lines.extend(["## Non-execution guards", ""])
    for guard in table["non_execution_guards"]:
        lines.append(f"- {guard}")
    return "\n".join(lines).rstrip() + "\n"


def _candidate_models(contract: dict[str, Any]) -> list[str]:
    feedback = contract.get("source_feedback") if isinstance(contract.get("source_feedback"), dict) else {}
    raw = feedback.get("model_leads_unverified") if isinstance(feedback, dict) else []
    candidates = _string_list(raw)
    return candidates or ["unknown_unverified_model_lead"]


def _source_label(contract: dict[str, Any]) -> str:
    feedback = contract.get("source_feedback") if isinstance(contract.get("source_feedback"), dict) else {}
    return str(feedback.get("source_label", "")) if isinstance(feedback, dict) else ""


def _evidence_by_model(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not evidence:
        return {}
    if isinstance(evidence.get("models"), list):
        return {
            str(item.get("model_id", "")): item
            for item in evidence["models"]
            if isinstance(item, dict) and item.get("model_id")
        }
    if isinstance(evidence.get("model_rows"), list):
        return {
            str(item.get("model_id", "")): item
            for item in evidence["model_rows"]
            if isinstance(item, dict) and item.get("model_id")
        }
    return {
        str(model_id): row
        for model_id, row in evidence.items()
        if isinstance(row, dict)
    }


def _model_row(model_id: str, evidence: dict[str, Any], *, artifact_dir: str) -> dict[str, Any]:
    claim_fields = [
        _claim_field(field, _claim_evidence(evidence, field))
        for field in CLAIM_FIELDS
    ]
    verified = [field for field in claim_fields if field["status"] in {"verified_primary_source", "verified_secondary_source"}]
    primary_url = _first_primary_url(claim_fields)
    overall = (
        "verified_primary_source"
        if claim_fields and all(field["status"] == "verified_primary_source" for field in claim_fields)
        else "partially_verified"
        if verified
        else "operator_relayed_unverified"
    )
    base = Path(artifact_dir) / _safe_name(model_id)
    return {
        "schema": "harness.model-card-claim-table.model/v1",
        "model_id": model_id,
        "overall_claim_status": overall,
        "primary_model_card_url": primary_url,
        "claim_fields": claim_fields,
        "planned_artifacts": {
            "source_notes": str(base / "source_notes.md"),
            "claim_receipt": str(base / "claim_receipt.json"),
        },
    }


def _claim_evidence(evidence: dict[str, Any], field: str) -> dict[str, Any]:
    claims = evidence.get("claims") if isinstance(evidence.get("claims"), dict) else {}
    row = claims.get(field) if isinstance(claims, dict) else None
    if isinstance(row, dict):
        return row
    value = evidence.get(field)
    if isinstance(value, dict):
        return value
    if value:
        return {"value": value, "status": evidence.get("status", "verified_secondary_source")}
    return {}


def _claim_field(field: str, evidence: dict[str, Any]) -> dict[str, Any]:
    status = str(evidence.get("status", "operator_relayed_unverified" if evidence else "not_checked"))
    if status not in CLAIM_STATUS_VALUES:
        status = "not_checked"
    return {
        "field": field,
        "status": status,
        "value": str(evidence.get("value", "")),
        "source_url": str(evidence.get("source_url", evidence.get("url", ""))),
        "retrieved_at": str(evidence.get("retrieved_at", "")),
        "notes": str(evidence.get("notes", "")),
    }


def _first_primary_url(fields: list[dict[str, Any]]) -> str:
    for field in fields:
        if field["field"] == "primary_model_card_url" and field.get("value"):
            return str(field["value"])
    for field in fields:
        if field.get("source_url"):
            return str(field["source_url"])
    return ""


def _safe_name(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed).strip("_") or "model"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
