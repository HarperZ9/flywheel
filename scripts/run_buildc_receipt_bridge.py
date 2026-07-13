"""Import a BuildLang/buildc receipt as a flywheel byte-witness packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.buildc_receipt_bridge import bridge_buildc_receipt, run_buildc_verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("C:/dev/public/pubscan/quantalang"))
    parser.add_argument("--buildc", default="buildc")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    command_result = None
    if args.verify:
        command_result = run_buildc_verify(
            args.receipt,
            buildc=args.buildc,
            repo_root=args.repo_root,
            timeout_seconds=args.timeout_seconds,
        )
    packet = bridge_buildc_receipt(
        args.receipt,
        export_path=args.export,
        repo_root=args.repo_root,
        command_result=command_result,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    print(f"out={args.out}")
    print(f"verdict={packet['flywheel']['verdict']}")
    print(f"witness={packet['witness']['byte_witness_id']}")
    print(f"verification_attached={packet['witness']['verification_attached']}")
    return 0 if packet["flywheel"]["verdict"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
