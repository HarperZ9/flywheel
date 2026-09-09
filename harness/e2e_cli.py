"""CLI for product E2E journey manifests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from harness.e2e_journey_manifest import load_journey_manifest, validate_journey_manifest
from harness.e2e_runner import run_journey


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _validate(args: argparse.Namespace) -> int:
    manifest = load_journey_manifest(args.manifest, repo_root=args.source_root)
    issues = validate_journey_manifest(manifest)
    _print_json({
        "schema": manifest.schema,
        "journey_id": manifest.journey_id,
        "product": manifest.product,
        "runtime": {"kind": manifest.runtime.kind},
        "status": "valid",
        "issues": [{"field": issue.field, "message": issue.message} for issue in issues],
    })
    return 0


def _run(args: argparse.Namespace) -> int:
    result = run_journey(
        args.manifest,
        artifact_root=args.artifact_root,
        repo_root=args.source_root,
        run_id=args.run_id,
    )
    _print_json(result.to_dict())
    if args.strict and (result.status != "completed" or result.primary_outcome != "semantic_pass"):
        return 1
    return 0


def _list(args: argparse.Namespace) -> int:
    root = Path(args.manifest_dir)
    manifests = sorted(str(path) for path in root.glob("*.json"))
    _print_json({"status": "ok", "manifests": manifests})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="e2e-journey", description="Validate and run product E2E journeys.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("manifest")
    validate.add_argument("--source-root", default=None)
    validate.set_defaults(func=_validate)

    run = sub.add_parser("run")
    run.add_argument("manifest")
    run.add_argument("--artifact-root", required=True)
    run.add_argument("--source-root", default=None)
    run.add_argument("--run-id", default=None)
    run.add_argument("--strict", action="store_true",
                     help="exit nonzero unless the journey completes with primary_outcome semantic_pass")
    run.set_defaults(func=_run)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("manifest_dir")
    list_cmd.set_defaults(func=_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"e2e-journey failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
