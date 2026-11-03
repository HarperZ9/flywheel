"""harness.spine -- the shared contract every tool's receipt can be written in.

One verdict vocabulary (`vocab`), one hash-chained record (`record`, built on
`harness.hash_chain` and canonical-record/1), optional cause-and-effect fields
(`cause`), and one offline verifier (`verify`). Standard library only. The text
of record is docs/spec/spine-record.md.
"""
from __future__ import annotations

from .cause import check_cause
from .record import (SCHEMA, SCHEMA_VERSION, chain_intact, link, make_record,
                     seal)
from .verify import Recheck, from_native, verify_chain, verify_record
from .vocab import VOCABULARIES, fold, to_spine

__all__ = ["SCHEMA", "SCHEMA_VERSION", "VOCABULARIES", "Recheck", "chain_intact",
           "check_cause", "fold", "from_native", "link", "make_record", "seal",
           "to_spine", "verify_chain", "verify_record"]
