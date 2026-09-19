"""Generate a Python-lane payload JSONL row for Flywheel's native bundle.

Given a lane name, emit the full ``packaging/python-lane-payloads.jsonl`` row for
it, derived from the lane registry plus the lane's own source checkout. The row
structure matches the rows already committed to that manifest and is validated by
``scripts/check_python_lane_payload_manifest.py``.

Source facts are read from the git object store at a pinned revision, not from the
working tree, so a dirty or advanced checkout does not perturb the evidence. File
bytes are read through the repo's checkout filters (``git cat-file --filters``) so
the recorded byte counts and hashes match a real on-disk checkout (autocrlf and
``.gitattributes`` applied), which is how the committed rows were built.

Reproduction: run this for ``gather`` at ``v1.8.2`` and ``crucible`` at ``v1.2.0``
(the revisions their committed rows pin) and the output is byte-identical to the
committed lines. The working checkouts have since advanced past those tags, so
``--rev`` selects the revision; it defaults to the checkout HEAD.

This module is a thin CLI. The build logic lives in ``_lane_payload_row.py`` and
``_lane_payload_source.py``, split out so every file stays under the 300-line gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _lane_payload_row import GeneratorError, build_row


def _emit(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", help="lane name (e.g. gather, crucible)")
    parser.add_argument(
        "--checkout-root",
        default="C:/dev",
        help="root that holds <source_repo> checkouts (default: C:/dev)",
    )
    parser.add_argument(
        "--rev",
        default=None,
        help="git revision to pin (default: the checkout HEAD)",
    )
    args = parser.parse_args(argv)
    try:
        row = build_row(args.lane, Path(args.checkout_root), args.rev)
    except GeneratorError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(_emit(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
