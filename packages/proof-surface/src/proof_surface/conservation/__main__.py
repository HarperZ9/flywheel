"""`python -m proof_surface.conservation` -> the wedge CLI."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
