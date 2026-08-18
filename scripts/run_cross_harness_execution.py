"""Source-checkout wrapper for the packaged cross-harness command."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.cross_harness_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
