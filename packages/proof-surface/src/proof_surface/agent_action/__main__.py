"""Enable `python -m proof_surface.agent_action ...`."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
