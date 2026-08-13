"""Packaged JSON CLI for the Unified Evidence Journey."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evidence_json import canonical_bytes
from .evidence_route import evidence_post


class _JsonParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        result = {"schema": "flywheel.evidence-transport-error/v1",
                  "error": {"code": "INVALID_ARGUMENTS",
                            "message": "journey command arguments are invalid"}}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2)


def _parser() -> argparse.ArgumentParser:
    parser = _JsonParser(prog="flywheel journey",
        description="Start, project, check, export, and recheck evidence journeys.")
    sub = parser.add_subparsers(dest="action", required=True, parser_class=_JsonParser)
    start = sub.add_parser("start")
    start.add_argument("--journey-id", required=True)
    start.add_argument("--goal", required=True)
    start.add_argument("--created-at", required=True)
    start.add_argument("--intake-ref", required=True)
    project = sub.add_parser("project")
    project.add_argument("--journey-ref", required=True)
    project.add_argument("--lens", required=True)
    check = sub.add_parser("check")
    check.add_argument("--journey-ref", required=True)
    check.add_argument("--claim-id", required=True)
    check.add_argument("--oracle-id", required=True)
    check.add_argument("--candidate-ref", required=True)
    check.add_argument("--context-ref", required=True)
    export = sub.add_parser("export")
    export.add_argument("--journey-ref", required=True)
    export.add_argument("--packet-ref", required=True)
    recheck = sub.add_parser("recheck")
    recheck.add_argument("--packet-ref", required=True)
    recheck.add_argument("--expected-manifest-sha256")
    return parser


def _request(args: argparse.Namespace) -> dict:
    fields = {
        "start": ("journey_id", "goal", "created_at", "intake_ref"),
        "project": ("journey_ref", "lens"),
        "check": ("journey_ref", "claim_id", "oracle_id", "candidate_ref", "context_ref"),
        "export": ("journey_ref", "packet_ref"),
        "recheck": ("packet_ref", "expected_manifest_sha256"),
    }[args.action]
    return {name: getattr(args, name) for name in fields
            if getattr(args, name, None) is not None}


def result_exit(result: dict, *, http_status: int, action: str) -> int:
    """Map server-owned verdicts to the stable journey CLI exit contract."""
    verdict = result.get("verdict")
    if verdict in {"PASS", "MATCH"}:
        return 0
    if verdict in {"FAIL", "DRIFT"}:
        return 1
    if verdict == "UNDECIDED":
        return 3
    if verdict == "UNVERIFIABLE":
        return 4
    return 0 if http_status < 400 else 2


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    request = _request(args)
    result, status = evidence_post(f"/api/evidence/{args.action}",
        canonical_bytes(request), root=Path.cwd() if root is None else Path(root))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return result_exit(result, http_status=status, action=args.action)


if __name__ == "__main__":
    raise SystemExit(main())
