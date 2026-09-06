"""hash_chain.py -- one append-only chain, shared by every record family here.

A record cites the digest of the record before it. Deleting one breaks the
citation at the record after it, rewriting one breaks its own digest, and
reordering breaks both. That is the whole mechanism, and it is the only reason
a count read off a file an operator can edit is worth anything.

The walk lives here because it was about to live in two modules. A rule with
two implementations is a rule that gets repaired in one of them, and the
half-repaired copy keeps returning True. Families differ only in their schema
string and the name of the field holding the digest, so both are parameters
rather than a second copy.

Sealing excludes the digest field from its own input. Including it would make
the value depend on itself, and the only way to satisfy that is to not check.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_sha256

PREV_KEY = "prev_sha256"


def seal(record: dict, *, digest_key: str) -> dict:
    """Return the record with its digest field set over everything else."""
    body = {k: v for k, v in record.items() if k != digest_key}
    return dict(record, **{digest_key: canonical_sha256(body)})


def chain_intact(records, *, schema: str, digest_key: str,
                 prev_key: str = PREV_KEY) -> bool:
    """Walk a chain and check every citation. False on any tampering.

    A record of the wrong schema fails too. A file holding a mix of families
    is not a chain of either one, and answering True for the prefix would let
    an appended foreign record hide behind a verdict about its neighbours.
    """
    previous = ""
    for record in records:
        if not isinstance(record, dict) or record.get("schema") != schema:
            return False
        if record.get(prev_key, "") != previous:
            return False
        if record.get(digest_key) != seal(record, digest_key=digest_key)[
                digest_key]:
            return False
        previous = record[digest_key]
    return True


def load_chain(path) -> list:
    """Read a chain file. A missing or non-list file reads as no records."""
    path = Path(path)
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return rows if isinstance(rows, list) else []


def head_digest(records, *, digest_key: str) -> str:
    """The digest the next record must cite, empty when the chain is empty."""
    return records[-1][digest_key] if records else ""


def append_sealed(record: dict, *, path, schema: str, digest_key: str,
                  prev_key: str = PREV_KEY) -> list:
    """Append and refuse to write a chain that does not verify.

    Checking after the append rather than before is deliberate. The thing
    worth refusing is a bad file on disk, and the appended list is the only
    thing that would become that file.
    """
    records = load_chain(path) + [record]
    if not chain_intact(records, schema=schema, digest_key=digest_key,
                        prev_key=prev_key):
        raise ValueError("appending this record would break the chain")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True),
                    encoding="utf-8")
    return records
