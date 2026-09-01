"""base.py -- the certificate oracle: read the data, never run it.

A construction certificate is a data structure and validating one is arithmetic.
This module imports nothing that can execute: no subprocess, no socket, no
ctypes, no pickle, no importlib, no eval. A test asserts that structurally,
because the property is what makes handing a verifier to a stranger safe instead
of handing them a way to run code on their machine.

Three things the base does so no subclass has to remember them:

  1. **Envelope before dispatch.** Declared parameters outside the criterion's
     scope bounds yield UNVERIFIABLE with OUT_OF_SCOPE, and `check` is never
     called. Out of scope is not wrong: scoring FAIL there would teach a policy
     to avoid legal regions of the parameter space for no reason.
  2. **Canonical hashing.** The output hash is over the canonicalized
     certificate plus the verdict, so two semantically identical certificates
     that differ only in key order agree, and a stranger re-deriving the hash
     does not disagree over formatting.
  3. **Coverage, always.** Every result carries what the check did NOT cover,
     and mechanically derives `does_not_prove` entries from it. A receipt that
     reports only its proof is how a true explanation becomes a fake passport.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict

from ..oracle import OracleResult
from ..verdict import Verdict, Execution, Attribution, UnverifiableReason


class CertificateError(ValueError):
    """A malformed coverage claim or checker contract."""


class OutOfScope(Exception):
    """Raised by a subclass's check() when the instance sits outside what this
    checker can dispose, in a way the declared-parameter envelope did not catch.

    The base turns it into UNVERIFIABLE with OUT_OF_SCOPE, never FAIL. A
    candidate is not wrong for handing us something we do not implement.
    """


@dataclass(frozen=True)
class Coverage:
    """What the check actually covered, and where its guarantee stops."""
    predicate_exact: bool
    search_space_enumerated: bool
    enumerated_fraction: str            # decimal or rational STRING, never float
    stop_reason: str                    # complete | budget | timeout | bound
    guarantee_weakens_above: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enumerated_fraction, str):
            raise CertificateError(
                "enumerated_fraction must be a string (a float in a hashed field "
                "makes a stranger's replay disagree over formatting)")

    def to_dict(self) -> dict:
        return asdict(self)


def canonical(obj) -> str:
    """Canonical JSON: sorted keys, tight separators. Two honest parties must not
    disagree because a dict was built in a different order."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _finite_number(token: str) -> float:
    # json accepts NaN/Infinity/-Infinity (parse_constant) and overflow literals
    # like 1e400 (parse_float) as non-finite floats; canonical()'s allow_nan=False
    # would then raise deep in verify(), so refuse them into an honest parse FAIL.
    f = float(token)
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(f"non-finite number {token!r} has no canonical form")
    return f


def parse_certificate(text: str) -> tuple[bool, dict, str]:
    """(ok, cert, why). A certificate is exactly one JSON object. Trailing
    garbage is refused: it is the cheapest smuggling channel there is."""
    if not isinstance(text, str):
        return False, {}, "certificate must be text"
    s = text.strip()
    if not s:
        return False, {}, "empty certificate"
    try:
        decoder = json.JSONDecoder(parse_constant=_finite_number, parse_float=_finite_number)
        obj, end = decoder.raw_decode(s)
    except Exception as e:
        return False, {}, f"not valid json: {e}"
    if s[end:].strip():
        return False, {}, "trailing content after the certificate object"
    if not isinstance(obj, dict):
        return False, {}, "certificate must be a json object"
    return True, obj, ""


ALWAYS_NOT_PROVEN = ("NOT_PROVES_NOVELTY", "NOT_PROVES_PUBLICATION_COMPLETENESS")


class CertificateOracle:
    """Base for data-only checkers. Subclasses implement `check`,
    `declared_parameters`, and `objective_of`, and never execute anything."""

    oracle_type = "certificate"
    family = "unset"
    scope_bounds: dict = {}
    executes_candidate_code = False        # a schema field a stranger filters on

    # Which declared parameters must MATCH the instance the candidate was asked
    # about. Empty means this family has not declared a binding, and every result
    # then says so rather than implying the certificate answered the question.
    #
    # This exists because `declared_parameters` reads the CERTIFICATE. Without a
    # binding, a candidate declares its own instance: asked for a 64x64 problem it
    # could submit a valid 3x3 certificate and earn PASS. `verify` accepted a
    # `task` argument and never read it, so four different instances produced
    # byte-identical verdicts AND byte-identical digests.
    binding_keys: tuple = ()

    # Codes this family always carries. A checker that verifies a SUBMITTED
    # object and does not decide optimality says so on every single result, so
    # the qualifier travels into every receipt and every bundle rather than
    # living in a document somebody may not read.
    family_not_proven: tuple = ()

    # --- subclass contract ---------------------------------------------------

    def check(self, cert: dict) -> tuple[bool, str, Coverage]:
        raise NotImplementedError

    def declared_parameters(self, cert: dict) -> dict:
        raise NotImplementedError

    def instance_binding(self, task) -> dict | None:
        """The parameters the INSTANCE fixes, or None when there is no instance.

        None is not a pass. It means the result cannot claim the certificate
        answered the question asked, and `_result` records that.
        """
        if not isinstance(task, dict) or not self.binding_keys:
            return None
        present = {k: task[k] for k in self.binding_keys if k in task}
        return present or None

    def objective_of(self, cert: dict) -> str:
        return ""

    # --- the fixed pipeline --------------------------------------------------

    # Bound suffixes this base understands. A scope key using any other suffix is
    # a DECLARED bound nobody enforces, which is worse than no bound at all, so it
    # is refused loudly rather than skipped silently.
    _BOUND_KINDS = {"_max": "max", "_min": "min", "_eq": "eq", "_in": "in"}

    def _in_scope(self, params: dict) -> tuple[bool, str]:
        """Enforce every declared bound, or refuse to pretend we did.

        The first version only handled keys ending `_max` and silently skipped
        everything else. That is a FALSE ACCEPT on the accept path: a checker
        declaring `d_min=4` would return PASS for a certificate declaring `d=1`,
        because the bound was never read. Found by probe, not by reading.
        """
        for key, bound in self.scope_bounds.items():
            suffix = next((s for s in self._BOUND_KINDS if key.endswith(s)), None)
            if suffix is None:
                raise OutOfScope(
                    f"scope bound {key!r} uses an unrecognized suffix; supported "
                    f"suffixes are {sorted(self._BOUND_KINDS)}. A declared bound "
                    "nobody enforces is worse than no bound, so this is a refusal "
                    "rather than a skip.")
            name = key[: -len(suffix)]
            if name not in params:
                continue
            value = params[name]
            kind = self._BOUND_KINDS[suffix]
            try:
                if kind == "max" and value > bound:
                    return False, f"{name}={value!r} exceeds {key}={bound!r}"
                if kind == "min" and value < bound:
                    return False, f"{name}={value!r} is below {key}={bound!r}"
                if kind == "eq" and value != bound:
                    return False, f"{name}={value!r} is not {key}={bound!r}"
                if kind == "in" and value not in bound:
                    return False, f"{name}={value!r} is not in {key}={bound!r}"
            except TypeError as e:
                # A declared parameter whose type cannot be compared to its bound
                # is a gap in the record, not a candidate error. Raising out of
                # verify() would crash a caller checking untrusted input.
                raise OutOfScope(
                    f"cannot compare {name}={value!r} against {key}={bound!r}: {e}")
        return True, ""

    def _result(self, verdict: Verdict, cert_canon: str, excerpt: str, *,
                coverage: Coverage | None = None, objective: str | None = None,
                attribution: Attribution = Attribution.CANDIDATE,
                unverifiable_reason: str = "",
                binding: dict | None = None) -> OracleResult:
        cov = coverage.to_dict() if coverage else {}
        dnp = list(ALWAYS_NOT_PROVEN) + list(self.family_not_proven)
        if coverage is not None and not coverage.predicate_exact:
            dnp.append("NOT_PROVES_EXACTNESS")
        if coverage is not None and not coverage.search_space_enumerated:
            dnp.append("NOT_PROVES_COMPLETE_ENUMERATION")
        dnp.append("NOT_PROVES_RESISTANCE_TO_ORACLE_GAMING")   # no held-out here
        if binding is None:
            # The single most important line in this method. An unbound verdict
            # says the certificate is internally valid, and says NOTHING about
            # whether it answers the instance the candidate was given.
            dnp.append("NOT_PROVES_ANSWERS_THE_QUESTION_ASKED")
        # The binding enters the preimage, so the same certificate checked
        # against two different instances no longer produces one digest.
        preimage = canonical({"cert": cert_canon, "verdict": verdict.value,
                              "family": self.family,
                              "instance_binding": binding})
        return OracleResult(
            cmd=f"{self.oracle_type}:{self.family}",
            output_hash=hashlib.sha256(preimage.encode()).hexdigest()[:16],
            stdout_excerpt=excerpt[:1200],
            rc=0 if verdict is Verdict.PASS else 1,
            verdict_=verdict,
            execution=Execution.COMPLETED,
            attribution=attribution,
            raw_stdout_sha256=hashlib.sha256(excerpt.encode("utf-8", "surrogatepass")).hexdigest(),
            objective=objective,
            unverifiable_reason=unverifiable_reason,
            coverage=dict(cov, instance_bound=binding is not None,
                          instance_binding=binding or {}),
            does_not_prove=dnp)

    def verify(self, candidate: str, task=None) -> OracleResult:
        binding = self.instance_binding(task)
        ok, cert, why = parse_certificate(candidate)
        if not ok:
            # The candidate emitted something that is not a certificate. That is
            # the candidate's error and it earns a FAIL.
            return self._result(Verdict.FAIL, "", f"parse failed: {why}",
                                binding=binding)

        try:
            params = self.declared_parameters(cert)
        except Exception as e:
            return self._result(Verdict.FAIL, canonical(cert),
                                f"malformed certificate: {e}", binding=binding)

        if binding:
            # Answering a DIFFERENT question is the candidate's error, not a gap
            # in the record, so it is FAIL and not UNVERIFIABLE. A valid 3x3
            # certificate submitted against a 64x64 instance is a wrong answer.
            wrong = {k: {"asked": v, "declared": params.get(k)}
                     for k, v in binding.items() if params.get(k) != v}
            if wrong:
                return self._result(
                    Verdict.FAIL, canonical(cert),
                    "certificate does not answer the instance it was given: "
                    + canonical(wrong), binding=binding)

        # Inside a guard: _in_scope can now raise OutOfScope for an unenforceable
        # bound or an incomparable type, and an uncaught raise out of verify()
        # would crash a caller checking untrusted input.
        try:
            in_scope, reason = self._in_scope(params)
        except OutOfScope as e:
            return self._result(
                Verdict.UNVERIFIABLE, canonical(cert), f"scope undecidable: {e}",
                attribution=Attribution.HARNESS,
                unverifiable_reason=UnverifiableReason.OUT_OF_SCOPE.value,
                binding=binding)
        if not in_scope:
            # Out of scope is not wrong. The check simply does not apply, so the
            # record says so and does not blame the candidate.
            return self._result(
                Verdict.UNVERIFIABLE, canonical(cert),
                f"out of scope: {reason}",
                attribution=Attribution.ENVIRONMENT,
                unverifiable_reason=UnverifiableReason.OUT_OF_SCOPE.value,
                binding=binding)

        try:
            valid, excerpt, coverage = self.check(cert)
        except OutOfScope as e:
            # The checker itself declined: not implemented for this shape. A gap
            # in the record, not a candidate error.
            return self._result(
                Verdict.UNVERIFIABLE, canonical(cert), f"out of scope: {e}",
                attribution=Attribution.ENVIRONMENT,
                unverifiable_reason=UnverifiableReason.OUT_OF_SCOPE.value,
                binding=binding)
        except Exception as e:
            return self._result(Verdict.FAIL, canonical(cert),
                                f"certificate rejected: {e}", binding=binding)

        return self._result(
            Verdict.PASS if valid else Verdict.FAIL, canonical(cert), excerpt,
            coverage=coverage, objective=self.objective_of(cert),
            binding=binding)
