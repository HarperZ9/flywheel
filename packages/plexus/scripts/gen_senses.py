"""Generate the sense manifests from src/plexus/sense_data/SENSES.tsv, or check they are in step.

  python scripts/gen_senses.py           # write src/plexus/sense_data/manifests/*.interop.json
  python scripts/gen_senses.py --check   # exit 1 and name each difference
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from plexus import senses  # noqa: E402


def main(argv: "list[str]") -> int:
    if "--check" in argv:
        problems = senses.check()
        for p in problems:
            print(p)
        print("senses: in step with SENSES.tsv" if not problems else f"senses: {len(problems)} problem(s)")
        return 1 if problems else 0
    names = senses.write()
    print(f"wrote {len(names)} manifests to {senses.MANIFEST_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
