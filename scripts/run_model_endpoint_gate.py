"""Compatibility wrapper for the packaged model endpoint gate CLI."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.model_endpoint_gate_cli import (
    DEFAULT_PROMPT,
    GENERATION_TIMEOUT_SECONDS,
    _backend_for_profile,
    _canonical_sha256,
    _finalize_row,
    _health_probe,
    _load_profiles,
    _ollama_identity,
    _split_csv,
    _stable_row_receipt,
    _write,
    build_report,
    main,
    now_utc,
    probe_profile,
    render_markdown,
)


if __name__ == "__main__":
    raise SystemExit(main())
