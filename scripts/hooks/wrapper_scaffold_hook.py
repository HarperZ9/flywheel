"""wrapper_scaffold_hook.py -- deprecated; runs the capture hook module.

This script used to fetch every URL in a prompt through /api/snapshot with no
token and hide every failure. URL freezing is now its own opt-in, off by
default, decided by the gateway. The script prints one deprecation line on
stderr and runs `python -m harness.capture_hooks prompt --client
claude-code`. Mount the module directly; `flywheel traces hooks print-mount`
prints the line. This wrapper stays for one release.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.capture_hooks.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.stderr.write("flywheel capture: wrapper_scaffold_hook.py is deprecated; "
                     "mount python -m harness.capture_hooks prompt instead\n")
    raise SystemExit(main(["prompt", "--client", "claude-code", *sys.argv[1:]]))
