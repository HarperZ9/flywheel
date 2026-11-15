"""The reconcile -- the project's single universal operation (the spine).

Perceive any artifact into a witnessed form, judge that form against a criterion it
did NOT author, and carry a re-checkable Certificate; UNVERIFIABLE when you can't.
Trust no assertion -- only the witness. Every surface (correctness, accountability,
security, creativity, the author) is one (perceive, criterion) binding of this loop;
the shipped verifier organs are its first instances. Naming the loop makes a new
surface a registration, not a rebuild. Generic by design: depends only on the
Certificate + Observation contracts, never on a specific oracle."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .certificate import Certificate, Verdict
from .observation import Observation, Provenance, Status, sha256_hex


# --- SPEC: making "a criterion it did NOT author" WITNESSABLE (additive) -------------
# The reconcile's central claim is judgement "against a criterion it did NOT author".
# Until now that independence was asserted by discipline and UNVERIFIED by the system's
# own standard: a Criterion carried no provenance and reconcile() never recorded who
# produced the artifact, so a SELF-graded reconcile (the judge's author == the
# artifact's producer) was byte-indistinguishable from an independent one. This makes
# the property a recorded, checkable WITNESS rather than a hope:
#   * Criterion may OPTIONALLY carry an `author` provenance id (who wrote the judge).
#   * reconcile() may OPTIONALLY accept a `producer` id (who produced the artifact).
#   * reconcile() records both and computes an `independence` field on the Observation:
#       - "witnessed-independent": both present AND differ (author != producer).
#       - "self-authored":         both present AND equal (author == producer).
#       - "unwitnessed":           either absent -- THE DEFAULT.
# DEFAULT-PRESERVING: when independence is "unwitnessed" the author/producer ids are NOT
# written into `data`, so every existing call is byte-for-byte unchanged in content (it
# only gains the honest annotation independence="unwitnessed"); two reconciles that
# differ ONLY in an un-witnessed author/producer are byte-identical, exactly as before.
# STRICT MODE (opt-in, default OFF): when enabled, a DECIDED verdict (VERIFIED/REFUTED)
# carried by a `self-authored` criterion is DOWNGRADED to UNVERIFIABLE -- the system now
# refuses to launder a self-graded decision as a witnessed one. Default mode leaves
# every verdict EXACTLY as today and only adds the `independence` annotation.
# Soundness over completeness: the absence of a witness is "unwitnessed" (honest),
# never silently "independent".
# -------------------------------------------------------------------------------------

# Sentinel reason emitted when strict mode refuses a self-graded decision.
_SELF_AUTHORED_DOWNGRADE_REASON = "verdict from a self-authored criterion (independence not witnessed)"
# Sentinel reason emitted when require_independent refuses an un-witnessed decision (A4):
# the criterion's independence was never witnessed, so a decision rests on no external check.
_UNWITNESSED_DOWNGRADE_REASON = "verdict from a criterion of unwitnessed independence (no external criterion)"


def witness_independence(author, producer) -> str:
    """Resolve (criterion author, artifact producer) to the independence tri-state.

    "witnessed-independent" iff BOTH are present and DIFFER; "self-authored" iff both
    present and equal; "unwitnessed" iff either is absent (the default -- an unsupplied
    witness is honestly unknown, never assumed independent). Pure + deterministic."""
    if author is None or producer is None:
        return "unwitnessed"
    return "self-authored" if author == producer else "witnessed-independent"


@dataclass(frozen=True)
class Criterion:
    """A named, independent judge: a perceived form -> a Certificate. The 'criterion it
    did not author' is the anti-hallucination heart of the reconcile.

    `author` is an OPTIONAL provenance id naming who wrote this judge. It defaults to
    None (unwitnessed), so existing Criterion(name, judge) call sites are unchanged. When
    set, reconcile() can witness it against the artifact's producer to mark independence
    (see witness_independence / reconcile's `independence` annotation)."""

    name: str
    judge: Callable[[Any], Certificate]
    author: str | None = None


def identity_perceive(artifact):
    """The fused case: the artifact already IS its own perceived form (e.g. a logical
    claim or a structured object). Returns (form, witnessed-bytes). The witness is
    repr(artifact); for re-derivability the artifact's repr must be value-stable (it is
    for the frozen AST nodes / dataclasses this is used on -- not for objects whose repr
    embeds a memory address)."""
    return artifact, repr(artifact).encode()


def _safe_str(x) -> str:
    try:
        return str(x)
    except Exception:
        return "<unrepresentable>"


def reconcile(artifact, *, perceive=identity_perceive, criterion, producer=None,
              strict=False, require_independent=False) -> Observation:
    """Perceive -> judge -> witness, as ONE witnessed Observation carrying the verdict.

    perceive(artifact) -> (form, payload_bytes); criterion.judge(form) -> Certificate.
    Fail-closed: ANY exception (perceive, judge, or constructing the witnessed result
    from a malformed Certificate) yields an UNVERIFIABLE Observation; reconcile never
    raises and never alters a verdict -- it is a faithful wrapper (the recorded verdict
    is always the criterion's own, passed through).

    `producer` (optional) is the provenance id of whoever produced the artifact. Together
    with criterion.author it lets reconcile WITNESS the spine's "criterion it did not
    author" claim: the emitted Observation carries an `independence` field
    (witnessed-independent / self-authored / unwitnessed -- see witness_independence).
    When BOTH ids are absent (the default) independence is "unwitnessed" and the ids are
    NOT recorded, so existing calls are byte-for-byte unchanged in content.

    `strict` (optional, default OFF -- so existing tests are untouched): when True, a
    DECIDED verdict (VERIFIED/REFUTED) carried by a `self-authored` criterion is
    DOWNGRADED to UNVERIFIABLE (reason: independence not witnessed). Default mode leaves
    every verdict EXACTLY as today and only annotates `independence`.

    `require_independent` (optional, default OFF): the STRONGER guard (aperture-sim A4 --
    internal confidence is not truth; a decision must rest on a criterion whose external
    independence is POSITIVELY witnessed). When True, a DECIDED verdict is downgraded to
    UNVERIFIABLE unless independence == "witnessed-independent" -- i.e. BOTH self-authored
    AND unwitnessed decisions are refused (strict only refuses self-authored). Use this at
    a real trust boundary where the mere ABSENCE of a witnessed external criterion must not
    be laundered into VERIFIED. Default OFF leaves every verdict exactly as today."""
    label = f"reconcile:{criterion.name}"
    independence = witness_independence(getattr(criterion, "author", None), producer)
    try:
        form, payload = perceive(artifact)
        cert = criterion.judge(form)
        # ALL post-judge construction stays inside the try: a malformed Certificate from
        # an untrusted criterion must degrade to UNVERIFIABLE, never raise (fail-closed).
        decided = cert.verdict in (Verdict.VERIFIED, Verdict.REFUTED)
        verdict_value = cert.verdict.value
        downgrade_reason = None
        # STRICT: refuse to launder a self-graded decision as a witnessed one. Only a
        # DECIDED verdict on a self-authored criterion is touched; default mode (strict
        # False) and every other independence value pass the criterion's verdict through.
        if strict and decided and independence == "self-authored":
            verdict_value = Verdict.UNVERIFIABLE.value
            decided = False
            downgrade_reason = _SELF_AUTHORED_DOWNGRADE_REASON
        # REQUIRE_INDEPENDENT (A4): stronger than strict -- a decision must rest on a
        # POSITIVELY witnessed-independent criterion; both self-authored and unwitnessed
        # are refused (the absence of an external witness is not truth). The elif means a
        # self-authored case already handled by `strict` keeps its specific reason.
        elif require_independent and decided and independence != "witnessed-independent":
            verdict_value = Verdict.UNVERIFIABLE.value
            decided = False
            downgrade_reason = (_SELF_AUTHORED_DOWNGRADE_REASON if independence == "self-authored"
                                else _UNWITNESSED_DOWNGRADE_REASON)
        downgraded = downgrade_reason is not None
        payload = bytes(payload) if isinstance(payload, (bytes, bytearray)) else str(payload).encode()
        claim = cert.claim if isinstance(cert.claim, str) else str(cert.claim)
        data = {"oracle": cert.oracle, "verdict": verdict_value, "claim": claim,
                "criterion": criterion.name, "evidence": [list(p) for p in cert.evidence],
                "identity_sha256": sha256_hex(claim.encode()), "independence": independence}
        # Only record the witnessing ids when independence is actually witnessed -- this
        # keeps the default ("unwitnessed") Observation byte-identical to the legacy one
        # and makes two un-witnessed reconciles indistinguishable, as before.
        if independence != "unwitnessed":
            data["criterion_author"] = getattr(criterion, "author", None)
            data["artifact_producer"] = producer
        if downgraded:
            data["downgrade_reason"] = downgrade_reason
        return Observation(
            label, claim, f"reconcile {verdict_value}",
            Status.PASS if decided else Status.UNVERIFIED,
            Provenance.witness_bytes(claim, payload, "high" if decided else "low"),
            data,
        )
    except Exception as exc:
        # A criterion-UNVERIFIABLE (a real verdict) and this exception-UNVERIFIABLE both
        # collapse to Status.UNVERIFIED by design (both mean "no decision"); the exception
        # path is distinguishable by its "reason" key and the absent oracle/evidence.
        subject = _safe_str(artifact)
        data = {"verdict": "unverifiable", "criterion": criterion.name, "reason": repr(exc),
                "independence": independence}
        if independence != "unwitnessed":
            data["criterion_author"] = getattr(criterion, "author", None)
            data["artifact_producer"] = producer
        return Observation(
            label, subject, "reconcile unverifiable", Status.UNVERIFIED,
            Provenance.witness_bytes(subject, b"", "low"),
            data,
        )
