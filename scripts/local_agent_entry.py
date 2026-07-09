"""Entry-point wrapper for a one-file local-agent executable."""
from __future__ import annotations

from harness.local_agent_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
