"""CLI for previewing public-safe Bulletin outcome projections."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evidence_json import strict_load_json
from .bulletin_origin import BulletinOriginError, PUBLIC_BULLETIN_ORIGIN
from .gateway_operation import GatewayOperationError
from .outcome_bulletin import (
    OutcomeBulletinError,
    build_gateway_grant_request,
    build_gateway_publish_envelope,
    build_preview,
)


class _ArgumentFailure(Exception):
    pass


class _JsonParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise _ArgumentFailure()


def _parser() -> argparse.ArgumentParser:
    parser = _JsonParser(
        prog="python -m harness.outcome_bulletin_cli",
        description="Render a public-safe Bulletin finding from a selected outcome.",
    )
    commands = parser.add_subparsers(dest="command", required=True,
                                     parser_class=_JsonParser)
    preview = commands.add_parser("preview")
    preview.add_argument("--outcome", required=True)
    preview.add_argument("--bulletin-base-url", default=PUBLIC_BULLETIN_ORIGIN)
    grant = commands.add_parser("grant-request")
    grant.add_argument("--outcome", required=True)
    grant.add_argument("--bulletin-base-url", default=PUBLIC_BULLETIN_ORIGIN)
    grant.add_argument("--journey-ref", required=True)
    grant.add_argument("--expected-event-head", required=True)
    grant.add_argument("--client-request-id", required=True)
    grant.add_argument("--timeout", type=int, default=20)
    grant.add_argument("--credential-ref")
    publish = commands.add_parser("publish-envelope")
    publish.add_argument("--outcome", required=True)
    publish.add_argument("--bulletin-base-url", default=PUBLIC_BULLETIN_ORIGIN)
    publish.add_argument("--journey-ref", required=True)
    publish.add_argument("--expected-event-head", required=True)
    publish.add_argument("--client-request-id", required=True)
    publish.add_argument("--grant-ref", required=True)
    publish.add_argument("--timeout", type=int, default=20)
    publish.add_argument("--credential-ref")
    return parser


def _safe_error(code: str) -> dict:
    return {"schema": "flywheel.outcome-bulletin-error/v1",
            "error": {"code": code, "message": "outcome could not be projected"}}


def _load(path: str) -> dict:
    try:
        with Path(path).open("rb") as source:
            raw = source.read(1_048_577)
        value = strict_load_json(raw, max_bytes=1_048_576, max_depth=16)
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError):
        raise OutcomeBulletinError(
            "UNSAFE_PUBLIC_OUTCOME",
            "outcome contains fields or content that cannot be projected publicly",
        ) from None
    if type(value) is not dict:
        raise OutcomeBulletinError(
            "UNSAFE_PUBLIC_OUTCOME",
            "outcome contains fields or content that cannot be projected publicly",
        )
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        preview = build_preview(_load(args.outcome), bulletin_base_url=args.bulletin_base_url)
        if args.command == "grant-request":
            result = build_gateway_grant_request(
                preview,
                journey_ref=args.journey_ref,
                expected_event_head=args.expected_event_head,
                client_request_id=args.client_request_id,
                timeout=args.timeout,
                credential_ref=args.credential_ref,
            )
        elif args.command == "publish-envelope":
            result = build_gateway_publish_envelope(
                preview,
                journey_ref=args.journey_ref,
                expected_event_head=args.expected_event_head,
                client_request_id=args.client_request_id,
                grant_ref=args.grant_ref,
                timeout=args.timeout,
                credential_ref=args.credential_ref,
            )
        else:
            result = preview
    except _ArgumentFailure:
        result = _safe_error("INVALID_ARGUMENTS")
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    except (OutcomeBulletinError, BulletinOriginError, GatewayOperationError) as exc:
        result = _safe_error(exc.code)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
