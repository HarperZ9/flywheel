from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .packet import validate_proof_surface_packet
from .validator import DEFAULT_SCHEMA, load_envelope, load_schema, scrub_text, validate_envelope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate model-reference provenance JSON envelopes."
    )
    parser.add_argument("envelopes", nargs="+", type=Path, help="Envelope JSON files.")
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="Schema JSON file. Defaults to the bundled schema.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON results.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a batch validation summary instead of per-file detail.",
    )
    parser.add_argument(
        "--proof-packet",
        action="store_true",
        help="Print a proof-surface interop packet as JSON.",
    )
    return parser


def _display_path(path: Path, base: Path | None = None) -> str:
    base = (base or Path.cwd()).resolve()
    try:
        return path.resolve().relative_to(base).as_posix()
    except (OSError, ValueError):
        return path.name


def _load_schema_or_error(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_schema(path), None
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return None, scrub_text(str(exc))


def _validate_path(path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        errors = validate_envelope(load_envelope(path), schema)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        errors = [{"path": "$", "message": scrub_text(str(exc))}]
    else:
        errors = [{"path": error.path, "message": scrub_text(error.message)} for error in errors]
    return {"path": _display_path(path), "valid": not errors, "errors": errors}


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    invalid = [result for result in results if not result["valid"]]
    return {
        "total": len(results),
        "valid": len(results) - len(invalid),
        "invalid": len(invalid),
        "error_count": sum(len(result["errors"]) for result in invalid),
        "action_items": [
            f"{result['path']}: resolve {len(result['errors'])} validation error(s)"
            for result in invalid[:8]
        ],
    }


def _format_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"total: {summary['total']}",
        f"valid: {summary['valid']}",
        f"invalid: {summary['invalid']}",
        f"error_count: {summary['error_count']}",
        "action_items:",
    ]
    actions = summary["action_items"] or ["none"]
    lines.extend(f"- {action}" for action in actions)
    return "\n".join(lines)


def _proof_surface_packet(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _summarize_results(results)
    status = "ready" if summary["invalid"] == 0 else "blocked"
    check_status = "pass" if summary["invalid"] == 0 else "fail"
    return {
        "proof_surface_version": "0.1",
        "packet_id": "model-provenance-validator-batch",
        "surface": "model provenance validation",
        "status": status,
        "claims": [
            {
                "claim": "Model/reference claims carry provenance envelopes.",
                "evidence": f"total envelopes={summary['total']}",
            },
            {
                "claim": "Envelope structure is validated before publication.",
                "evidence": f"valid={summary['valid']}, invalid={summary['invalid']}",
            },
            {
                "claim": "Invalid provenance is converted into action items.",
                "evidence": f"validation errors={summary['error_count']}",
            },
        ],
        "checks": [
            {
                "tool": "model-provenance-validator",
                "status": check_status,
                "summary": (
                    f"valid={summary['valid']}, invalid={summary['invalid']}, "
                    f"errors={summary['error_count']}"
                ),
            }
        ],
        "action_items": summary["action_items"],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    schema, schema_error = _load_schema_or_error(args.schema)
    if schema is None:
        print(json.dumps({"error": schema_error}, indent=2) if args.json else f"error: {schema_error}")
        return 1

    results = [_validate_path(path, schema) for path in args.envelopes]
    has_errors = any(not result["valid"] for result in results)

    if args.proof_packet:
        packet = _proof_surface_packet(results)
        issues = validate_proof_surface_packet(packet)
        if issues:
            print("error: generated proof-surface packet failed validation", file=sys.stderr)
            for issue in issues:
                print(f"  {issue}", file=sys.stderr)
            return 1
        print(json.dumps(packet, indent=2))
    elif args.summary:
        summary = _summarize_results(results)
        print(json.dumps(summary, indent=2) if args.json else _format_summary(summary))
    elif args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            if result["valid"]:
                print(f"{result['path']}: valid")
            else:
                print(f"{result['path']}: invalid")
                for error in result["errors"]:
                    print(f"  {error['path']}: {error['message']}")

    return 1 if has_errors else 0
