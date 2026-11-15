from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .models import GuardedTextResult
from .receipts import GuardrailReceipt
from .redaction import GuardrailPolicy


def read_text_guarded(path: str | Path, *, policy: GuardrailPolicy | None = None) -> GuardedTextResult:
    source = Path(path)
    raw = source.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    redacted = (policy or GuardrailPolicy.default()).redact_text(text)
    receipt = GuardrailReceipt.create(
        operation="read",
        target=str(source),
        raw_bytes=raw,
        redacted_text=redacted.text,
        redactions=redacted.counts,
        metadata={"exists": True},
    )
    return GuardedTextResult(text=redacted.text, receipt=receipt)


def write_text_guarded(
    path: str | Path,
    content: str,
    *,
    dry_run: bool = False,
    policy: GuardrailPolicy | None = None,
) -> GuardedTextResult:
    target = Path(path)
    raw = content.encode("utf-8")
    redacted = (policy or GuardrailPolicy.default()).redact_text(content)
    operation = "write.dry_run" if dry_run else "write"
    receipt = GuardrailReceipt.create(
        operation=operation,
        target=str(target),
        raw_bytes=raw,
        redacted_text=redacted.text,
        redactions=redacted.counts,
        metadata={"written": not dry_run},
    )
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(target, redacted.text)
    return GuardedTextResult(text=redacted.text, receipt=receipt)


def _atomic_write_text(target: Path, text: str) -> None:
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as tmp:
            temp_name = tmp.name
            tmp.write(text)
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
