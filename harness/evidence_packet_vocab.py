"""evidence_packet_vocab.py -- an evidence packet's schema ids and scope, per version.

An evidence packet carries one scope list in criterion.json and the bundle and
packet lists together in manifest.json. Version 2 names those lists `scope`
and says what the packet covers. Version 1 packets named them with the older
key and phrased each entry as a limit; their bytes stay as written, so the
verifier reads each version with its own vocabulary, chosen by the criterion
schema.
"""
from __future__ import annotations

from dataclasses import dataclass

from .bundle import SCHEMA as BUNDLE_SCHEMA, SCHEMA_V1 as BUNDLE_SCHEMA_V1
from .bundle import SCOPE as BUNDLE_SCOPE
from .runtime_descriptor import PYTHON_LIMITS
from .scope import LEGACY_SCOPE_KEY, SCOPE_KEY

SCHEMA_V1 = "flywheel.evidence-packet/v1"
SCHEMA = "flywheel.evidence-packet/v2"

SCOPE = (
    "CHECKER_SOURCE_CARRIED: the checker source ships in the packet for a "
    "reader to inspect; whether it implements the intended predicate is that "
    "reader's review.",
    "PACKED_EVIDENCE_BOUND: the carried artifacts are exactly what was packed; "
    "evidence left out before packing has no record here.",
    "OFFLINE_RECHECK: the recheck runs offline and makes no provider or "
    "network call.",
    "UNSIGNED_PACKET: the packet is unsigned; its digests detect accidental "
    "change, and its author is the channel it came through.",
    "ANCHORED_REHASH_RESISTANCE: self-carried hashes resist a rehash once the "
    "manifest digest is anchored outside the packet.",
) + PYTHON_LIMITS

# The version 1 lists, byte for byte, so version 1 packets still recheck.
BUNDLE_SCOPE_V1 = (
    "NOT_PROVES_PUBLICATION_COMPLETENESS: this bundle shows what it contains and "
    "cannot show what was left out of it.",
    "NOT_PROVES_RECEIPT_CORRECTNESS: the manifest shows nothing was altered after "
    "packing. A bundle of forged receipts with intact hashes verifies structurally.",
    "NOT_PROVES_CHECKER_CORRECTNESS: the checker source ships so it can be read. "
    "That it was shipped is not evidence that it implements the right predicate.",
)
SCOPE_V1 = (
    "NOT_PROVES_CHECKER_CORRECTNESS: carried checker source can be inspected but its "
    "presence does not prove that it implements the intended predicate.",
    "NOT_PROVES_EVIDENCE_COMPLETENESS: carried artifacts prove what was packed, not "
    "that no relevant evidence was omitted before packing.",
    "NOT_PROVES_LIVE_PROVIDER_STATE: offline recheck makes no provider or network call.",
    "NOT_PROVES_ORIGIN_AUTHENTICITY: an unsigned packet has no authenticated author.",
    "NOT_PROVES_REHASH_RESISTANCE: self-carried hashes need an external manifest anchor.",
    "NOT_PROVES_FULL_RUNTIME_DEPENDENCY_CLOSURE: the descriptor binds Python "
    "identity, pytest Python sources, and declared requirements, not stdlib, "
    "native code, or transitive dependency sources.",
    "NOT_PROVES_CROSS_ENVIRONMENT_REPRODUCTION: matching descriptors are "
    "required; execution under a different runtime is not proved equivalent.",
    "NOT_PROVES_TRUSTWORTHY_PYTHON_PASS: arbitrary Python shares memory with "
    "its test process, so a positive child result is not independent acceptance.",
    "NOT_PROVES_CLOSED_EXECUTION_DEPENDENCIES: admitted sources and the described "
    "runtime are bound, but external reads are not independently observable.",
)


@dataclass(frozen=True)
class Vocabulary:
    schema: str
    bundle_schema: str
    scope_key: str
    scope: tuple
    bundle_scope: tuple

    def manifest_scope(self) -> list[str]:
        return list(self.bundle_scope) + list(self.scope)


CURRENT = Vocabulary(SCHEMA, BUNDLE_SCHEMA, SCOPE_KEY, SCOPE, tuple(BUNDLE_SCOPE))
V1 = Vocabulary(SCHEMA_V1, BUNDLE_SCHEMA_V1, LEGACY_SCOPE_KEY, SCOPE_V1, BUNDLE_SCOPE_V1)


def vocabulary_for(schema: object) -> Vocabulary | None:
    """The vocabulary a criterion schema names, or None for an unknown schema."""
    return {SCHEMA: CURRENT, SCHEMA_V1: V1}.get(schema)
