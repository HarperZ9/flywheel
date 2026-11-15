"""Console-script entry point for proof-surface-report."""
from __future__ import annotations

import sys

from .core import main


def run() -> None:
    """Entry point registered as the ``proof-surface-report`` console script."""
    raise SystemExit(main(sys.argv[1:]))


if __name__ == "__main__":
    run()
