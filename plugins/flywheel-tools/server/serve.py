"""Load the packaged restricted entrypoint without installing the full harness."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness.tool_mcp import main

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
