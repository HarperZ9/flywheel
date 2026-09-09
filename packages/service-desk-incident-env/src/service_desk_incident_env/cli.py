"""Dedicated CLI for the ServiceDesk incident environment product."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness.enterprise_envs.receipts import ArtifactRootRejected, bind_rejection_receipt, prepare_artifact_root, write_json

from . import product


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="service-desk-incident-env", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("identity", "descriptor", "contract"):
        sub = commands.add_parser(name)
        sub.add_argument("--json", action="store_true")
    e2e = commands.add_parser("e2e")
    e2e.add_argument("--out", required=True, type=Path)
    e2e.add_argument("--failure-receipt", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("artifact_dir", type=Path)
    verify.add_argument("--recompute", action="store_true")
    verify.add_argument("--json", action="store_true")
    review = commands.add_parser("review")
    review.add_argument("artifact_dir", type=Path)
    review.add_argument("--json", action="store_true")
    review.add_argument("--html-out", type=Path)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--out", required=True, type=Path)
    doctor.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "identity":
        return _emit(product.identity(), args.json)
    if args.command == "descriptor":
        return _emit(product.descriptor(), args.json)
    if args.command == "contract":
        return _emit(product.contract(), args.json)
    if args.command == "e2e":
        try:
            print(json.dumps(product.run_e2e(args.out), sort_keys=True))
            return 0
        except ArtifactRootRejected as exc:
            print(json.dumps(_handle_rejection(args.out, args.failure_receipt, exc.receipt), sort_keys=True))
            return 2
    if args.command == "verify":
        result = product.verify_artifacts(args.artifact_dir)
        _emit(result, args.json)
        return 0 if result["observed_state"] == "pass" else 1
    if args.command == "review":
        report = product.review_artifacts(args.artifact_dir)
        if args.html_out:
            try:
                product.write_review_html(report, args.html_out)
            except (OSError, ValueError) as exc:
                # Do not echo OS errors that contain private paths.
                code = str(exc) if isinstance(exc, ValueError) else "html_output_write_failed"
                print(code, file=sys.stderr)
                return 2
        _emit(report, args.json)
        return 0 if report["verification"]["observed_state"] == "pass" else 1
    if args.command == "doctor":
        report = product.doctor(args.out)
        _emit(report, args.json)
        return 0 if report["installed_artifact_verification"]["observed_state"] == "pass" else 1
    return 2


def _emit(doc: dict[str, Any], as_json: bool) -> int:
    if as_json:
        print(json.dumps(doc, sort_keys=True))
    else:
        print(json.dumps(doc, indent=2, sort_keys=True))
    return 0


def _handle_rejection(out: Path, failure_receipt: Path | None, receipt: dict[str, Any]) -> dict[str, Any]:
    response = dict(receipt)
    response["failure_receipt_written"] = False
    if failure_receipt is not None:
        source_root = Path(__file__).resolve().parents[2]
        safe_parent = prepare_artifact_root(source_root, failure_receipt.parent, product.ENVIRONMENT_ID)
        if safe_parent["verdict"] == "accept":
            response["failure_receipt_written"] = True
        else:
            response["failure_receipt_failure_code"] = safe_parent["failure_code"]
    response["rejected_artifact_root_created"] = Path(out).exists()
    bind_rejection_receipt(response)
    if failure_receipt is not None and response["failure_receipt_written"]:
        write_json(failure_receipt, response)
    return response


if __name__ == "__main__":
    raise SystemExit(main())
