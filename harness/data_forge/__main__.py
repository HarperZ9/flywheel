"""Module entrypoint for `python -m harness.data_forge`."""

from __future__ import annotations

from .pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
