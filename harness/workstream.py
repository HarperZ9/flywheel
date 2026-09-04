"""workstream.py -- standings that compose across a dependency graph.

One receipt answers for one artifact. The formalization work now arriving does
not come as one artifact. A Fermat statement is reached through tens of thousands
of lemmas, a swarm submits proofs against a shared library, and the question that
decides whether the top of that stack means anything is what happens to a parent
whose child was withdrawn.

This module holds that rule and nothing else. An obligation carries the exact
statement that was checked, which kind of checker decided it, the pinned
environment it was decided in, and what it rests on. Its identity folds in the
identities of everything below it, so restating a lemma or moving a toolchain
version moves the identity of every obligation above it. No checker runs here.
workstream_run.py runs them, and keeping the two apart is what lets the
composition rule be tested on a machine with no proof assistant installed.

Four properties:

  1. DERIVED STANDING. An obligation is verified only when its own check passed
     and everything it rests on is settled. A green leaf under a red one reports
     blocked, never verified.
  2. DECLARED ASSUMPTIONS, NEVER HIDDEN ONES. An obligation nothing checked is an
     assumption. It satisfies its parent and it appears by name in the footprint
     the receipt carries. Lean reports the axioms a proof leaned on rather than
     forbidding them; this is the same move one level up.
  3. PINNED ENVIRONMENTS TRAVEL. Every environment reached from the goal lands in
     the receipt. A proof checked under one Mathlib and a reading taken on one
     instrument do not merge into a single unlabelled claim.
  4. does_not_prove IS DERIVED. workstream_receipt.py computes it from what
     actually settled, never from the caller, and never leaves it empty.
"""
from __future__ import annotations

from dataclasses import dataclass

from harness.evidence_json import canonical_sha256
from harness.verdict import Verdict

SCHEMA = "flywheel.workstream/v1"

# What kind of thing decided this obligation. The kind is part of the hashed
# identity because "the numbers agree" and "a proof assistant accepted it" are
# different evidence, and a receipt that blurs them is unpriceable.
CHECKS = {
    "lean": "a proof assistant accepted the statement in a pinned environment",
    "arithmetic": "the quantities were recomputed and agree inside a stated interval",
    "dimensional": "the units reduce and the relation is dimensionally sound",
    "citation": "a named source was read and says what the statement says it says",
    "schema": "an artifact validates against a named schema",
    "instrument": "a device receipt records the reading and the command that produced it",
    "assumed": "nothing checked this; it is carried as a declared assumption",
}

VERIFIED = "verified"
REFUTED = "refuted"
BLOCKED = "blocked"
UNDECIDED = "undecided"
UNVERIFIABLE = "unverifiable"
PENDING = "pending"
ASSUMED = "assumed"

STANDINGS = frozenset(
    (VERIFIED, REFUTED, BLOCKED, UNDECIDED, UNVERIFIABLE, PENDING, ASSUMED))

# An assumption satisfies its parent the way an axiom satisfies a Lean proof: the
# parent still composes, and the assumption is disclosed rather than erased.
_SATISFIED = frozenset((VERIFIED, ASSUMED))

_VERDICTS = frozenset(member.value for member in Verdict)
_MAX_OBLIGATIONS = 50_000
_MAX_DEPENDENCIES = 512
_MAX_TEXT = 20_000


class WorkstreamError(ValueError):
    """A malformed workstream. Raised before anything is settled."""


def _text(value: object, field: str, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise WorkstreamError(f"{field} must be a non-empty string under {limit} characters")
    return value


@dataclass(frozen=True)
class Obligation:
    """One thing that has to hold, and what it rests on.

    `statement` is the exact text that was checked, not a description of it. A
    receipt whose statement paraphrases what the checker saw cannot be re-derived
    by a stranger, which is the only kind of re-derivation worth having.
    """

    obligation_id: str
    statement: str
    check: str
    environment: str
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.obligation_id, "obligation_id")
        _text(self.statement, "statement", _MAX_TEXT)
        _text(self.environment, "environment")
        if self.check not in CHECKS:
            raise WorkstreamError(
                f"check must be one of {', '.join(sorted(CHECKS))}")
        if not isinstance(self.depends_on, tuple):
            raise WorkstreamError("depends_on must be a tuple of obligation ids")
        if len(self.depends_on) > _MAX_DEPENDENCIES:
            raise WorkstreamError(f"an obligation may rest on at most {_MAX_DEPENDENCIES} others")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise WorkstreamError("depends_on repeats an obligation id")
        for ref in self.depends_on:
            _text(ref, "depends_on entry")
        if self.obligation_id in self.depends_on:
            raise WorkstreamError(f"obligation {self.obligation_id} depends on itself")


def _ordered(nodes: dict[str, Obligation]) -> tuple[str, ...]:
    """Dependencies first. Iterative, because a proof stack gets deep."""
    order: list[str] = []
    state: dict[str, int] = {}
    for root in sorted(nodes):
        stack = [(root, False)]
        while stack:
            node_id, expanded = stack.pop()
            if expanded:
                state[node_id] = 2
                order.append(node_id)
                continue
            if state.get(node_id) == 2:
                continue
            if state.get(node_id) == 1:
                raise WorkstreamError(f"dependency cycle through {node_id}")
            state[node_id] = 1
            stack.append((node_id, True))
            for ref in reversed(nodes[node_id].depends_on):
                if state.get(ref) == 1:
                    raise WorkstreamError(f"dependency cycle through {ref}")
                if state.get(ref) != 2:
                    stack.append((ref, False))
    return tuple(order)


class Workstream:
    """A goal, the obligations under it, and the identities that bind them.

    Construction is where a workstream is refused: an unknown dependency, a
    cycle, a duplicate id, or a goal that is not present are all errors here
    rather than surprises during settlement.
    """

    def __init__(self, obligations: list[Obligation], goal: str) -> None:
        if not obligations or len(obligations) > _MAX_OBLIGATIONS:
            raise WorkstreamError(f"a workstream holds 1 to {_MAX_OBLIGATIONS} obligations")
        nodes: dict[str, Obligation] = {}
        for item in obligations:
            if not isinstance(item, Obligation):
                raise WorkstreamError("every entry must be an Obligation")
            if item.obligation_id in nodes:
                raise WorkstreamError(f"duplicate obligation id {item.obligation_id}")
            nodes[item.obligation_id] = item
        for item in obligations:
            for ref in item.depends_on:
                if ref not in nodes:
                    raise WorkstreamError(
                        f"obligation {item.obligation_id} rests on missing {ref}")
        if goal not in nodes:
            raise WorkstreamError(f"goal {goal} is not one of the obligations")
        self.nodes = nodes
        self.goal = goal
        self.order = _ordered(nodes)
        self.digests = self._digests()
        self.workstream_id = self.digests[goal]

    def _digests(self) -> dict[str, str]:
        """A Merkle identity per obligation, folding in what it rests on.

        Naming a dependency by its caller-chosen id would let two different
        lemmas share an identity. Folding in the dependency digest means the id
        of the goal witnesses the whole subtree under it, so a swapped lemma or a
        moved toolchain is visible at the top without reading the middle.
        """
        digests: dict[str, str] = {}
        for node_id in self.order:
            node = self.nodes[node_id]
            digests[node_id] = canonical_sha256({
                "statement": node.statement,
                "check": node.check,
                "environment": node.environment,
                "depends_on": [digests[ref] for ref in node.depends_on],
            })
        return digests

    def reachable(self, start: str | None = None) -> tuple[str, ...]:
        """Every obligation the goal actually rests on, itself included."""
        root = self.goal if start is None else start
        seen: set[str] = set()
        stack = [root]
        while stack:
            node_id = stack.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            stack.extend(self.nodes[node_id].depends_on)
        return tuple(sorted(seen))


def _own_standing(node: Obligation, result: object) -> tuple[str, str]:
    """What this obligation's own check says, before its dependencies weigh in."""
    if node.check == "assumed":
        if result is not None:
            raise WorkstreamError(
                f"assumption {node.obligation_id} cannot carry a check result")
        return ASSUMED, "carried as a declared assumption"
    if result is None:
        return PENDING, "no result submitted yet"
    value = result.value if isinstance(result, Verdict) else result
    if value not in _VERDICTS:
        raise WorkstreamError(f"result for {node.obligation_id} must be one of {sorted(_VERDICTS)}")
    if value == "FAIL":
        return REFUTED, "the check refused this statement"
    if value == "UNVERIFIABLE":
        return UNVERIFIABLE, "the checker could not run"
    if value == "UNDECIDED":
        return UNDECIDED, "the checker ran and declined to dispose"
    return VERIFIED, "the check passed"


def settle(workstream: Workstream, results: dict[str, object] | None = None) -> dict[str, dict]:
    """Derive a standing for every obligation, dependencies first.

    `results` carries what each checker returned, as a Verdict or its string. An
    obligation with no entry is pending, which is the ordinary state of most of a
    proof stack while it is being built.
    """
    supplied = dict(results or {})
    unknown = set(supplied) - set(workstream.nodes)
    if unknown:
        raise WorkstreamError(f"results name obligations that are not here: {sorted(unknown)[0]}")
    settled: dict[str, dict] = {}
    for node_id in workstream.order:
        node = workstream.nodes[node_id]
        standing, reason = _own_standing(node, supplied.get(node_id))
        # A refuted check is refuted whatever holds it up. Everything else waits
        # on its dependencies, so one withdrawn lemma blocks the stack above it
        # instead of leaving a parent reading verified over a hole.
        if standing != REFUTED:
            for ref in node.depends_on:
                below = settled[ref]["standing"]
                if below not in _SATISFIED:
                    standing = BLOCKED
                    reason = f"rests on {ref}, which is {below}"
                    break
        settled[node_id] = {
            "standing": standing,
            "reason": reason,
            "check": node.check,
            "environment": node.environment,
            "obligation_sha256": workstream.digests[node_id],
            "depends_on": list(node.depends_on),
        }
    return settled
