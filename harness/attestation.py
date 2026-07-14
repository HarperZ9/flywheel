"""attestation.py -- ownership made checkable.

The essay's requirement, executable: a person who presents machine work as
their own should be able to prove the review behind the claim. An
attestation binds a sign-off to the run's ledger checkpoint and to exactly
what the reviewer walked:

- coverage    reviewed edited-files over all edited files -- you cannot
              attest to more than you saw, and what you skipped is listed;
- overclaimed files named in the sign-off that the run never edited,
              flagged instead of silently counted;
- sha256      the whole attestation is content-addressed, so a doctored
              one stops matching its own hash.

"I own this" becomes a checkable statement. Standing is `complete` only at
full coverage; anything less is honestly `partial`.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA = "flywheel.attestation/v1"


def attest(run: dict, reviewed_files: list, *, note: str = "",
           reviewer: str = "") -> dict:
    """Build the attestation for `run` (an agent-run doc carrying `review`
    and `checkpoint`). Pure and deterministic: same inputs, same hash."""
    review = run.get("review") or {}
    edited = sorted(review.get("files_edited") or [])
    claimed = sorted(set(str(f) for f in reviewed_files))
    reviewed = sorted(set(claimed) & set(edited))
    overclaimed = sorted(set(claimed) - set(edited))
    # a run that edited nothing has nothing to attest: coverage is None
    # and standing is 'empty', never a vacuous 'complete' that would
    # confer holdership downstream
    coverage = round(len(reviewed) / len(edited), 4) if edited else None
    if coverage is None:
        standing = "empty"
    elif coverage == 1.0 and not overclaimed:
        standing = "complete"
    else:
        standing = "partial"
    doc = {
        "schema": SCHEMA,
        "checkpoint": str(run.get("checkpoint", "")),
        "review_sha256": hashlib.sha256(
            json.dumps(review, sort_keys=True).encode("utf-8")).hexdigest(),
        "reviewer": reviewer,
        "note": note,
        "reviewed": reviewed,
        "unreviewed": sorted(set(edited) - set(reviewed)),
        "overclaimed": overclaimed,
        "coverage": coverage,
        "standing": standing,
    }
    doc["sha256"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True).encode("utf-8")).hexdigest()
    return doc
