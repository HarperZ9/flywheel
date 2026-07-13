"""flywheel_entry.py -- PyInstaller entry for the `flywheel` exe.

Delegates to harness.cli_entry.main, which is the single dispatch surface
(pass-through to run_harness_cli + the new umbrella subcommands). This file
exists so the .spec has a stable top-level entry; cli_entry does the work.
"""
from __future__ import annotations

from harness.cli_entry import main

if __name__ == "__main__":
    raise SystemExit(main())
