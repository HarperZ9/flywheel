"""Operate the zero-dependency file-backed harness store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--create-run-kind", default="")
    parser.add_argument("--create-run-title", default="")
    parser.add_argument("--inputs-json", default="")
    parser.add_argument("--receipt-json", default="")
    parser.add_argument("--receipt-kind", default="profile_bundle")
    parser.add_argument("--receipt-run-id", default="")
    parser.add_argument("--receipt-verdict", default="RECORDED")
    parser.add_argument("--copy-artifact", default="")
    parser.add_argument("--artifact-run-id", default="")
    parser.add_argument("--artifact-label", default="")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    store = FileBackedHarnessStore(Path(args.store_root))
    outputs = []
    if args.init:
        outputs.append(store.init())
    if args.create_run_kind:
        inputs = _load_json(args.inputs_json) if args.inputs_json else {}
        outputs.append(store.create_run(
            kind=args.create_run_kind,
            title=args.create_run_title,
            inputs=inputs,
        ))
    if args.receipt_json:
        body = _load_json(args.receipt_json)
        outputs.append(store.put_receipt(
            kind=args.receipt_kind,
            body=body,
            run_id=args.receipt_run_id,
            verdict=args.receipt_verdict,
        ))
    if args.copy_artifact:
        outputs.append(store.copy_artifact(
            Path(args.copy_artifact),
            run_id=args.artifact_run_id,
            label=args.artifact_label,
        ))
    if args.snapshot or not outputs:
        outputs.append(store.snapshot())

    result = {
        "schema": "harness.file-store-command/v1",
        "store_root": str(Path(args.store_root)),
        "outputs": outputs,
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
