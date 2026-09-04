"""Keep the bytes a refused attempt produced.

Four of the twenty launched attempts in the 2026-09-03 head-to-head recorded no
raw output at all. Not an empty file, no file. One of them, `claude_code` on
`agt-001`, ran five provider turns, produced 10,421 output tokens, and billed
$0.1398. The receipt kept the token counts and the cost and dropped the text, so
a paid attempt left nothing behind to read.

The bound the harness enforces is correct. Discarding what it rejects is not. An
attempt that timed out, was refused, or answered with something the parser will
not accept still says something about the harness under test, and it is exactly
the attempt whose evidence a reader needs. A run that spends money and keeps
only the verdict `malformed_jsonl` cannot be debugged, and the next run repeats
the same failure at the same price.

So a refused attempt now keeps its own bytes, cut at a stated ceiling, recorded
under its own name, and hashed like every other attempt file.

The file is never graded. `output.txt` remains the only path an oracle reads,
and it is still written only for an attempt that returned, so nothing here can
turn a refused attempt into a scored one. What the caller passes in has already
been through the adapter's redaction, the same treatment a failure detail gets.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

# 256 KiB holds the whole of the largest refused output this harness has seen
# (10,421 output tokens, roughly 40 KB) with room to spare, and still bounds an
# attempt directory against a provider that streams without stopping.
MAX_REJECTED_BYTES = 1 << 18
REJECTED_OUTPUT_NAME = "rejected-output.txt"


def record_rejected_output(text: str, attempt_dir: Path, files: dict[str, Path]) -> dict[str, Any]:
    """Write what the harness refused, and report exactly what was written.

    Returns the row fields describing the file, or an empty mapping when the
    provider produced nothing, so a caller can update a row unconditionally.
    The truncation is stated rather than implied: both the size that arrived and
    the size that was kept travel with the hash, so a reader can tell a short
    answer from a cut one.
    """
    data = str(text or "").encode("utf-8", "replace")
    if not data:
        return {}
    truncated = len(data) > MAX_REJECTED_BYTES
    # Cutting a UTF-8 stream at a byte offset can land inside a character. Decode
    # the prefix loosely and re-encode it, so the file on disk is always valid.
    kept = data[:MAX_REJECTED_BYTES].decode("utf-8", "ignore").encode("utf-8") if truncated else data
    root = Path(attempt_dir)
    root.mkdir(parents=True, exist_ok=True)
    target = root / REJECTED_OUTPUT_NAME
    target.write_bytes(kept)
    files[target.name] = target
    return {
        "rejected_output_path": str(target),
        "rejected_output_sha256": hashlib.sha256(kept).hexdigest(),
        "rejected_output_bytes": len(kept),
        "rejected_output_arrived_bytes": len(data),
        "rejected_output_truncated": truncated,
    }
