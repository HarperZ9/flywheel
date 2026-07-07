"""router.py — the capability router: friction goes where it is handled best.

The operator's flywheel-of-cogs thesis, made native. Every organ is best-in-class
in ONE category; alone it is a cog, together they are an engine only if a weaker
link's friction is *immediately sent to the organ that handles it*. This module is
that connective tissue: classify a friction signal, route it to the best-in-class
handler, emit a receipt binding friction -> handler. Categorical efficiency through
algorithmic flow — no friction sits at the wrong organ.

It composes, not replaces: escalation routes among ORACLE TIERS; this routes among
ORGANS by friction category. Routing is descriptive (it names the handler + action
+ receipt); the caller invokes the organ. C2 is preserved — the router never
accepts, it only dispatches.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

# category -> (best-in-class organ, the action it takes). Each organ earns its
# slot by being the strongest handler for that friction, not a generalist.
HANDLERS: dict[str, tuple[str, str]] = {
    "SYNTAX_FAIL":        ("escalation.CompileOracle", "prune before the expensive test tier"),
    "LOGIC_FAIL":         ("search.best_of_n", "diversify temperatures and re-sample, oracle selects"),
    "LOW_DIVERSITY":      ("budget_control.steer", "correlation collapse -> boost diversity, reallocate budget"),
    "UNVERIFIABLE":       ("transitive_witness.verify_frontier", "re-witness the dependency cone"),
    "STALE_KNOWLEDGE":    ("wiki.verify", "re-check sealed nodes, refresh the drifted ones"),
    "STALE_CACHE":        ("cache.knowledge_hash", "invalidate on cited-source drift, re-verify"),
    "ENV_ERROR":          ("escalation", "runner/tooling fault -> repair env, not the candidate"),
    "REPEAT_FAILURE":     ("failure_corpus.record_if_rejected", "bank as a durable regression case"),
    "UNCALIBRATED_ORACLE":("calibration.require_calibrated", "prove the oracle discriminates before trusting it"),
    "NOVEL_TASK":         ("proposer.generate", "no cached fact -> propose, then verify"),
    "REPEAT_TASK":        ("proof_cache.proof_lookup", "oracle-certified fact cached -> re-witness and serve"),
}
UNKNOWN = ("triage", "unclassified friction -> surface to the operator, do not guess a handler")


@dataclass
class Friction:
    category: str
    stage: str
    evidence: str


@dataclass
class Route:
    category: str
    handler: str
    action: str
    receipt: str


def classify(signal: dict) -> Friction:
    """Map a raw harness signal to a friction category. `signal` carries whatever
    the stage produced: an oracle result, a verdict, a correlation, a cache miss."""
    stage = str(signal.get("stage", "?"))
    rc = signal.get("rc")
    verdict = signal.get("verdict")
    passed = signal.get("passed")

    if rc == 127 or signal.get("env_error"):
        cat, ev = "ENV_ERROR", f"rc={rc} (command/tooling not found)"
    elif signal.get("compile_failed"):
        cat, ev = "SYNTAX_FAIL", "candidate did not compile"
    elif verdict == "DRIFT":
        cat, ev = "STALE_KNOWLEDGE", "witness DRIFT: a source changed"
    elif verdict == "UNVERIFIABLE":
        cat, ev = "UNVERIFIABLE", "grounding could not be confirmed"
    elif signal.get("correlation", 0.0) >= signal.get("collapse_threshold", 0.85):
        cat, ev = "LOW_DIVERSITY", f"correlation {signal.get('correlation')} >= collapse"
    elif signal.get("cache_stale"):
        cat, ev = "STALE_CACHE", "cited knowledge drifted since caching"
    elif signal.get("repeat_of"):
        cat, ev = "REPEAT_FAILURE", f"same known-bad as {signal.get('repeat_of')}"
    elif signal.get("oracle_false_accept"):
        cat, ev = "UNCALIBRATED_ORACLE", "oracle accepted a known-bad in calibration"
    elif passed is False:
        cat, ev = "LOGIC_FAIL", "oracle rejected the candidate"
    elif signal.get("cache_hit"):
        cat, ev = "REPEAT_TASK", "oracle-certified fact already banked"
    elif passed is True:
        cat, ev = "NONE", "accepted"
    else:
        cat, ev = "UNKNOWN", str(signal)[:120]
    return Friction(category=cat, stage=stage, evidence=ev)


def route(friction: Friction) -> Route:
    """Dispatch to the best-in-class cog. UNKNOWN/NONE route honestly (triage /
    no-op), never to a guessed handler."""
    if friction.category == "NONE":
        handler, action = ("none", "accepted, nothing to route")
    else:
        handler, action = HANDLERS.get(friction.category, UNKNOWN)
    receipt = hashlib.sha256(
        "|".join([friction.category, friction.stage, handler, friction.evidence]).encode()
    ).hexdigest()[:16]
    return Route(category=friction.category, handler=handler, action=action, receipt=receipt)


def flow(signals: list[dict]) -> list[Route]:
    """The natural algorithmic flow: each friction routed to where it is handled
    best, in one pass. This is what makes the organs an engine, not a bag of cogs."""
    return [route(classify(s)) for s in signals]


def handled_categories() -> set[str]:
    return set(HANDLERS)
