"""claim_grounding.py -- the summary cannot outrun the ledger.

Every tamper-evidence system stops at "the log was not edited." This goes one step
the others do not: it checks the agent's FINAL ANSWER against the log. Each factual
claim in the summary is decomposed into an atomic assertion and bound to a witnessing
ledger entry that entails it -- a read/tool_result that returned the named file, a
check whose recorded pass/fail matches a claimed test verdict, an edit whose path
matches a claimed change -- or the run is stamped UNGROUNDED. A summary that claims
the tests pass over a failed check entry is REFUTED, even with an intact chain.

Checking the story against the chain is what the chain was for, and no competitor can
do it: it needs a per-turn ledger with witnessed tool results they do not keep.

Honest null: the claim extractor is RULE-BASED and brittle. It classifies test-verdict
and file-change claims and grounds those; anything it cannot parse degrades to
``unclassified`` -- FAIL-CLOSED, counted against the run, never a silent pass. This is
instrument v1, not a solved NLP problem.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .local_tools import edited_targets

SCHEMA = "relay.claim-grounding/v1"
GROUNDED, UNGROUNDED, REFUTED, UNVERIFIABLE = "GROUNDED", "UNGROUNDED", "REFUTED", "UNVERIFIABLE"

_FILE = re.compile(r"\b[\w./-]+\.[A-Za-z]{1,4}\b")     # a filename with an extension
_CHANGE = ("edit", "edited", "fix", "fixed", "add", "added", "refactor", "refactored",
           "change", "changed", "wrote", "write", "remove", "removed", "create", "created",
           "implement", "implemented", "update", "updated", "rename", "renamed", "delete", "deleted")
_TESTWORD = ("test", "tests", "suite", "check", "checks", "pytest", "spec", "specs")
_PASS = ("pass", "passes", "passed", "passing", "green", "succeed", "succeeds", "succeeded")
_FAIL = ("fail", "fails", "failed", "failing", "red", "broken")


@dataclass(frozen=True)
class Claim:
    text: str
    kind: str            # "test_verdict" | "file_change" | "vague"
    target: str = ""     # the named file (file_change)
    polarity: str = ""   # "pass" | "fail" (test_verdict)


def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text or "")
    return [s.strip() for s in parts if s.strip()]


def _words(low: str) -> set:
    return set(re.findall(r"[a-z]+", low))


def extract_claims(final_answer: str) -> list:
    """Decompose a final answer into atomic, classifiable claims (rule-based)."""
    claims = []
    for sentence in _sentences(final_answer):
        low = sentence.lower()
        words = _words(low)
        files = _FILE.findall(sentence)
        if words & set(_TESTWORD) and words & (set(_PASS) | set(_FAIL)):
            polarity = "fail" if words & set(_FAIL) else "pass"
            claims.append(Claim(sentence, "test_verdict", polarity=polarity))
        elif files and words & set(_CHANGE):
            claims.append(Claim(sentence, "file_change", target=files[0]))
        else:
            claims.append(Claim(sentence, "vague"))
    return claims


def _base(path: str) -> str:
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


def _witnessed_edits(ledger) -> set:
    out = set()
    for e in ledger.entries:
        if getattr(e, "kind", "") != "tool_call":
            continue
        name, _, rest = (getattr(e, "content", "") or "").partition(" ")
        try:
            args = json.loads(rest) if rest else {}
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(args, dict):
            for p, _new in edited_targets(name, args):
                out.add(_base(p))
    return out


def _last_check_ok(ledger):
    checks = [e for e in ledger.entries if getattr(e, "kind", "") == "check"]
    return bool(checks[-1].meta.get("ok")) if checks else None


def _ground_one(claim: Claim, check_ok, edits: set) -> str:
    if claim.kind == "test_verdict":
        if check_ok is None:
            return "ungrounded"                       # a verdict claim with no witnessing check
        claimed_pass = claim.polarity == "pass"
        return "grounded" if check_ok == claimed_pass else "refuted"
    if claim.kind == "file_change":
        return "grounded" if _base(claim.target) in edits else "ungrounded"
    return "unclassified"


def ground_claims(claims: list, ledger) -> dict:
    """Bind each claim to a witness, or mark it ungrounded/refuted/unclassified."""
    check_ok = _last_check_ok(ledger)
    edits = _witnessed_edits(ledger)
    findings = [{"text": c.text, "kind": c.kind, "status": _ground_one(c, check_ok, edits)}
                for c in claims]
    statuses = [f["status"] for f in findings]
    if "refuted" in statuses:
        verdict = REFUTED
    elif "ungrounded" in statuses:
        verdict = UNGROUNDED
    elif "unclassified" in statuses:
        verdict = UNVERIFIABLE                        # fail-closed: unparsed is not a pass
    else:
        verdict = GROUNDED
    total = len(findings)
    return {"schema": SCHEMA, "verdict": verdict, "findings": findings,
            "grounded_ratio": (statuses.count("grounded") / total) if total else 1.0}


def ground_final_answer(ledger) -> dict:
    """Ground the run's final answer (its last assistant turn) against the ledger."""
    finals = [e for e in ledger.entries if getattr(e, "kind", "") == "assistant"]
    text = finals[-1].content if finals else ""
    result = ground_claims(extract_claims(text), ledger)
    result["seq"] = getattr(finals[-1], "seq", None) if finals else None
    return result
