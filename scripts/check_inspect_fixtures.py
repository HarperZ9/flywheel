from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.inspect_fixture_contract import check_fixture_dir  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check versioned Inspect contract fixtures for drift.")
    parser.add_argument("--root", type=Path, default=Path("tests/fixtures/inspect/v1"))
    args = parser.parse_args(argv)
    report = check_fixture_dir(args.root)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
