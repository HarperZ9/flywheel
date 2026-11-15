#!/usr/bin/env python3
"""Experiment: witnessing "a criterion it did NOT author" closes a byte-level seam.

The reconcile's central claim is that an artifact is judged "against a criterion it did
NOT author". This experiment makes that claim CHECKABLE and shows the seam it closes:

  BEFORE (the seam):
    Run reconcile() on the SAME artifact with two criteria that judge identically -- one
    SELF-authored (its author == the artifact's producer) and one INDEPENDENT (author !=
    producer) -- but WITHOUT witnessing independence (no `producer` passed). The two
    emitted Observations are BYTE-IDENTICAL: self-grading is indistinguishable from
    independent grading. The anti-hallucination heart is asserted, UNVERIFIED.

  AFTER (the closure):
    Run the same two cases WITH independence witnessed (`producer` passed) and strict
    mode ON. The self-authored case is now marked `self-authored` and its DECIDED verdict
    downgrades to UNVERIFIABLE (independence not witnessed); the independent case is
    marked `witnessed-independent` and stays decided. The two are now distinguishable --
    the system witnesses its own central claim instead of asserting it.

Runnable, stdlib only, zero external dependency. Prints a compact BEFORE/AFTER table.
"""
from __future__ import annotations

import json

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.reconcile import Criterion, reconcile

# An artifact and a judge that DECIDES it (VERIFIED) -- the verdict content is identical
# across the self-authored and independent cases, so any difference between the two
# Observations can come ONLY from the independence witness, nothing else.
ARTIFACT = {"claim": "the artifact is well-formed", "value": 42}
PRODUCER = "org:model-A"            # who produced the artifact
SELF_AUTHOR = "org:model-A"         # a criterion authored by the SAME party (self-grading)
INDEP_AUTHOR = "org:auditor-B"      # a criterion authored by an INDEPENDENT party


def _perceive(d):
    """Deterministic perceive: stable form + stable witnessed bytes (no addresses)."""
    return d, json.dumps(d, sort_keys=True).encode()


def _judge(form) -> Certificate:
    """A decided judgement identical regardless of who authored the criterion."""
    return Certificate("the artifact is well-formed", Verdict.VERIFIED, "wellformed-v1")


def _self_authored_criterion() -> Criterion:
    return Criterion("wellformed", _judge, author=SELF_AUTHOR)


def _independent_criterion() -> Criterion:
    return Criterion("wellformed", _judge, author=INDEP_AUTHOR)


def _canonical_bytes(obs) -> bytes:
    """Serialise an Observation to canonical bytes for a byte-level comparison, with the
    one wall-clock field (provenance.timestamp) normalised -- it is never part of the
    verdict content, so excluding it isolates whether the WITNESSED content differs."""
    d = obs.to_dict()
    d["provenance"] = dict(d["provenance"])
    d["provenance"]["timestamp"] = "<normalized>"
    return json.dumps(d, sort_keys=True).encode()


def before() -> tuple[bytes, bytes]:
    """BEFORE: no independence witnessing (no `producer`). Returns the two canonical
    byte serialisations -- they are expected to be IDENTICAL (the seam)."""
    self_obs = reconcile(ARTIFACT, perceive=_perceive, criterion=_self_authored_criterion())
    indep_obs = reconcile(ARTIFACT, perceive=_perceive, criterion=_independent_criterion())
    return _canonical_bytes(self_obs), _canonical_bytes(indep_obs)


def after():
    """AFTER: independence witnessed (`producer` passed) + strict mode ON. Returns the
    two Observations -- now distinguishable, the self-authored decision downgraded."""
    self_obs = reconcile(ARTIFACT, perceive=_perceive,
                         criterion=_self_authored_criterion(), producer=PRODUCER, strict=True)
    indep_obs = reconcile(ARTIFACT, perceive=_perceive,
                          criterion=_independent_criterion(), producer=PRODUCER, strict=True)
    return self_obs, indep_obs


def _row(label, independence, verdict, status):
    return f"  {label:<24} {independence:<22} {verdict:<13} {status}"


def main() -> int:
    print("=" * 78)
    print("CRITERION INDEPENDENCE WITNESS -- closing the 'a criterion it did NOT author' seam")
    print("=" * 78)
    print(f"  artifact producer : {PRODUCER}")
    print(f"  self-authored crit: author={SELF_AUTHOR}  (author == producer)")
    print(f"  independent  crit : author={INDEP_AUTHOR}  (author != producer)")
    print()

    b_self, b_indep = before()
    identical = b_self == b_indep
    print("BEFORE -- independence NOT witnessed (no `producer` passed):")
    print(_row("case", "independence", "verdict", "status"))
    # Re-derive the human fields from the canonical bytes for the table.
    sb = json.loads(b_self.decode())
    ib = json.loads(b_indep.decode())
    print(_row("self-authored", sb["data"]["independence"], sb["data"]["verdict"], sb["status"]))
    print(_row("independent", ib["data"]["independence"], ib["data"]["verdict"], ib["status"]))
    print(f"  -> emitted Observations BYTE-IDENTICAL: {identical}"
          f"   (self-grading is INDISTINGUISHABLE from independent grading)")
    print()

    self_obs, indep_obs = after()
    a_self, a_indep = _canonical_bytes(self_obs), _canonical_bytes(indep_obs)
    distinguished = a_self != a_indep
    print("AFTER  -- independence witnessed (`producer` passed) + strict mode ON:")
    print(_row("case", "independence", "verdict", "status"))
    print(_row("self-authored", self_obs.data["independence"], self_obs.data["verdict"],
               self_obs.status.value))
    print(_row("independent", indep_obs.data["independence"], indep_obs.data["verdict"],
               indep_obs.status.value))
    print(f"  -> emitted Observations DISTINGUISHABLE: {distinguished}")
    print(f"  -> self-authored decided verdict DOWNGRADED to: {self_obs.data['verdict']}"
          f"   ({self_obs.data.get('downgrade_reason', '-')})")
    print(f"  -> independent verdict stays decided: {indep_obs.data['verdict']}"
          f"   (status {indep_obs.status.value})")
    print("=" * 78)

    # The checkable result: the seam exists BEFORE (identical) and is closed AFTER
    # (distinguished + downgraded). Non-zero exit if either property fails.
    ok = identical and distinguished and self_obs.data["verdict"] == "unverifiable" \
        and indep_obs.data["verdict"] == "verified"
    print("RESULT:", "seam reproduced then closed (OK)" if ok else "UNEXPECTED -- investigate")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
