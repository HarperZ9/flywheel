from __future__ import annotations

from typing import Any, TypedDict


ORCA_ORGAN_EXCHANGE_MODULE = "orca.module.organ_exchange.bundle"


class OrganRowFields(TypedDict):
    contract: str
    kind: str
    surface: str
    status: str
    evidence: str


def is_orca_organ_exchange(data: dict[str, Any]) -> bool:
    return data.get("module_id") == ORCA_ORGAN_EXCHANGE_MODULE and isinstance(
        data.get("summary"), dict
    )


def is_organ_receipt_bundle(data: dict[str, Any]) -> bool:
    return (
        "organ_bundle_version" in data
        and "bundle_id" in data
        and isinstance(data.get("entries"), list)
    )


def summarize_orca_organ_exchange(data: dict[str, Any]) -> OrganRowFields:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    bundle = data.get("bundle") if isinstance(data.get("bundle"), dict) else {}
    return {
        "contract": _text(
            bundle.get("bundle_id") or data.get("module_id") or "organ-exchange"
        ),
        "kind": "organ-exchange",
        "surface": _text(summary.get("subject"), "workspace-organ-health"),
        "status": _text(summary.get("bundle_status")),
        "evidence": _exchange_evidence(summary),
    }


def summarize_organ_receipt_bundle(data: dict[str, Any]) -> OrganRowFields:
    entries = _objects(data.get("entries"))
    return {
        "contract": _text(data.get("bundle_id"), "organ-receipt-bundle"),
        "kind": "organ-receipt-bundle",
        "surface": _text(data.get("subject"), "workspace-organ-health"),
        "status": _bundle_status(entries),
        "evidence": _bundle_evidence(data, entries),
    }


def _exchange_evidence(summary: dict[str, Any]) -> str:
    return (
        f"entries={_int(summary.get('entry_count'))}, "
        f"collected={_int(summary.get('collected_count'))}, "
        f"organs={len(_strings(summary.get('organ_ids')))}, "
        f"receipts={len(_strings(summary.get('receipt_kinds')))}"
    )


def _bundle_evidence(data: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    organ_count = len({
        item for item in (_text(entry.get("organ_id"), "") for entry in entries) if item
    })
    receipt_count = len({
        item
        for item in (_text(entry.get("receipt_kind"), "") for entry in entries)
        if item
    })
    return (
        f"entries={len(entries)}, "
        f"edges={len(_objects(data.get('edges')))}, "
        f"organs={organ_count}, "
        f"receipts={receipt_count}"
    )


def _bundle_status(entries: list[dict[str, Any]]) -> str:
    statuses = [_text(entry.get("status"), "unverified").lower() for entry in entries]
    if any(status in {"deny", "fail", "block"} for status in statuses):
        return "block"
    if any(status == "warn" for status in statuses):
        return "warn"
    if any(status == "needs-human" for status in statuses):
        return "needs-human"
    if any(status in {"unknown", "unverified"} for status in statuses):
        return "unverified"
    return "pass" if statuses else "unverified"


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _text(value: object, default: str = "unknown") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return default


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
