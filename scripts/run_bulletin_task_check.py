"""Observe or recheck a bounded Bulletin handoff; no acting-client credentials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.bulletin_observer import observe_handoff
from harness.bulletin_task_review import build_review, write_review
from harness.evidence_json import strict_load_json


def load(path: Path):
    with path.open("rb") as stream:
        return strict_load_json(stream.read(1048577))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contract", required=True, type=Path)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--base")
    source.add_argument("--observation", type=Path)
    p.add_argument("--allow-loopback", action="store_true")
    p.add_argument("--out", type=Path, help="Existing artifact directory, outside actor writes")
    args = p.parse_args()
    contract = load(args.contract)
    observation = (load(args.observation) if args.observation else
                   observe_handoff(contract, args.base, allow_loopback=args.allow_loopback))
    review = build_review(contract, observation)
    if args.out:
        write_review(args.out, review)
    print(json.dumps(review["result"], indent=2))
    return {"PASS": 0, "FAIL": 1, "UNVERIFIABLE": 3}[review["result"]["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
