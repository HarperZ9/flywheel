"""run_output_check.py -- check an answer before it reaches a reader.

A checkout-local way in to `harness.output_check_cli`, which is where the code
lives so an install gets it too. From an install the same command is
`flywheel check-output`. Read that module for the contract format, the
authority kinds, and what each exit code means.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.output_check_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
