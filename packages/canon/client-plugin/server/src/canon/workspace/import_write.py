"""import_write.py -- turn an importer's candidates into proposed rows and a report.

This is the one path from a transcript to the store. It runs the project check
and the undeclared-loss check before anything is written, scrubs every
candidate, builds each record through the same validating builder the CLI uses,
and writes it as a proposed row whose origin names the source file, its digest,
the line and the rule. A proposal already accepted with the same content, or
rejected before with the same content, is reported and not written again.
"""
from __future__ import annotations

import hashlib
import shlex

from canon.schema import Record
from canon.workspace import authoring
from canon.workspace.identity import ProjectIdentity
from canon.workspace.import_common import (
    DOES_NOT_PROVE,
    REPORT_SCHEMA,
    Extraction,
    ImportRefused,
    Source,
    bare_label,
    proposal_id,
    project_check,
    read_jsonl,
)
from canon.workspace.rows import STATE_ACCEPTED, STATE_PROPOSED
from canon.workspace.scrub import scrub_value
from canon.workspace.store import ProjectStore, record_digest


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _refuse_early(identity: ProjectIdentity, extraction: Extraction,
                  accept_foreign: bool) -> dict:
    check = project_check(identity, extraction)
    if check["status"] == "mismatch" and not accept_foreign:
        named = check.get("source_key", "another working directory")
        raise ImportRefused(
            "isolation_refused", f"the source belongs to {named}, not {identity.label}; "
            "pass --accept-foreign-source to import it into this project anyway")
    undeclared = extraction.ledger.undeclared
    if undeclared:
        where = "; ".join(f"{label} at lines {lines[:5]}"
                          for label, lines in sorted(undeclared.items()))
        flags = " ".join(sorted({f"--drop-type {shlex.quote(bare_label(label))}"
                                 for label in undeclared}))
        raise ImportRefused(
            "undeclared_loss", f"the importer does not know what it would drop: {where}. "
            f"To import without it, run the import again with {flags}")
    return check


def _record_id(importer: str, key: str, cand, index: int, source: Source,
               accepted: dict) -> str:
    """The proposal id, minted again with the source file in its key when an
    accepted record already holds the id but came from another file, so two
    sessions that share a session id never replace each other's records."""
    rid = proposal_id(importer, key, cand, index)
    prior = accepted.get(rid)
    native = prior.provenance.native_id if prior is not None else None
    if rid == authoring.FOCUS_ID or native is None or \
            native.startswith(f"{importer}:{source.name}:"):
        return rid
    return proposal_id(importer, f"{key}\n{source.name}", cand, index)


def build_proposals(store: ProjectStore, extraction: Extraction, source: Source, *,
                    importer: str) -> tuple[list[tuple[Record, dict]], dict[str, int]]:
    hits: dict[str, int] = dict(extraction.hits)
    key = extraction.session_id or source.name
    raw = {n: line for n, _obj, line in source.lines}
    slots: dict[tuple[int, str], int] = {}
    ordinal = store.next_ord()
    accepted, _ = seen_before(store)
    out: list[tuple[Record, dict]] = []
    for cand in extraction.candidates:
        index = slots.get((cand.line, cand.rule), 0)
        slots[(cand.line, cand.rule)] = index + 1
        data = scrub_value(cand.data, hits)
        try:
            record = authoring.build(
                cand.kind, _record_id(importer, key, cand, index, source, accepted), data,
                ordinal, harness=importer, source_hash=_sha(raw.get(cand.line, "")),
                native_id=f"{importer}:{source.name}:{cand.line}",
                session_id=extraction.session_id)
        except authoring.AuthoringError:
            extraction.ledger.drop("invalid-candidate")
            continue
        ordinal += 1
        origin = {"importer": importer, "source": source.name,
                  "source_sha256": source.sha256, "line": cand.line, "rule": cand.rule,
                  "content_sha256": authoring.content_hash(record.kind, record.data)}
        out.append((record, origin))
    return out, hits


def seen_before(store: ProjectStore) -> tuple[dict, set]:
    """The accepted records by id, and every rejection as (id, content digest,
    render). An import has no render (None); an edit read back from a region
    names the render it was read against, so rejecting it holds only until a
    later render stands and the same edit made again is proposed again."""
    accepted = {r.record.id: r.record for r in store.rows(STATE_ACCEPTED)}
    rejected = set()
    for entry in store.log_entries():
        origin = entry.get("origin") or {}
        if entry.get("action") == "reject" and origin.get("content_sha256"):
            rejected.add((entry["record_key"].split("/", 1)[1], origin["content_sha256"],
                          origin.get("base_render")))
    return accepted, rejected


def run_import(identity: ProjectIdentity, store: ProjectStore, extraction: Extraction,
               source: Source, *, importer: str, accept_foreign: bool = False,
               dry_run: bool = False) -> dict:
    """Check, scrub, propose, and report. Writes nothing when `dry_run`."""
    check = _refuse_early(identity, extraction, accept_foreign)
    proposals, hits = build_proposals(store, extraction, source, importer=importer)
    accepted, rejected = seen_before(store)
    written, already, previously = [], [], []
    for record, origin in proposals:
        entry = {"id": record.id, "kind": record.kind, "rule": origin["rule"],
                 "line": origin["line"]}
        if (record.id, origin["content_sha256"], None) in rejected:
            previously.append(entry)
            continue
        prior = accepted.get(record.id)
        if prior is not None and prior.data == record.data:
            already.append(entry)
            continue
        if not dry_run:
            base = {"base_record_sha256": record_digest(prior) if prior else None}
            store.put(record, state=STATE_PROPOSED, origin={**origin, **base},
                      action="import")
        written.append(entry)
    return _report(identity, extraction, source, importer, check, hits,
                   written, already, previously, dry_run)


def _report(identity, extraction, source, importer, check, hits, written, already,
            previously, dry_run) -> dict:
    ledger = extraction.ledger
    return {
        "schema": REPORT_SCHEMA,
        "importer": importer,
        "dry_run": dry_run,
        "source": {"name": source.name, "sha256": source.sha256,
                   "lines": source.line_count, "truncated_tail": source.truncated_tail},
        "project": identity.to_public(),
        "project_check": check,
        "proposed": written,
        "already_accepted": already,
        "previously_rejected": previously,
        "declared_drops": dict(sorted(ledger.counts.items())),
        "declared_drop_meanings": dict(sorted(ledger.declared.items())),
        "user_declared_drops": dict(sorted(ledger.user_counts.items())),
        "secrets_redacted": dict(sorted(hits.items())),
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def importers() -> dict:
    """The importers by source format name."""
    from canon.workspace import import_claude, import_codex
    return {import_claude.IMPORTER: import_claude, import_codex.IMPORTER: import_codex}


def import_session(identity: ProjectIdentity, store: ProjectStore, path: str, *,
                   source_format: str, accept_foreign: bool = False,
                   user_drops: tuple[str, ...] = (), dry_run: bool = False) -> dict:
    """Read one session file in `source_format` and propose records from it."""
    module = importers().get(source_format)
    if module is None:
        raise ImportRefused("invalid_args", f"unknown source format {source_format!r}; "
                                            f"expected one of {sorted(importers())}")
    source = read_jsonl(path)
    extraction = module.extract(source, identity, user_drops=frozenset(user_drops))
    return run_import(identity, store, extraction, source, importer=module.IMPORTER,
                      accept_foreign=accept_foreign, dry_run=dry_run)
