"""Recover a run's scorecard from the attempt receipts it left on disk.

Use this when a run finished its attempts and raised before writing
comparison-input.json. The receipts already carry each final row and a hash over
it, so the scorecard is re-derived and checked rather than retyped.

    python scripts/rebuild_scorecard.py <run-root> --out comparison-input.json

Every receipt that fails its own hashes is excluded and listed in the output
under `rebuilt_from.excluded`, and the count of what was excluded is printed. A
rebuild that drops attempts silently would be worse than no rebuild at all.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.scorecard_rebuild import rebuild  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", help="the run directory holding the attempt receipts")
    parser.add_argument("--out", required=True, help="where to write the scorecard")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        document = rebuild(Path(args.run_root))
    except (OSError, ValueError) as exc:
        print(f"rebuild refused: {exc}", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")

    provenance = document["rebuilt_from"]
    if not args.quiet:
        print(f"{provenance['receipts_verified']} of {provenance['receipts_found']} receipts "
              f"verified into {out}")
        for item in provenance["excluded"]:
            print(f"  excluded {item['receipt']}: {item['reason']}")
    # An excluded receipt is a finding, so the run does not report success while
    # quietly publishing a comparison that is missing attempts.
    return 1 if provenance["excluded"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
