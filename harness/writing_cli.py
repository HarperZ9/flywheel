"""Packaged JSON CLI for the private Writing Workspace workflow."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .evidence_cli import result_exit
from .evidence_public import ERROR_SCHEMA
from .writing_service import WritingError, WritingService


class _ArgumentFailure(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise _ArgumentFailure()


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="flywheel writing")
    sub = parser.add_subparsers(dest="action", required=True, parser_class=_Parser)
    status = sub.add_parser("status"); status.add_argument("--json", action="store_true")
    doctor = sub.add_parser("doctor"); doctor.add_argument("--json", action="store_true")
    init = sub.add_parser("init"); _prepare(init)
    init.add_argument("--brief", required=True); init.add_argument("--source-packet", required=True)
    proposal = sub.add_parser("proposal")
    proposals = proposal.add_subparsers(dest="proposal_action", required=True, parser_class=_Parser)
    approve = proposals.add_parser("approve"); approve.add_argument("proposal_ref"); approve.add_argument("--json", action="store_true")
    get = proposals.add_parser("get"); get.add_argument("proposal_ref"); get.add_argument("--json", action="store_true")
    commit = proposals.add_parser("commit"); commit.add_argument("proposal_ref")
    commit.add_argument("--grant", required=True); commit.add_argument("--json", action="store_true")
    section = sub.add_parser("section"); sections = section.add_subparsers(dest="section_action", required=True, parser_class=_Parser)
    add = sections.add_parser("add"); _journey(add); add.add_argument("--section-json", required=True)
    revision = sub.add_parser("revision"); revisions = revision.add_subparsers(dest="revision_action", required=True, parser_class=_Parser)
    rec = revisions.add_parser("record"); _journey(rec); rec.add_argument("--project", required=True); rec.add_argument("--section", required=True); rec.add_argument("--body", required=True)
    diagnose = sub.add_parser("diagnose"); _journey(diagnose)
    diagnose.add_argument("--project", required=True); diagnose.add_argument("--revision", required=True)
    card = sub.add_parser("card"); cards = card.add_subparsers(dest="card_action", required=True, parser_class=_Parser)
    card_rec = cards.add_parser("record"); _journey(card_rec); card_rec.add_argument("--card-json", required=True)
    cand = sub.add_parser("candidate"); cands = cand.add_subparsers(dest="candidate_action", required=True, parser_class=_Parser)
    cand_rec = cands.add_parser("record"); _journey(cand_rec); cand_rec.add_argument("--project", required=True); cand_rec.add_argument("--card", required=True); cand_rec.add_argument("--body", required=True)
    decision = sub.add_parser("decision"); decisions = decision.add_subparsers(dest="decision_action", required=True, parser_class=_Parser)
    dec_rec = decisions.add_parser("record"); _journey(dec_rec); dec_rec.add_argument("--project", required=True); dec_rec.add_argument("--decision", required=True, choices=("accept", "reject", "supersede", "rollback")); dec_rec.add_argument("--candidate"); dec_rec.add_argument("--section"); dec_rec.add_argument("--to-revision"); dec_rec.add_argument("--reason")
    review = sub.add_parser("review"); _journey(review); review.add_argument("--project", required=True)
    export = sub.add_parser("export"); _journey(export); export.add_argument("--project", required=True); export.add_argument("--out-ref", required=True)
    return parser


def _prepare(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--client-request-id", required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--json", action="store_true")


def _journey(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--journey-ref", required=True)
    parser.add_argument("--expected-event-head", required=True)
    _prepare(parser)


def _load_json(path: str) -> dict:
    value = Path(path)
    if not value.is_file() or value.stat().st_size > 262_144:
        raise WritingError("INPUT_UNAVAILABLE")
    return json.loads(value.read_text(encoding="utf-8"))


def _load_text(path_or_text: str) -> str | bytes:
    value = Path(path_or_text)
    if value.is_file():
        if value.stat().st_size > 262_144:
            raise WritingError("INPUT_UNAVAILABLE")
        return value.read_bytes()
    return path_or_text


def _dispatch(args: argparse.Namespace, service: WritingService) -> dict:
    if args.action == "status": return service.status()
    if args.action == "doctor": return service.doctor()
    if args.action == "init":
        return service.prepare_init(Path(args.brief), Path(args.source_packet),
                                    client_request_id=args.client_request_id)
    if args.action == "proposal" and args.proposal_action == "approve":
        return service.approve_proposal(args.proposal_ref)
    if args.action == "proposal" and args.proposal_action == "get":
        return service.proposal_get(args.proposal_ref)
    if args.action == "proposal" and args.proposal_action == "commit":
        return service.commit_proposal(args.proposal_ref, args.grant)
    if args.action == "section":
        return service.prepare_section(args.journey_ref, args.expected_event_head,
                                       _load_json(args.section_json),
                                       client_request_id=args.client_request_id)
    if args.action == "revision":
        return service.prepare_revision(args.journey_ref, args.expected_event_head,
            args.project, args.section, _load_text(args.body),
            client_request_id=args.client_request_id)
    if args.action == "diagnose":
        return service.prepare_diagnose(
            args.journey_ref, args.expected_event_head, args.project,
            args.revision, client_request_id=args.client_request_id)
    if args.action == "card":
        return service.prepare_card(args.journey_ref, args.expected_event_head,
                                    _load_json(args.card_json),
                                    client_request_id=args.client_request_id)
    if args.action == "candidate":
        return service.prepare_candidate(args.journey_ref, args.expected_event_head,
            args.project, args.card, _load_text(args.body),
            client_request_id=args.client_request_id)
    if args.action == "decision":
        return service.prepare_decision(args.journey_ref, args.expected_event_head,
            args.project, decision=args.decision, candidate_ref=args.candidate,
            section_ref=args.section, to_revision_ref=args.to_revision,
            reason=args.reason, client_request_id=args.client_request_id)
    if args.action == "review":
        return service.prepare_review(args.journey_ref, args.expected_event_head,
                                      args.project, client_request_id=args.client_request_id)
    return service.prepare_export(args.journey_ref, args.expected_event_head,
                                  args.project, out_ref=args.out_ref,
                                  client_request_id=args.client_request_id)


def _argument_error() -> dict:
    return {"schema": ERROR_SCHEMA, "error": {
        "code": "INVALID_ARGUMENTS", "message": "writing command arguments are invalid"}}


def main(argv: list[str] | None = None, *, home: Path | None = None,
         clock=None) -> int:
    try:
        args = _parser().parse_args(argv)
        effective_home = Path(home) if home is not None else Path(
            os.environ.get("FLYWHEEL_HOME", str(Path.home() / ".flywheel")))
        result, status = _dispatch(args, WritingService(effective_home, clock=clock)), 200
    except (_ArgumentFailure, WritingError, OSError, ValueError, TypeError) as exc:
        result = (_argument_error() if isinstance(exc, _ArgumentFailure)
                  else {"schema": ERROR_SCHEMA, "error": {
                      "code": getattr(exc, "code", str(exc) or "WRITING_FAILED"),
                      "message": "writing workflow is unavailable"}})
        status = 400 if isinstance(exc, _ArgumentFailure) else 409
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return result_exit(result, http_status=status, action="writing")


if __name__ == "__main__":
    raise SystemExit(main())
