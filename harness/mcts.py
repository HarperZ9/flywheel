"""mcts.py — M6 verifier-guided search (MCTS-lite over repair actions).

Where the cheap oracle gives DENSE signal (fraction of tests passing, proof
progress), a tree search over edit/repair actions can climb the reward gradient
to solutions the model's single-shot distribution would never sample. UCB1
selection balances exploration vs exploitation.

Honest scoping (HARNESS-ROADMAP M6 falsifier): beats best-of-N at matched budget
ONLY on task classes with dense cheap-oracle signal; on binary-only tasks (no
gradient to follow) it offers no improvement. The falsifier proves both halves.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Protocol

from .task import Task


@dataclass
class DenseResult:
    passed: bool
    reward: float
    output_hash: str


class DenseOracle(Protocol):
    def verify_dense(self, candidate: str, task: Task) -> DenseResult: ...


class RepairProposer(Protocol):
    def repair(self, candidate: str, feedback: DenseResult,
               task: Task) -> str: ...


@dataclass
class SearchNode:
    text: str
    reward: float
    visits: int = 0
    children: list["SearchNode"] = field(default_factory=list)
    parent: "SearchNode | None" = None

    def is_leaf(self) -> bool:
        return not self.children


def ucb1(child: SearchNode, parent_visits: int, c: float = 1.4) -> float:
    if child.visits == 0:
        return float("inf")
    exploit = child.reward
    explore = c * math.sqrt(math.log(max(parent_visits, 1)) / child.visits)
    return exploit + explore


def _frontier_distance(child: SearchNode, siblings: list[SearchNode]) -> float:
    """Option-diversity proxy (AWG causal-entropic-forces inspired): how far is
    this child from its already-explored siblings? A child opening a new region
    scores high; one clustering near explored siblings scores low. Measured as
    mean token-edit distance normalized to [0,1]."""
    if not siblings:
        return 1.0
    dists = []
    for s in siblings:
        if s is child:
            continue
        sa, sb = set(child.text.split()), set(s.text.split())
        union = sa | sb
        dists.append(1.0 - (len(sa & sb) / len(union)) if union else 0.0)
    return sum(dists) / len(dists) if dists else 1.0


def awg_ucb(child: SearchNode, parent_visits: int, siblings: list[SearchNode],
            c: float = 1.4, d: float = 0.5) -> float:
    """AWG-informed UCB: exploit + explore + option-diversity bonus. The
    diversity term (d * frontier_distance) prefers children that open new
    regions, resisting premature collapse — the causal-entropic-forces
    principle (keep future options open) as a selection heuristic. Set d=0 to
    recover standard UCB (the ablation)."""
    if child.visits == 0:
        return float("inf")
    return ucb1(child, parent_visits, c) + d * _frontier_distance(child, siblings)


def _select(root: SearchNode, c: float, selector=None) -> SearchNode:
    sel = selector or _std_selector
    node = root
    while not node.is_leaf():
        node = max(node.children,
                   key=lambda ch: sel(ch, node.visits, node.children, c))
    return node


def _std_selector(child, parent_visits, siblings, c):
    return ucb1(child, parent_visits, c)


def awg_selector(d: float = 0.5):
    def _sel(child, parent_visits, siblings, c):
        return awg_ucb(child, parent_visits, siblings, c, d=d)
    return _sel


def _backprop(node: SearchNode) -> None:
    n = node
    while n is not None:
        n.visits += 1
        n = n.parent


def verifier_guided_search(task: Task, dense_oracle: DenseOracle,
                           repair: RepairProposer, *, root_text: str,
                           budget: int, c: float = 1.4,
                           branching: int = 1,
                           selector=None) -> SearchNode:
    root_reward = dense_oracle.verify_dense(root_text, task)
    root = SearchNode(text=root_text, reward=root_reward.reward, visits=1)
    if root_reward.reward >= 1.0:
        return root
    best = root
    for _ in range(budget):
        leaf = _select(root, c, selector)
        for _ in range(branching):
            fb = dense_oracle.verify_dense(leaf.text, task)
            child_text = repair.repair(leaf.text, fb, task)
            cr = dense_oracle.verify_dense(child_text, task)
            child = SearchNode(text=child_text, reward=cr.reward,
                               parent=leaf)
            leaf.children.append(child)
            if cr.reward > best.reward:
                best = child
            _backprop(child)
            if cr.reward >= 1.0:
                return best
    return best
