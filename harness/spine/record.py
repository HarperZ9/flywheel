"""record.py -- the spine record: one hash-chained receipt shape for every tool.

A spine record wraps a tool's own receipt (the payload) and states, in fields
every tool shares, what that receipt decided. The chain walk and the seal are
`harness.hash_chain`, the walk Flywheel's scheduler, scan and browser records
already share. This module adds no chain code of its own. It passes
`canonical_record.sha256` as the byte form, because effect and interval fields
are floats and canonical-record/1 is the form other languages can reproduce.

Fields (docs/spec/spine-record.md is the text of record):

  schema             "flywheel.spine-record/1"
  schema_version     1
  canonical_form     "canonical-record/1"
  tool               the producing tool ("emet", "crucible", "gather", ...)
  source_schema      the payload's own schema id
  source_vocabulary  one of spine.vocab.VOCABULARIES
  source_verdict     the payload's verdict term in that vocabulary
  verdict            the spine verdict, which must equal the mapped term
  scope              what the verdict covers, in positive words
  payload_sha256     canonical-record/1 digest of the payload
  payload            the tool's receipt, embedded (optional; needed to recheck)
  cause              cause-and-effect fields (optional; spine.cause)
  prev_sha256        record_sha256 of the record before, "" for the first
  record_sha256      seal over every other field
"""
from __future__ import annotations

from .. import canonical_record, hash_chain
from .vocab import to_spine

SCHEMA = "flywheel.spine-record/1"
SCHEMA_VERSION = 1
CANONICAL_FORM = canonical_record.SPEC
DIGEST_KEY = "record_sha256"
PREV_KEY = hash_chain.PREV_KEY

REQUIRED = ("schema", "schema_version", "canonical_form", "tool",
            "source_schema", "source_vocabulary", "source_verdict", "verdict",
            "scope", "payload_sha256", PREV_KEY, DIGEST_KEY)


def digest(value) -> str:
    """canonical-record/1 sha256 of a JSON value."""
    return canonical_record.sha256(value)


def seal(record: dict) -> dict:
    """Return the record with record_sha256 set over every other field."""
    return hash_chain.seal(record, digest_key=DIGEST_KEY, digest=digest)


def make_record(*, tool: str, source_schema: str, source_vocabulary: str,
                source_verdict: str, payload: dict, scope: str,
                cause: dict | None = None, embed: bool = True,
                prev_sha256: str = "") -> dict:
    """Build and seal one spine record. The spine verdict is derived from the
    source term, never passed in, so a writer cannot state a mismatched pair."""
    record = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "canonical_form": CANONICAL_FORM,
        "tool": tool,
        "source_schema": source_schema,
        "source_vocabulary": source_vocabulary,
        "source_verdict": source_verdict,
        "verdict": to_spine(source_vocabulary, source_verdict).value,
        "scope": scope,
        "payload_sha256": digest(payload),
        PREV_KEY: prev_sha256,
    }
    if embed:
        record["payload"] = payload
    if cause is not None:
        record["cause"] = cause
    return seal(record)


def link(records: list[dict]) -> list[dict]:
    """Re-cite and re-seal records in order, so each cites the one before."""
    out: list[dict] = []
    for record in records:
        body = {k: v for k, v in record.items() if k != DIGEST_KEY}
        body[PREV_KEY] = out[-1][DIGEST_KEY] if out else ""
        out.append(seal(body))
    return out


def chain_intact(records) -> bool:
    """Every citation and every seal holds, under canonical-record/1."""
    return hash_chain.chain_intact(records, schema=SCHEMA,
                                   digest_key=DIGEST_KEY, digest=digest)


def append(record: dict, path) -> list:
    """Append to a chain file, refusing to write a chain that does not verify."""
    return hash_chain.append_sealed(record, path=path, schema=SCHEMA,
                                    digest_key=DIGEST_KEY, digest=digest)
