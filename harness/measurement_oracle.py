"""measurement_oracle.py -- the ml (measurement-gate) domain oracle.

The empirical lane. Where PytestOracle disposes code and LeanOracle disposes a
proof, this disposes a MEASUREMENT CLAIM: an effect with its interval, a
registered minimum it must clear, a sample size, and a negative control that
must hold at zero. The accept authority is the gate arithmetic over the claim's
own denominator, never a learned model -- C2-clean, the same shape as the other
oracles.

A claim is JSON:
  {"effect": e, "ci_low": lo, "ci_high": hi, "min_effect": m, "n": N,
   "negative_control": {"effect": e0, "ci_low": lo0, "ci_high": hi0}}
PASS requires all three: the interval clears the registered minimum
(ci_low > min_effect), the negative-control interval holds at zero
(lo0 <= 0 <= hi0), and the sample clears the registered minimum size
(n >= n_min). FAIL if the effect does not clear, or the control is significant
(a confound), or n is too small. UNVERIFIABLE, never FAIL, when the claim has no
denominator to price it: no n, no interval, no registered minimum, or no
control. A measurement without its denominator and interval is not a result.

Determinism: the hash is over the CANONICAL claim with every number rendered as
a string (NO FLOATS in a hashed field, because cross-platform float text is how
an honest replay disagrees over nothing real) plus the verdict word.
"""
from __future__ import annotations

import hashlib
import json

from .oracle import OracleResult
from .receipt_fields import canonical
from .verdict import Verdict, Execution, UnverifiableReason

CMD = "measurement_gate"
DEFAULT_N_MIN = 1

OBJECTIVE = ("measurement gate: the effect interval clears the registered "
             "minimum and the negative-control interval holds at zero")

# does_not_prove: the scope a passing gate does NOT extend to. Both travel on
# every dispositive verdict so the receipt can never read as more than checked.
_EVIDENCE_NOT_PROOF = ("a passing interval is evidence the effect cleared the "
                       "registered minimum on this sample, not proof of the "
                       "effect")
_CONTROL_SCOPE = ("the negative control bounds only the tested confound; an "
                  "untested confound is not excluded")
_NO_DENOMINATOR = ("a measurement without its denominator and interval is not a "
                   "result, so nothing was disposed")

_REQUIRED = ("effect", "ci_low", "ci_high", "min_effect", "n")


def _is_number(x) -> bool:
    """A real number, not a bool. bool subclasses int in Python, so an honest
    numeric field must exclude True/False explicitly."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _stringify_numbers(obj):
    """Every number -> its str, recursively. The hashed form of a claim carries
    no float, because cross-platform float formatting is the likeliest way a
    stranger's replay disagrees over nothing real."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _stringify_numbers(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_stringify_numbers(v) for v in obj]
    return obj


def _control_interval(claim: dict):
    """(lo0, hi0) of the negative control, or None if the control is absent or
    carries no interval. A control without its interval cannot bound a confound."""
    nc = claim.get("negative_control")
    if not isinstance(nc, dict):
        return None
    lo0, hi0 = nc.get("ci_low"), nc.get("ci_high")
    if not (_is_number(lo0) and _is_number(hi0)):
        return None
    return float(lo0), float(hi0)


def _nc_lo(claim: dict):
    return claim["negative_control"]["ci_low"]


def _nc_hi(claim: dict):
    return claim["negative_control"]["ci_high"]


def evaluate_claim(claim, *, n_min: int) -> dict:
    """Grade a parsed claim. Returns a dict with `status` in
    {PASS, FAIL, UNVERIFIABLE}, a human `reason`, an `unverifiable_reason`
    (UnverifiableReason or None), and `coverage`. Pure: no I/O, no hashing."""
    if not isinstance(claim, dict):
        return {"status": "UNVERIFIABLE",
                "reason": "the claim is not a JSON object",
                "unverifiable_reason": UnverifiableReason.ENVELOPE_MISSING,
                "coverage": {"n": None, "negative_control_present": False}}

    nc_present = isinstance(claim.get("negative_control"), dict)
    n_raw = claim.get("n")
    coverage = {"n": n_raw if isinstance(n_raw, int) and not isinstance(n_raw, bool)
                else None,
                "negative_control_present": nc_present}

    # Denominator discipline: a claim with no n, no interval, or no registered
    # minimum cannot be priced. UNVERIFIABLE, never FAIL.
    for key in _REQUIRED:
        if key not in claim:
            return {"status": "UNVERIFIABLE",
                    "reason": f"the claim is missing '{key}'; without it the "
                              "measurement has no denominator to price it",
                    "unverifiable_reason": UnverifiableReason.ENVELOPE_MISSING,
                    "coverage": coverage}
        if not _is_number(claim[key]):
            return {"status": "UNVERIFIABLE",
                    "reason": f"the claim field '{key}'={claim[key]!r} is not a "
                              "number; the interval and denominator are unpriceable",
                    "unverifiable_reason": UnverifiableReason.ENVELOPE_MISSING,
                    "coverage": coverage}

    control = _control_interval(claim)
    if control is None:
        return {"status": "UNVERIFIABLE",
                "reason": "no negative control with an interval; the tested "
                          "confound is unbounded, so the effect cannot be "
                          "attributed",
                "unverifiable_reason": UnverifiableReason.CONFOUNDED,
                "coverage": coverage}

    n = int(claim["n"])
    coverage["n"] = n
    coverage["n_min"] = int(n_min)
    coverage["min_effect"] = str(claim["min_effect"])

    ci_low = float(claim["ci_low"])
    min_effect = float(claim["min_effect"])
    lo0, hi0 = control

    clears = ci_low > min_effect
    control_holds = lo0 <= 0.0 <= hi0
    big_enough = n >= int(n_min)

    if clears and control_holds and big_enough:
        return {"status": "PASS",
                "reason": (f"ci_low={claim['ci_low']} clears min_effect="
                           f"{claim['min_effect']}, negative control "
                           f"[{_nc_lo(claim)}, {_nc_hi(claim)}] holds at zero, "
                           f"n={n} >= {int(n_min)}"),
                "unverifiable_reason": None,
                "coverage": coverage}

    faults = []
    if not clears:
        faults.append(f"ci_low={claim['ci_low']} does not clear min_effect="
                      f"{claim['min_effect']}")
    if not control_holds:
        faults.append(f"negative control [{_nc_lo(claim)}, {_nc_hi(claim)}] "
                      "excludes zero, so a confound is significant")
    if not big_enough:
        faults.append(f"n={n} is below the registered minimum {int(n_min)}")
    return {"status": "FAIL",
            "reason": "; ".join(faults),
            "unverifiable_reason": None,
            "coverage": coverage}


class MeasurementOracle:
    """The ml domain oracle: an Oracle-Protocol adapter over the measurement
    gate. The gate arithmetic is the sole acceptance authority; no learned model
    sits in the accept path. `n_min` is the registered minimum sample size, read
    from the task when it declares one and otherwise the constructor default."""
    oracle_type = "measurement"

    def __init__(self, n_min: int = DEFAULT_N_MIN):
        self.n_min = n_min

    def _n_min(self, task) -> int:
        declared = getattr(task, "n_min", None)
        if isinstance(declared, int) and not isinstance(declared, bool):
            return declared
        return self.n_min

    def verify(self, candidate: str, task=None) -> OracleResult:
        try:
            claim = json.loads(candidate)
        except Exception as e:
            return self._result(
                claim=None, verdict=Verdict.UNVERIFIABLE, rc=0,
                reason=f"the claim did not parse as JSON: {e}",
                unverifiable_reason=UnverifiableReason.ENVELOPE_MISSING,
                coverage={"n": None, "negative_control_present": False})

        r = evaluate_claim(claim, n_min=self._n_min(task))
        status = r["status"]
        if status == "PASS":
            verdict, rc, ur = Verdict.PASS, 0, None
        elif status == "FAIL":
            verdict, rc, ur = Verdict.FAIL, 1, None
        else:
            verdict, rc, ur = Verdict.UNVERIFIABLE, 0, r["unverifiable_reason"]
        return self._result(claim=claim, verdict=verdict, rc=rc,
                            reason=r["reason"], unverifiable_reason=ur,
                            coverage=r["coverage"])

    def _result(self, *, claim, verdict, rc, reason, unverifiable_reason,
                coverage) -> OracleResult:
        payload = {"claim": _stringify_numbers(claim) if claim is not None
                   else None,
                   "verdict": verdict.value}
        output_hash = hashlib.sha256(
            canonical(payload).encode()).hexdigest()[:16]
        if verdict is Verdict.UNVERIFIABLE:
            return OracleResult(
                cmd=CMD, output_hash=output_hash,
                stdout_excerpt=reason[:1200], rc=rc,
                verdict_=Verdict.UNVERIFIABLE, execution=Execution.COMPLETED,
                unverifiable_reason=(unverifiable_reason.value
                                     if unverifiable_reason else ""),
                does_not_prove=[_NO_DENOMINATOR, _EVIDENCE_NOT_PROOF,
                                _CONTROL_SCOPE],
                coverage=coverage, objective=OBJECTIVE)
        return OracleResult(
            cmd=CMD, output_hash=output_hash, stdout_excerpt=reason[:1200],
            rc=rc, verdict_=verdict,
            does_not_prove=[_EVIDENCE_NOT_PROOF, _CONTROL_SCOPE],
            coverage=coverage, objective=OBJECTIVE)
