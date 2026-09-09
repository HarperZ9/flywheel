"""Canonical digest helpers for enterprise environment receipts."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Return the strict canonical JSON used by environment receipts."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def preimage(domain: str, value: Any) -> str:
    return f"{domain}\n{canonical_json(value)}"


def digest(domain: str, value: Any) -> str:
    return hashlib.sha256(preimage(domain, value).encode("utf-8")).hexdigest()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_text(data: str) -> str:
    return digest_bytes(data.encode("utf-8"))
