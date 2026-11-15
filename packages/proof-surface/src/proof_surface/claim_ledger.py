"""Claim ledger: traceable multi-agent memory with calibrated uncertainty.

The ledger records claims made by agents (or principals), each with a
source-provided confidence score and explicit dependency/conflict links.
It is an accountability layer -- it surfaces provenance, confidence, and
conflict for human review.  It does NOT adjudicate truth.

Design principles
-----------------
* Honest confidence: the confidence field is SOURCE-PROVIDED.  The tool
  surfaces it unchanged; it never adjusts or normalises it.  A claim
  with confidence=0.0 is logged, not filtered.
* Referential integrity: depends_on and conflicts_with entries must
  reference existing claim_ids within the same ledger.  Dangling
  references are validation errors.
* Uniqueness: claim_id values must be unique within a ledger.
* Cycle safety: trace_dependents uses an explicit visited set; any cycle
  in depends_on links terminates traversal cleanly without infinite loop.
* Advisory-never-authority: these functions REPORT structural findings
  (low confidence, conflicts, transitive dependents).  They never grant
  authority, modify the ledger, or get injected into a model as trusted
  state.
* Forbidden-field guard: the same 16-key FORBIDDEN_FIELDS set used by
  every other proof-surface contract is applied recursively, fail-closed.
* additionalProperties:false at every object level.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ._validate import Issue, reject_unknown, require_const, require_text

LEDGER_VERSION = "0.1"

# Top-level field allowlist.
ROOT_FIELDS = {"ledger_version", "claims"}

# Claim field allowlist.
CLAIM_FIELDS = {
    "claim_id",
    "statement",
    "source",
    "confidence",
    "evidence_refs",
    "depends_on",
    "conflicts_with",
}

# Field NAMES lifted verbatim from the excluded warden-prefire capsule/meta.
# Identical set to every other proof-surface contract.  Applied recursively;
# fail-closed.
FORBIDDEN_FIELDS = {
    "federal_appointment",
    "oversight_principals",
    "operator_role",
    "judgment_owner",
    "proof_policy",
    "policy_boundary",
    "authorization_context_mode",
    "model_authorization_behavior",
    "guardrail_posture",
    "consume_verified_native_state",
    "lossy_neutral_embedded_state",
    "sovereignty_capsule",
    "self_applicable",
    "recursion_depth",
    "prefire",
    "run_state",
}


# ---------------------------------------------------------------------------
# Public API -- validation
# ---------------------------------------------------------------------------


def validate_claim_ledger(data: Any) -> list[Issue]:
    """Validate a claim-ledger document.  Returns [] iff valid."""
    if not isinstance(data, dict):
        return [Issue("$", "expected object")]

    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "ledger_version", LEDGER_VERSION, issues)

    claims = data.get("claims")
    if not isinstance(claims, list):
        issues.append(Issue("$.claims", "expected array"))
        return issues

    # Validate individual claim shapes first.
    seen_ids: dict[str, int] = {}  # claim_id -> first-seen index
    for index, item in enumerate(claims):
        _validate_claim(item, index, issues)
        if isinstance(item, dict):
            cid = item.get("claim_id")
            if isinstance(cid, str) and cid.strip():
                if cid in seen_ids:
                    issues.append(
                        Issue(
                            f"$.claims[{index}].claim_id",
                            f"duplicate claim_id {cid!r} (first seen at index {seen_ids[cid]})",
                        )
                    )
                else:
                    seen_ids[cid] = index

    # Referential integrity: depends_on / conflicts_with must reference known ids.
    all_ids: set[str] = set(seen_ids)
    for index, item in enumerate(claims):
        if not isinstance(item, dict):
            continue
        _validate_ref_list(item, "depends_on", index, all_ids, issues)
        _validate_ref_list(item, "conflicts_with", index, all_ids, issues)

    return issues


# ---------------------------------------------------------------------------
# Public API -- analysis functions
# ---------------------------------------------------------------------------


def confidence_gate(ledger: dict[str, Any], threshold: float) -> list[str]:
    """Return claim_ids whose confidence is strictly below ``threshold``.

    This surfaces low-confidence claims for human review.  It does NOT
    remove or suppress them.  Confidence is source-provided; this function
    only compares against the caller-supplied threshold.
    """
    result: list[str] = []
    for claim in ledger.get("claims", []):
        if not isinstance(claim, dict):
            continue
        cid = claim.get("claim_id")
        conf = claim.get("confidence")
        if not isinstance(cid, str) or not isinstance(conf, (int, float)):
            continue
        if conf < threshold:
            result.append(cid)
    return result


def find_conflicts(ledger: dict[str, Any]) -> list[tuple[str, str]]:
    """Return unordered pairs of claim_ids that declare a conflict.

    A conflict pair (A, B) is surfaced when:
      - A.conflicts_with contains B, OR
      - B.conflicts_with contains A, OR
      - both (conflict is symmetric either way).

    Each unordered pair appears at most once in the output.
    """
    pairs: set[frozenset[str]] = set()
    claims = ledger.get("claims", [])
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cid = claim.get("claim_id")
        if not isinstance(cid, str):
            continue
        conflicts = claim.get("conflicts_with", [])
        if not isinstance(conflicts, list):
            continue
        for other_id in conflicts:
            if isinstance(other_id, str) and other_id != cid:
                pairs.add(frozenset({cid, other_id}))
    return [tuple(sorted(pair)) for pair in pairs]  # type: ignore[return-value]


def trace_dependents(
    ledger: dict[str, Any],
    claim_id: str,
) -> list[str]:
    """Return all claim_ids that transitively depend on ``claim_id``.

    A claim C is a dependent of X if C.depends_on contains X (directly or
    transitively through the depends_on graph).

    Cycle-safe: any claim already in the visited set is skipped, so cycles
    in the depends_on graph terminate cleanly without infinite recursion.

    The seed ``claim_id`` itself is NOT included in the output.
    """
    # Build reverse adjacency: for each id Y, who depends directly on Y?
    reverse: dict[str, list[str]] = {}
    for claim in ledger.get("claims", []):
        if not isinstance(claim, dict):
            continue
        cid = claim.get("claim_id")
        if not isinstance(cid, str):
            continue
        deps = claim.get("depends_on", [])
        if not isinstance(deps, list):
            continue
        for dep_id in deps:
            if isinstance(dep_id, str):
                reverse.setdefault(dep_id, []).append(cid)

    # BFS from claim_id over the reverse graph (deque for O(1) dequeue).
    visited: set[str] = set()
    queue: deque[str] = deque([claim_id])
    while queue:
        current = queue.popleft()
        for dependent in reverse.get(current, []):
            if dependent not in visited:
                visited.add(dependent)
                queue.append(dependent)

    # Exclude the seed itself (it was never added to visited in our BFS).
    visited.discard(claim_id)
    return sorted(visited)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reject_forbidden(node: Any, path: str, issues: list[Issue]) -> None:
    """Recursively reject any key whose name appears in FORBIDDEN_FIELDS."""
    if isinstance(node, dict):
        for key in sorted(node):
            child = f"{path}.{key}"
            if key in FORBIDDEN_FIELDS:
                issues.append(Issue(child, "forbidden authorization-suppression field"))
            _reject_forbidden(node[key], child, issues)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_forbidden(item, f"{path}[{index}]", issues)


def _validate_claim(item: Any, index: int, issues: list[Issue]) -> None:
    base = f"$.claims[{index}]"
    if not isinstance(item, dict):
        issues.append(Issue(base, "expected object"))
        return
    reject_unknown(item, base, CLAIM_FIELDS, issues)
    # claim_id
    require_text(item, "claim_id", issues, f"{base}.claim_id")
    # statement
    require_text(item, "statement", issues, f"{base}.statement")
    # source
    require_text(item, "source", issues, f"{base}.source")
    # confidence: required number in [0.0, 1.0]
    conf = item.get("confidence")
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        issues.append(Issue(f"{base}.confidence", "expected number"))
    elif conf < 0.0 or conf > 1.0:
        issues.append(
            Issue(f"{base}.confidence", f"confidence {conf} out of range [0.0, 1.0]")
        )
    # evidence_refs: required array of strings
    erefs = item.get("evidence_refs")
    if not isinstance(erefs, list):
        issues.append(Issue(f"{base}.evidence_refs", "expected array"))
    else:
        for i, ref in enumerate(erefs):
            if not isinstance(ref, str):
                issues.append(Issue(f"{base}.evidence_refs[{i}]", "expected string"))
    # depends_on: required array of strings
    deps = item.get("depends_on")
    if not isinstance(deps, list):
        issues.append(Issue(f"{base}.depends_on", "expected array"))
    else:
        for i, dep in enumerate(deps):
            if not isinstance(dep, str):
                issues.append(Issue(f"{base}.depends_on[{i}]", "expected string"))
    # conflicts_with: required array of strings
    cfls = item.get("conflicts_with")
    if not isinstance(cfls, list):
        issues.append(Issue(f"{base}.conflicts_with", "expected array"))
    else:
        for i, cfl in enumerate(cfls):
            if not isinstance(cfl, str):
                issues.append(Issue(f"{base}.conflicts_with[{i}]", "expected string"))


def _validate_ref_list(
    item: dict[str, Any],
    field: str,
    index: int,
    all_ids: set[str],
    issues: list[Issue],
) -> None:
    """Check that every entry in item[field] is an existing claim_id."""
    base = f"$.claims[{index}]"
    refs = item.get(field, [])
    if not isinstance(refs, list):
        return  # shape error already reported by _validate_claim
    for i, ref_id in enumerate(refs):
        if isinstance(ref_id, str) and ref_id not in all_ids:
            issues.append(
                Issue(
                    f"{base}.{field}[{i}]",
                    f"dangling reference: claim_id {ref_id!r} does not exist in this ledger",
                )
            )
