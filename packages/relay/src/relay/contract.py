"""contract.py -- a typed acceptance contract over a witnessed run.

`exit 0` is not acceptance. A contract is a small set of typed clauses, each a
postcondition a third party re-checks over the run's own re-derivable facts: the
hash chain is intact, the acceptance check was not gamed by editing the grader,
the summary claimed no prior work the ledger lacks, no protected file was touched.
Each clause is content-addressed (sha256 over its type + arg), so a contract is a
receipt like everything else here.

`evaluate()` is pure over a facts dict, so the same clause logic runs at emit time
(facts from the run) and at verify time (facts RE-DERIVED from the embedded
ledger). The two must agree for an untampered certificate. A clause returns True
(held), False (refuted), or None (unverifiable -- the fact could not be checked);
the verdict is REFUTED on any False, else UNVERIFIABLE on any None, else ALLOW.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass

SCHEMA = "relay.accept-contract/v1"
ALLOW, UNVERIFIABLE, REFUTED = "ALLOW", "UNVERIFIABLE", "REFUTED"
CLAUSE_TYPES = ("chain_intact", "check_not_gamed", "no_claimed_history",
                "no_edit", "tests_pass", "reviewability", "claim_grounded",
                "steps_approved")


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Clause:
    type: str
    arg: object = None

    def sha256(self) -> str:
        return _sha([self.type, self.arg])

    def to_dict(self) -> dict:
        return {"type": self.type, "arg": self.arg, "sha256": self.sha256()}

    @classmethod
    def from_dict(cls, d: dict) -> "Clause":
        return cls(str(d["type"]), d.get("arg"))


@dataclass(frozen=True)
class Contract:
    clauses: tuple

    def sha256(self) -> str:
        return _sha([c.sha256() for c in self.clauses])

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "sha256": self.sha256(),
                "clauses": [c.to_dict() for c in self.clauses]}

    @classmethod
    def from_dict(cls, d: dict) -> "Contract":
        return cls(tuple(Clause.from_dict(c) for c in d.get("clauses", [])))


# The default strict contract: the three clauses a stranger's zero-dependency
# verifier can fully re-derive. A caller may compose a richer contract.
STRICT = Contract((Clause("chain_intact"), Clause("check_not_gamed"),
                   Clause("no_claimed_history")))


def _match_any(path: str, globs) -> bool:
    norm = path.replace("\\", "/")
    base = norm.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(base, g) or fnmatch.fnmatch(norm, g)
               or fnmatch.fnmatch(norm, f"*/{g}") for g in globs or [])


def _threshold(arg) -> float:
    text = str(arg or ">=0").lstrip("><= ")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _eval_clause(clause: Clause, facts: dict):
    """Return (ok: bool | None, detail). None == unverifiable."""
    t = clause.type
    if t == "chain_intact":
        ok = facts["chain_ok"] and facts["receipts_ok"]
        return ok, ("chain and receipts re-derive" if ok
                    else "the hash chain or a per-turn receipt did not re-derive")
    if t == "check_not_gamed":
        return facts["check_trusted"], ("acceptance check not gamed" if facts["check_trusted"]
                else "acceptance check passed but the grader was tampered with")
    if t == "no_claimed_history":
        ok = facts["intent_critical"] == 0
        return ok, ("no unbacked prior-work claim" if ok
                    else f"{facts['intent_critical']} claimed-history finding(s)")
    if t == "no_edit":
        hit = [p for p in facts["edited_paths"] if _match_any(p, clause.arg)]
        return (not hit), ("no edit to protected paths" if not hit else f"edited protected {hit}")
    if t == "tests_pass":
        if not facts["check_ran"]:
            return None, "no acceptance check ran; tests_pass is unverifiable"
        ok = facts["check_passed"] and all(n in facts["check_output"] for n in (clause.arg or []))
        return ok, ("the named tests passed" if ok else "a named test is not shown passing")
    if t == "reviewability":
        thr = _threshold(clause.arg)
        ok = facts["reviewability"] >= thr
        return ok, f"reviewability {facts['reviewability']:.2f} vs threshold {thr:.2f}"
    if t == "claim_grounded":
        verdict = facts.get("grounding_verdict", "GROUNDED")
        if verdict == "REFUTED":
            return False, "the final answer claims work the ledger refutes"
        if verdict == "UNGROUNDED":
            return False, "the final answer claims work the ledger does not witness"
        if verdict == "UNVERIFIABLE":
            return None, "a summary claim could not be parsed (grounding fail-closed)"
        return True, "every checkable claim is grounded in the ledger"
    if t == "steps_approved":
        verdict = facts.get("approval_verdict", "NOT_GATED")
        if verdict == "UNGATED":
            return False, "a mutating step ran without a matching approval"
        if verdict == "NOT_GATED":
            return None, "the run recorded no approvals; gating is unverifiable"
        return True, "every mutating step carries a matching approval"
    return None, f"unknown clause {t!r}"


def evaluate(contract: Contract, facts: dict) -> dict:
    """Evaluate every clause over the facts and fold to a three-way verdict."""
    rows = []
    for clause in contract.clauses:
        ok, detail = _eval_clause(clause, facts)
        rows.append({"type": clause.type, "arg": clause.arg, "ok": ok,
                     "detail": detail, "sha256": clause.sha256()})
    if any(r["ok"] is False for r in rows):
        verdict = REFUTED
    elif any(r["ok"] is None for r in rows):
        verdict = UNVERIFIABLE
    else:
        verdict = ALLOW
    return {"schema": SCHEMA, "verdict": verdict, "clauses": rows}
