"""Native composition of the gather, chorus, and crucible lanes into one
claim-verification pipeline that emits a re-derivable bundle receipt.

This is the peer-composition rule made concrete inside Flywheel: each tool is a
lane that stands alone (see harness/lanes_registry.py), and here they compose
through their published JSON seams, not their internals.

  1. gather   -> a witnessed digest of the evidence (provenance per receipt, sealed).
  2. chorus   -> a deterministic reading of the same corpus (themes, dissent, receipt).
  3. crucible -> MATCH / DRIFT / UNVERIFIABLE on a falsifiable claim about the evidence,
                 recomputed from the record via GatherDigestMeasure, no model in the verdict.
  4. bundle   -> one receipt binding all three stage fingerprints, re-derivable.

Boundary held (tool-positioning accuracy): the bundle attests that these stages ran
over this evidence and reproduce these fingerprints. It does not prove the claim is
true of the world, nor that the corpus is representative. crucible additionally
requires a falsification condition on the claim, so an untestable claim is
UNVERIFIABLE by design.

The three tools are peer lanes; import failures degrade to a clear error rather than a
silent partial result.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict


class CompositionUnavailable(RuntimeError):
    """A peer lane could not be imported. The composition fails closed, loud."""


def _import_peers():
    try:
        from gather.item import make_item
        from gather.digest import digest as gather_digest
        from chorus.item import normalize
        from chorus.sentiment import score
        from chorus.synthesize import synthesize
        from crucible.claim import make_claim
        from crucible.verdict import verdict_for
        from crucible.ecosystem_measure import GatherDigestMeasure, verify_gather_digest
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise CompositionUnavailable(
            "compose_claim needs the gather, chorus, and crucible lanes importable "
            f"(pip install the lanes or add their src to the path): {exc}"
        ) from exc
    return {
        "make_item": make_item, "gather_digest": gather_digest, "normalize": normalize,
        "score": score, "synthesize": synthesize, "make_claim": make_claim,
        "verdict_for": verdict_for, "GatherDigestMeasure": GatherDigestMeasure,
        "verify_gather_digest": verify_gather_digest,
    }


def _sha(obj: object) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class Bundle:
    gather_seal: str
    gather_ok: bool
    gather_receipts: int
    chorus_digest_sha: str
    chorus_verifies: bool
    chorus_themes: int
    verdict_status: str
    verdict_deviation: float | None
    bundle_sha: str


def run_claim_verification(rows, claim_text, selector, *, falsification=None,
                           tolerance=1.0, clock=lambda: 0.0) -> Bundle:
    """Run the composed pipeline over `rows` (a shared corpus of catalog-style rows).

    rows: list of dicts (kind/id/ref/text/meta, plus optional source/method/fetched_at).
    claim_text: a falsifiable claim about what the gathered evidence contains.
    selector: gather receipt fields the claim asserts are present (kind/id/title/source/
              ref/method/sha256, and optional derived_from).
    falsification: the condition that would make the claim false. crucible treats a claim
                   with no falsification condition as UNVERIFIABLE by design, so a default
                   is supplied when none is given.
    """
    p = _import_peers()

    # 1. gather: rows -> Items -> a witnessed digest (dict form for the seam).
    items = [p["make_item"](
        kind=r.get("kind", "comment"), id=str(r.get("id", "")),
        title=str(r.get("title", "")), text=str(r.get("text", "")),
        source=str(r.get("source", "synthetic")), ref=str(r.get("ref", "")),
        method=str(r.get("method", "synthetic")), fetched_at=float(r.get("fetched_at", 0.0)),
        meta=r.get("meta") or {}) for r in rows]
    gd = p["gather_digest"](items)
    gjson = {"receipts": [dict(rc) for rc in gd.receipts], "seal": gd.seal}
    gcheck = p["verify_gather_digest"](gjson)

    # 2. chorus: the same corpus -> a re-derivable reading; re-derive to confirm.
    cdigest = p["synthesize"](p["score"](p["normalize"](rows)))
    again = p["synthesize"](p["score"](p["normalize"](rows)))
    cverifies = again.receipt.digest_sha256 == cdigest.receipt.digest_sha256

    # 3. crucible: adjudicate the claim against the gather digest.
    claim = p["make_claim"](
        claim_text,
        falsification or "the verified gather digest contains no receipt matching the selector",
        tolerance=tolerance)
    measure = p["GatherDigestMeasure"]({"run": gjson}, {claim.id: selector}, clock=clock)
    measurement = measure.measure(claim)
    verdict = p["verdict_for"](claim, measurement)

    # 4. bundle: bind the three stage fingerprints into one re-derivable receipt.
    body = {
        "gather_seal": gjson["seal"],
        "chorus_digest_sha": cdigest.receipt.digest_sha256,
        "verdict_status": verdict.status,
        "claim": claim_text,
    }
    return Bundle(
        gather_seal=gjson["seal"], gather_ok=bool(gcheck.get("matches")),
        gather_receipts=len(gjson["receipts"]),
        chorus_digest_sha=cdigest.receipt.digest_sha256, chorus_verifies=cverifies,
        chorus_themes=len(cdigest.themes),
        verdict_status=verdict.status,
        verdict_deviation=getattr(measurement, "deviation", None),
        bundle_sha=_sha(body))


def bundle_json(b: Bundle) -> str:
    return json.dumps(asdict(b), indent=2, ensure_ascii=False)
