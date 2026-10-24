"""journey_packet_vocab.py -- the custody packet's schema ids and scope, per version.

A custody packet carries one scope list in its criterion, its receipt, its
manifest and its recheck result. Version 2 names that list `scope` and says
what the packet covers. Version 1 packets named it with the older key and
phrased each entry as a limit; their bytes stay as written, so the verifier
reads each version with its own vocabulary, chosen by the manifest schema.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scope import LEGACY_SCOPE_KEY, SCOPE_KEY

SCOPE = (
    "CUSTODY_STRUCTURE: the packet checks custody structure; each claim is "
    "decided by its own check.",
    "CARRIED_EVENTS: the packet covers the events it carries; evidence outside "
    "them has no record here.",
    "NO_EXECUTION: the packet performs no execution, contained or otherwise.",
    "UNSIGNED_PACKET: the packet is unsigned; its digests detect accidental "
    "change, and its author is the channel it came through.",
    "OFFLINE_RECHECK: the recheck runs offline and makes no provider or "
    "network call.",
    "TESTED_FILESYSTEM_BOUNDARIES: durability is covered within the tested "
    "filesystem boundaries.",
    "PRE_EXPORT_HEAD: the packet binds the pre-export head H0; the export "
    "binds the final head H1.",
    "LOCAL_CHECKER_VERSION: the recheck runs the local checker, named by its "
    "source digest.",
)

# The version 1 list, byte for byte, so version 1 packets still recheck.
SCOPE_V1 = (
    "NOT_PROVES_CLAIM_CORRECTNESS: custody structure does not decide any claim.",
    "NOT_PROVES_EVIDENCE_COMPLETENESS: carried events may omit relevant evidence.",
    "NOT_PROVES_EXECUTION_CONTAINMENT: this packet performs no contained execution.",
    "NOT_PROVES_ORIGIN_AUTHENTICITY: an unsigned packet has no authenticated author.",
    "NOT_PROVES_LIVE_PROVIDER_STATE: offline recheck makes no provider or network call.",
    "NOT_PROVES_DURABLE_FILESYSTEM: recheck does not prove durability outside tested boundaries.",
    "NOT_PROVES_FINAL_EXPORTED_HEAD: the packet binds pre-export H0, not final H1.",
    "NOT_PROVES_CROSS_VERSION_CHECKER_EQUIVALENCE: local checker versions may differ.",
)


@dataclass(frozen=True)
class Vocabulary:
    packet_schema: str
    manifest_schema: str
    receipt_schema: str
    scope_key: str
    scope: tuple


CURRENT = Vocabulary(
    packet_schema="flywheel.evidence-packet/v2",
    manifest_schema="flywheel.evidence-journey-custody-manifest/v2",
    receipt_schema="flywheel.evidence-journey-custody-receipt/v2",
    scope_key=SCOPE_KEY, scope=SCOPE)
V1 = Vocabulary(
    packet_schema="flywheel.evidence-packet/v1",
    manifest_schema="flywheel.evidence-journey-custody-manifest/v1",
    receipt_schema="flywheel.evidence-journey-custody-receipt/v1",
    scope_key=LEGACY_SCOPE_KEY, scope=SCOPE_V1)


def vocabulary_for(manifest_schema: object) -> Vocabulary:
    """The vocabulary a manifest schema names; the current one when unknown,
    so an unknown schema fails the manifest check rather than passing here."""
    return V1 if manifest_schema == V1.manifest_schema else CURRENT
