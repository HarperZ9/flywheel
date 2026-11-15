from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class GuardrailReceipt:
    operation: str
    target: str
    raw_bytes: int
    redacted_bytes: int
    input_sha256: str
    redacted_sha256: str
    redactions: dict[str, int]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    @classmethod
    def create(
        cls,
        *,
        operation: str,
        target: str,
        raw_bytes: bytes,
        redacted_text: str,
        redactions: dict[str, int],
        metadata: dict[str, Any] | None = None,
    ) -> "GuardrailReceipt":
        redacted_bytes = redacted_text.encode("utf-8")
        return cls(
            operation=operation,
            target=target,
            raw_bytes=len(raw_bytes),
            redacted_bytes=len(redacted_bytes),
            input_sha256=_sha256_bytes(raw_bytes),
            redacted_sha256=_sha256_bytes(redacted_bytes),
            redactions=dict(sorted(redactions.items())),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "input_sha256": self.input_sha256,
            "metadata": self.metadata,
            "operation": self.operation,
            "raw_bytes": self.raw_bytes,
            "redacted_bytes": self.redacted_bytes,
            "redacted_sha256": self.redacted_sha256,
            "redactions": self.redactions,
            "target": self.target,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)
