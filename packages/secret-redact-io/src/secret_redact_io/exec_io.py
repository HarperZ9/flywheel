from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from .models import GuardedExecResult
from .receipts import GuardrailReceipt
from .redaction import GuardrailPolicy


def run_guarded(
    argv: Sequence[str],
    *,
    timeout: float = 30,
    policy: GuardrailPolicy | None = None,
) -> GuardedExecResult:
    if not argv:
        raise ValueError("argv must contain at least one item")
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    decoder = "utf-8"
    stdout_raw = completed.stdout
    stderr_raw = completed.stderr
    stdout = stdout_raw.decode(decoder, errors="replace")
    stderr = stderr_raw.decode(decoder, errors="replace")
    active_policy = policy or GuardrailPolicy.default()
    stdout_redacted = active_policy.redact_text(stdout)
    stderr_redacted = active_policy.redact_text(stderr)
    counts = _merge_counts(stdout_redacted.counts, stderr_redacted.counts)
    receipt = GuardrailReceipt.create(
        operation="exec",
        target=Path(argv[0]).name,
        raw_bytes=stdout_raw + b"\n" + stderr_raw,
        redacted_text=stdout_redacted.text + "\n" + stderr_redacted.text,
        redactions=counts,
        metadata={"argv_count": len(argv), "returncode": completed.returncode},
    )
    return GuardedExecResult(
        stdout=stdout_redacted.text,
        stderr=stderr_redacted.text,
        returncode=completed.returncode,
        receipt=receipt,
    )


def _merge_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = merged.get(key, 0) + value
    return merged
