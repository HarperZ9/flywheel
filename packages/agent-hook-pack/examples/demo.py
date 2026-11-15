#!/usr/bin/env python
# Best-effort demo -- not runtime-verified by author.
"""End-to-end demo of the agent_hook_pack public API.

Run from a clone (with the package installed via `pip install -e .`, or with
`PYTHONPATH=src`):

    python examples/demo.py

It exercises the real, existing API only:
  - hook_pack.discover_hooks()
  - hook_pack.audit_hooks()
  - hook_pack.install_hooks()
  - hook_pack.HOOK_DIR / EXPECTED_HOOKS
  - the CLI entry point (agent_hook_pack.cli.main)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_hook_pack import __version__, hook_pack
from agent_hook_pack.cli import main as cli_main


def main() -> int:
    print(f"agent-hook-pack version: {__version__}")
    print(f"packaged hook directory: {hook_pack.HOOK_DIR}\n")

    # 1. Discover the packaged hooks.
    hooks = hook_pack.discover_hooks()
    print("discovered hooks:")
    for path in hooks:
        print(f"  - {path.name}")
    print()

    # 2. Audit the packaged hooks. An empty list means no findings.
    findings = hook_pack.audit_hooks(hook_pack.HOOK_DIR)
    if findings:
        print("audit findings:")
        for path, issue in findings:
            print(f"  {path}: {issue}")
    else:
        print("audit findings: none")
    print()

    # 3. Install the hooks into a throwaway directory and confirm the count.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "hooks"
        copied = hook_pack.install_hooks(hook_pack.HOOK_DIR, target)
        print(f"installed {copied} hook file(s) into {target}")
        installed = sorted(p.name for p in target.iterdir())
        print(f"target now contains: {installed}\n")

    # 4. Drive the same behavior through the CLI entry point.
    print("CLI `list`:")
    cli_main(["list"])
    print("\nCLI `audit` (exit code):", cli_main(["audit"]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
