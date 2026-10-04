"""action_authority.py -- what decided that an action was approved or refused.

A tool-call receipt says what ran and what it touched. The ``authority`` block
says on whose say-so. Five bases, strongest first:

  * ``intent``: the human's stated goal, quoted, with its date and source.
  * ``policy:machine``: a rule checked by code outside the agent. Here that is
    the separate-identity signer's ``check_policy`` statement (signer/policy.py),
    signed under a key the verifier pins.
  * ``scope``: the role or task boundary the action falls inside.
  * ``policy:self``: a rule that lives only in the agent's own instructions.
    Nothing enforces it, so it never renders as a pass.
  * ``none``: nothing. A FINDING, never a pass.

Each element carries a decision, ``allow`` or ``deny``. A deny is narrower than
an allow, and the narrower one wins. When scope and policy disagree the block
records both, names the winner, and the event is appended to a disagreement
log. A confirmation counts as ``intent`` only when it names the object acted on
and the fact that matters, and does not restate the agent's own plan summary;
otherwise it is recorded as ``scope`` at most (``classify_confirmation``).

Standard library only. Checking a block is action_authority_verify.py.
"""
from __future__ import annotations

import re
from datetime import date

INTENT, MACHINE, SCOPE, SELF, NONE = "intent", "policy:machine", "scope", "policy:self", "none"
STRENGTH = (INTENT, MACHINE, SCOPE, SELF)
ALLOW, DENY = "allow", "deny"
PASS, UNENFORCED, FINDING = "PASS", "UNENFORCED", "FINDING"
DISAGREEMENT_SCHEMA = "flywheel.authority-disagreement/v1"
RESTATEMENT_SHARE = 0.8

_WORD = re.compile(r"[a-z0-9][a-z0-9_./-]*")
_STOP = frozenset("the a an and or to of for in on at it is be this that with you your "
                  "please yes ok okay sure go ahead do so as i we will can".split())


class AuthorityError(ValueError):
    """An authority element is malformed."""


def _norm(text: str) -> str:
    return " ".join(_WORD.findall(str(text).lower()))


def _content(text: str) -> set:
    return {w for w in _WORD.findall(str(text).lower()) if w not in _STOP and len(w) > 2}


def classify_confirmation(text: str, *, object_name: str, fact: str,
                          plan_summary: str) -> tuple[str, str]:
    """(basis, reason) for a human confirmation. ``intent`` needs the object
    and the fact named in the human's own words; a restated plan is scope."""
    norm = _norm(text)
    if not object_name or _norm(object_name) not in norm:
        return SCOPE, "does not name the object acted on"
    if not fact or _norm(fact) not in norm:
        return SCOPE, "does not name the fact that matters"
    words, plan = _content(text), _content(plan_summary)
    if plan and words and len(words & plan) / len(words) >= RESTATEMENT_SHARE:
        return SCOPE, "restates the agent's own plan summary"
    return INTENT, "names the object and the fact in the human's words"


def _decision(value: str) -> str:
    if value not in (ALLOW, DENY):
        raise AuthorityError(f"decision must be {ALLOW!r} or {DENY!r}, got {value!r}")
    return value


def intent(quote: str, *, on: str, source: str, decision: str, object_name: str,
           fact: str, plan_summary: str) -> dict:
    """A human confirmation. Its basis is classified here, so an element built
    from a plan restatement is a scope element from the start."""
    date.fromisoformat(on)
    if not quote or not source:
        raise AuthorityError("intent needs the quoted words and their source")
    basis, why = classify_confirmation(quote, object_name=object_name, fact=fact,
                                       plan_summary=plan_summary)
    return {"basis": basis, "decision": _decision(decision), "quote": quote, "date": on,
            "source": source, "object": object_name, "fact": fact,
            "plan_summary": plan_summary, "classified": why}


def scope(boundary: str, decision: str) -> dict:
    if not boundary:
        raise AuthorityError("scope needs the boundary it names")
    return {"basis": SCOPE, "decision": _decision(decision), "boundary": boundary}


def policy_self(rule: str, decision: str) -> dict:
    """A rule from the agent's own instructions. Recorded, never enforced."""
    return {"basis": SELF, "decision": _decision(decision), "rule": rule}


def policy_machine(statement: dict) -> dict:
    """A rule the signer checked. The decision comes from the signed verdict,
    never from the caller."""
    verdict = statement.get("verdict") if isinstance(statement, dict) else None
    decision = ALLOW if verdict == "ALLOW" else DENY
    return {"basis": MACHINE, "decision": decision, "statement": statement}


def from_signer(client, tool: str, args: dict, path_id: str = "E1") -> dict:
    """Ask the separate signer to check the shipped rules on this call, and
    return the signed result as a policy:machine element."""
    return policy_machine(client.check_policy(tool, args, path_id))


def _strongest(elements: list) -> dict:
    return min(elements, key=lambda e: STRENGTH.index(e["basis"]))


def _disagreement(elements: list):
    scopes = [e for e in elements if e["basis"] == SCOPE]
    policies = [e for e in elements if e["basis"] in (MACHINE, SELF)]
    for s in scopes:
        for p in policies:
            if s["decision"] != p["decision"]:
                winner = s if s["decision"] == DENY else p
                return {"scope": s["decision"], "policy": p["decision"],
                        "policy_basis": p["basis"], "winner": winner["basis"]}
    return None


def resolve(elements: list) -> dict:
    """The authority block for a set of elements: the deciding basis, the
    decision, the verdict for that basis, and any scope/policy disagreement."""
    elements = [e for e in elements if e]
    if not elements:
        return {"basis": NONE, "decision": DENY, "verdict": FINDING, "elements": [],
                "note": "nothing recorded as deciding this action"}
    denies = [e for e in elements if e["decision"] == DENY]
    decider = _strongest(denies or elements)
    block = {"basis": decider["basis"], "decision": decider["decision"],
             "verdict": verdict_for(decider["basis"]), "elements": elements}
    clash = _disagreement(elements)
    if clash:
        block["disagreement"] = clash
    return block


def verdict_for(basis: str) -> str:
    if basis == NONE:
        return FINDING
    if basis == SELF:
        return UNENFORCED
    return PASS


def log_disagreement(log_home, block: dict, *, tool: str, args_sha256: str, at: str,
                     signer=None) -> None:
    """Append a scope/policy disagreement to its own sealed log. With a signer
    configured (FLYWHEEL_SIGNER, or ``signer``) the entry is signed too."""
    if "disagreement" not in block:
        return
    from .preaction.records import HoldStore
    kwargs = {} if signer is None else {"signer": signer}
    HoldStore(log_home, **kwargs).append({
        "schema": DISAGREEMENT_SCHEMA, "source": f"authority:{tool}:{args_sha256[:16]}",
        "tool": tool, "args_sha256": args_sha256, "at": at, **block["disagreement"]})


def attach(receipt: dict, block: dict) -> dict:
    """Seal ``block`` into a tool-call receipt as ``authority``, before the
    seal block, and reseal. A receipt with no block is unchanged."""
    from .tool_call_receipt import _seal_receipt
    seal_block = receipt.pop("seal")
    receipt["authority"] = block
    receipt["seal"] = {"algorithm": seal_block.get("algorithm", "sha256"), "hex": ""}
    _seal_receipt(receipt)
    return receipt
