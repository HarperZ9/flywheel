"""Packaged JSON CLI for durable Journey and exact grant actions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Callable

from .evidence_cli import main as evidence_main, result_exit
from .evidence_json import canonical_bytes, strict_load_json
from .evidence_public import ERROR_SCHEMA
from .grant_route import grant_post
from .journey_route import journey_post
from .operation_grants import load_or_create_owner_ref


class _ArgumentFailure(Exception):
    pass


class _JsonParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise _ArgumentFailure()


def _common(parser, action: str, *, grant: bool) -> None:
    if action == "create":
        parser.add_argument("--goal", required=True)
        parser.add_argument("--intake-ref", required=True)
        parser.add_argument("--client-request-id", required=True)
    elif action == "append":
        parser.add_argument("--journey-ref", required=True)
        parser.add_argument("--expected-event-head", required=True)
        parser.add_argument("--client-request-id", required=True)
        parser.add_argument("--command", required=True)
    elif action == "check":
        for field in ("journey-ref", "expected-event-head", "client-request-id",
                      "claim-id", "oracle-id", "candidate-ref", "context-ref"):
            parser.add_argument(f"--{field}", required=True)
    elif action == "cancel":
        for field in ("journey-ref", "expected-event-head", "client-request-id",
                      "operation-ref"):
            parser.add_argument(f"--{field}", required=True)
    elif action == "export":
        for field in ("journey-ref", "expected-event-head", "client-request-id",
                      "packet-ref"):
            parser.add_argument(f"--{field}", required=True)
    if grant:
        parser.add_argument("--grant-ref", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = _JsonParser(prog="flywheel",
        description="Durable actions: create, list, resume, append, check, cancel, export. Legacy evidence actions: start, project, recheck.")
    surfaces = parser.add_subparsers(dest="surface", required=True,
                                     parser_class=_JsonParser)
    grant = surfaces.add_parser("grant")
    grant_actions = grant.add_subparsers(dest="grant_action", required=True,
                                         parser_class=_JsonParser)
    prepare = grant_actions.add_parser("prepare")
    preparations = prepare.add_subparsers(dest="action", required=True,
                                          parser_class=_JsonParser)
    for action in ("create", "append", "check", "cancel", "export"):
        _common(preparations.add_parser(action), action, grant=False)
    approve = grant_actions.add_parser("approve-once")
    approve.add_argument("--proposal-ref", required=True)
    journey = surfaces.add_parser("journey",
        description="Durable actions plus legacy evidence start, project, and recheck.")
    actions = journey.add_subparsers(dest="action", required=True,
                                     parser_class=_JsonParser)
    for action in ("create", "append", "check", "cancel", "export"):
        _common(actions.add_parser(action), action, grant=True)
    actions.add_parser("list")
    resume = actions.add_parser("resume")
    resume.add_argument("--journey-ref", required=True)
    resume.add_argument("--lens", required=True)
    return parser


def _legacy(argv: list[str] | None) -> bool:
    raw = list(argv or [])
    if not raw or raw[0] != "journey" or len(raw) < 2:
        return False
    action = raw[1]
    if action in {"start", "project", "recheck"}:
        return True
    return action in {"check", "export"} and not any(
        flag in raw for flag in ("--grant-ref", "--expected-event-head",
                                 "--client-request-id"))


def _request(args: argparse.Namespace) -> dict:
    if args.surface == "grant" and args.grant_action == "approve-once":
        return {"proposal_ref": args.proposal_ref}
    fields = {
        "create": ("goal", "intake_ref", "client_request_id"),
        "list": (), "resume": ("journey_ref", "lens"),
        "append": ("journey_ref", "expected_event_head", "client_request_id", "command"),
        "check": ("journey_ref", "expected_event_head", "client_request_id",
                  "claim_id", "oracle_id", "candidate_ref", "context_ref"),
        "cancel": ("journey_ref", "expected_event_head", "client_request_id",
                   "operation_ref"),
        "export": ("journey_ref", "expected_event_head", "client_request_id", "packet_ref"),
    }[args.action]
    result = {name: getattr(args, name) for name in fields}
    if "command" in result:
        result["command"] = strict_load_json(result["command"])
    if args.surface == "journey" and args.action not in {"list", "resume"}:
        result["grant_ref"] = args.grant_ref
    return result


def _argument_error() -> dict:
    return {"schema": ERROR_SCHEMA, "error": {
        "code": "INVALID_ARGUMENTS", "message": "journey command arguments are invalid"}}


def main(argv: list[str] | None = None, *, home: Path | None = None,
         state_root: Path | None = None, evidence_root: Path | None = None,
         clock: Callable[[], str] | None = None) -> int:
    if _legacy(argv):
        return evidence_main(list(argv or [])[1:], root=(
            Path(evidence_root) if evidence_root is not None else Path.cwd()))
    try:
        args = _parser().parse_args(argv)
        request = _request(args)
    except (_ArgumentFailure, TypeError, ValueError, UnicodeError, RecursionError):
        result = _argument_error()
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    from datetime import datetime, timezone
    effective_clock = clock or (
        lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    effective_home = Path(home) if home is not None else Path(
        os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
    state = Path(state_root) if state_root is not None else effective_home / "state"
    evidence = Path(evidence_root) if evidence_root is not None else state / "artifacts"
    try:
        owner_ref = load_or_create_owner_ref(effective_home)
        if args.surface == "grant":
            route = ("approve-once" if args.grant_action == "approve-once"
                     else f"prepare/{args.action}")
            result, status = grant_post(
                f"/api/grants/{route}", canonical_bytes(request), owner_ref=owner_ref,
                state_root=state, evidence_root=evidence, clock=effective_clock)
            action = route
        else:
            result, status = journey_post(
                f"/api/journeys/{args.action}", canonical_bytes(request),
                owner_ref=owner_ref, state_root=state,
                evidence_root=evidence, clock=effective_clock)
            action = args.action
    except (OSError, PermissionError, TypeError, ValueError):
        result, status, action = ({"schema": ERROR_SCHEMA, "error": {
            "code": "STORE_COMMIT_FAILED", "message": "local custody is unavailable"}},
            500, "")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return result_exit(result, http_status=status, action=action)


if __name__ == "__main__":
    raise SystemExit(main())
