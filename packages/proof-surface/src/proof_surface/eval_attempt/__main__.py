"""`python -m proof_surface.eval_attempt` -> the wedge CLI."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
