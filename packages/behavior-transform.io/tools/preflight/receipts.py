"""Timestamped receipts with secret screening."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SECRET_MARKERS = (
    "API_KEY=",
    "TOKEN=",
    "PASSWORD=",
    "PRIVATE KEY",
    ".env",
    "BEGIN OPENSSH",
)


def assert_no_secret_markers(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True)
    upper_text = text.upper()
    lower_text = text.lower()
    for marker in SECRET_MARKERS:
        haystack = lower_text if marker == ".env" else upper_text
        needle = marker if marker == ".env" else marker.upper()
        if needle in haystack:
            raise ValueError(f"receipt contains secret marker: {marker}")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _resolve_operator_fingerprint() -> str:
    """Inject operator fingerprint from env authority if available."""
    try:
        from env_authority import cached_authority
        grant = cached_authority()
        if grant.operator_fingerprint:
            return grant.operator_fingerprint
    except Exception:
        pass
    return ""


def write_receipt(receipt_root: Path, payload: dict[str, Any]) -> Path:
    operator_fp = _resolve_operator_fingerprint()
    receipt = {
        "schema": "warden.prefire.receipt.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    if operator_fp:
        receipt["operator_fingerprint"] = operator_fp
    assert_no_secret_markers(receipt)

    surface = str(receipt["surface"])
    surface_dir = receipt_root / surface
    surface_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = surface_dir / f"{_timestamp()}.json"
    latest_path = surface_dir / "latest.json"
    serialized = json.dumps(receipt, indent=2, sort_keys=True)
    receipt_path.write_text(serialized + "\n", encoding="utf-8")
    latest_path.write_text(serialized + "\n", encoding="utf-8")
    return receipt_path


def read_latest_receipt(receipt_root: Path, surface: str) -> dict[str, Any] | None:
    latest_path = receipt_root / surface / "latest.json"
    if not latest_path.exists():
        return None
    return json.loads(latest_path.read_text(encoding="utf-8"))
