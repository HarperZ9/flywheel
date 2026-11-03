"""verify.py -- one offline verifier for spine records.

    python -m harness.spine verify RECORD_OR_CHAIN.json

A file holding one object is checked as a record; a list is checked as a
chain. Exit 0 PASS, 1 FAIL, 2 UNVERIFIABLE, 3 UNDECIDED. The verifier hashes,
compares and subtracts. It reaches no model, network or clock, so it stays
off-model under Flywheel's C2 rule and runs on a bare interpreter.

The recheck verdict answers "is this receipt intact and does its verdict follow
from what it carries". It is separate from the record's own verdict: an emet
receipt that honestly records DRIFT rechecks as PASS.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

from ..canonical_record import CanonicalError
from ..verdict import Verdict
from . import natives
from .cause import check_cause
from .record import (CANONICAL_FORM, DIGEST_KEY, REQUIRED, SCHEMA,
                     SCHEMA_VERSION, chain_intact, digest, make_record, seal)
from .vocab import VocabularyError, fold, to_spine


@dataclass(frozen=True)
class Recheck:
    verdict: Verdict
    record_verdict: str | None
    checks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"verdict": self.verdict.value,
                "record_verdict": self.record_verdict,
                "checks": [{"name": n, "verdict": v.value, "detail": d}
                           for n, v, d in self.checks]}


def from_native(source_schema: str, payload: dict, *, cause: dict | None = None,
                prev_sha256: str = "", embed: bool = True) -> dict:
    """Re-express one tool receipt as a spine record. The source verdict is
    derived from the payload by the tool's own rule, never supplied."""
    if source_schema not in natives.NATIVE:
        raise ValueError(f"no native adapter for {source_schema!r}")
    tool, vocabulary, _, scope = natives.NATIVE[source_schema]
    intact, term, detail = natives.recheck(source_schema, payload)
    if not intact:
        raise ValueError(f"{source_schema} payload does not recheck: {detail}")
    return make_record(tool=tool, source_schema=source_schema,
                       source_vocabulary=vocabulary, source_verdict=term,
                       payload=payload, scope=scope, cause=cause, embed=embed,
                       prev_sha256=prev_sha256)


def _shape(record, checks: list) -> bool:
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        checks.append(("shape", Verdict.UNVERIFIABLE, f"not a {SCHEMA} record"))
        return False
    version = record.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        checks.append(("shape", Verdict.UNVERIFIABLE, "schema_version missing"))
        return False
    if version > SCHEMA_VERSION:
        checks.append(("shape", Verdict.UNVERIFIABLE,
                       f"schema_version {version} is newer than this verifier "
                       f"({SCHEMA_VERSION})"))
        return False
    missing = [k for k in REQUIRED if k not in record]
    if missing or record["canonical_form"] != CANONICAL_FORM:
        checks.append(("shape", Verdict.UNVERIFIABLE,
                       f"missing {missing}" if missing
                       else f"canonical_form is not {CANONICAL_FORM}"))
        return False
    checks.append(("shape", Verdict.PASS, f"{SCHEMA} v{version}"))
    return True


def _seal_and_map(record, checks: list) -> None:
    sealed = seal({k: v for k, v in record.items() if k != DIGEST_KEY})
    checks.append(("seal", Verdict.PASS, "record_sha256 re-derives")
                  if sealed[DIGEST_KEY] == record[DIGEST_KEY] else
                  ("seal", Verdict.FAIL, "record_sha256 does not re-derive"))
    try:
        mapped = to_spine(record["source_vocabulary"], record["source_verdict"])
    except VocabularyError as exc:
        checks.append(("vocabulary", Verdict.UNVERIFIABLE, str(exc)))
        return
    checks.append(("vocabulary", Verdict.PASS,
                   f"{record['source_verdict']} maps to {mapped.value}")
                  if mapped.value == record["verdict"] else
                  ("vocabulary", Verdict.FAIL,
                   f"{record['source_verdict']} maps to {mapped.value}, the "
                   f"record says {record['verdict']}"))


def _payload(record, checks: list) -> None:
    if "payload" not in record:
        checks.append(("payload", Verdict.UNVERIFIABLE,
                       "payload not embedded; only the digest travels"))
        return
    payload = record["payload"]
    if digest(payload) != record["payload_sha256"]:
        checks.append(("payload", Verdict.FAIL, "payload_sha256 does not match"))
        return
    checks.append(("payload", Verdict.PASS, "payload_sha256 matches"))
    intact, term, detail = natives.recheck(record["source_schema"], payload)
    if intact is None:
        checks.append(("native", Verdict.UNVERIFIABLE, detail))
    elif not intact:
        checks.append(("native", Verdict.FAIL, detail))
    elif term != record["source_verdict"]:
        checks.append(("native", Verdict.FAIL,
                       f"payload yields {term}, the record says "
                       f"{record['source_verdict']}"))
    else:
        checks.append(("native", Verdict.PASS, detail))


def verify_record(record) -> Recheck:
    checks: list = []
    if not _shape(record, checks):
        return Recheck(fold(v for _, v, _ in checks), None, checks)
    try:
        _seal_and_map(record, checks)
        _payload(record, checks)
        checks.extend(check_cause(record.get("cause")))
    except CanonicalError as exc:
        checks.append(("canonical", Verdict.UNVERIFIABLE, str(exc)))
    return Recheck(fold(v for _, v, _ in checks), record.get("verdict"), checks)


def verify_chain(records) -> Recheck:
    if not isinstance(records, list) or not records:
        return Recheck(Verdict.UNVERIFIABLE, None,
                       [("chain", Verdict.UNVERIFIABLE, "empty or not a list")])
    try:
        intact = chain_intact(records)
    except CanonicalError as exc:
        return Recheck(Verdict.UNVERIFIABLE, None,
                       [("chain", Verdict.UNVERIFIABLE, str(exc))])
    checks = [("chain", Verdict.PASS, f"{len(records)} records, links intact")
              if intact else ("chain", Verdict.FAIL, "a citation or seal broke")]
    for i, record in enumerate(records):
        result = verify_record(record)
        checks.extend((f"record[{i}].{n}", v, d) for n, v, d in result.checks)
    return Recheck(fold(v for _, v, _ in checks), None, checks)


_EXIT = {Verdict.PASS: 0, Verdict.FAIL: 1, Verdict.UNVERIFIABLE: 2,
         Verdict.UNDECIDED: 3}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "verify":
        print("usage: python -m harness.spine verify FILE.json", file=sys.stderr)
        return 64
    try:
        with open(argv[1], encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"cannot read {argv[1]}: {exc}", file=sys.stderr)
        return 2
    result = verify_chain(data) if isinstance(data, list) else verify_record(data)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return _EXIT[result.verdict]
