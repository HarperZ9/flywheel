"""CLI for independently versioned enterprise environment packages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness.enterprise_envs.compat import EnterpriseEnvironmentProductMissing, load_service_desk_product
from harness.enterprise_envs.receipts import ArtifactRootRejected, bind_rejection_receipt, prepare_artifact_root, write_json


def _run_e2e(environment_id: str, out: Path) -> dict[str, Any]:
    if environment_id != "service-desk-incident/v1":
        raise SystemExit(f"unknown enterprise environment: {environment_id}")
    return load_service_desk_product().run_e2e(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harness.enterprise_envs.cli")
    subcommands = parser.add_subparsers(dest="command", required=True)
    e2e = subcommands.add_parser("e2e")
    e2e.add_argument("environment_id")
    e2e.add_argument("--out", required=True, type=Path)
    e2e.add_argument("--failure-receipt", type=Path)
    args = parser.parse_args(argv)

    if args.command == "e2e":
        try:
            packet = _run_e2e(args.environment_id, args.out)
        except EnterpriseEnvironmentProductMissing as exc:
            print(json.dumps({"schema": "flywheel.enterprise-env-compat-error/v1", "error_code": exc.error_code, "environment_id": exc.environment_id, "required_distribution": exc.distribution}, sort_keys=True))
            return 2
        except ArtifactRootRejected as exc:
            response = _handle_rejection(args.environment_id, args.out, args.failure_receipt, exc.receipt)
            print(json.dumps(response, sort_keys=True))
            return 2
        print(json.dumps(packet, sort_keys=True))
        return 0
    raise SystemExit(f"unsupported command: {args.command}")


def _handle_rejection(environment_id: str, out: Path, failure_receipt: Path | None, receipt: dict[str, Any]) -> dict[str, Any]:
    response = dict(receipt)
    response["failure_receipt_written"] = False
    if failure_receipt is not None:
        source_root = Path(__file__).resolve().parents[2]
        safe_parent = prepare_artifact_root(source_root, failure_receipt.parent, environment_id)
        if safe_parent["verdict"] == "accept":
            response["failure_receipt_written"] = True
        else:
            response["failure_receipt_failure_code"] = safe_parent["failure_code"]
    response["rejected_artifact_root_created"] = Path(out).exists()
    bind_rejection_receipt(response)
    if failure_receipt is not None and response["failure_receipt_written"] is True:
        write_json(failure_receipt, response)
    return response


if __name__ == "__main__":
    raise SystemExit(main())
