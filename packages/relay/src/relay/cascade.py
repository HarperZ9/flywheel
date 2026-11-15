"""cascade.py: answer typed questions locally first, escalate to the endpoint on ABSTAIN.

A local classifier returns a probability for a yes/no question. When the probability is at least
``threshold`` away from even (confidence = max(p, 1 - p)), the cascade answers locally; otherwise
it abstains and asks the endpoint. Each answer is appended to the session ledger with who answered
it and the local probability, so endpoint calls saved and every local answer stay checkable.

The first question shipped is "is this test failure flaky?" (``FlakyClassifier``): weighted cues
in the failure text, summed and squashed to a probability. Cues that name a code defect (import,
syntax, type and name errors, compile errors) outweigh transport cues, so a refused connection to
a server that crashed on an ImportError still reads as real.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

# (pattern, weight): positive pushes toward flaky, negative toward a real failure.
_CUES: tuple[tuple[str, float], ...] = (
    (r"timed? ?out|timeout|deadline exceeded", 1.6),
    (r"connection (reset|refused|aborted)|econnreset|econnrefused|broken pipe", 1.8),
    (r"address already in use|eaddrinuse|port \d+ (is )?(already )?in use", 2.2),
    (r"\b429\b|too many requests|rate.?limit", 2.2),
    (r"temporary failure in name resolution|getaddrinfo|\benotfound\b|name or service not known|\bdns\b", 2.0),
    (r"\b50[234]\b|service unavailable|bad gateway|gateway timeout", 1.4),
    (r"resource temporarily unavailable|eagain|too many open files|no space left|oom|out of memory|killed", 1.4),
    (r"race|data race|concurrent|deadlock|flaky|intermittent", 1.4),
    (r"database is locked|lock wait|could not obtain lock|file is being used|ebusy|resource busy", 1.6),
    (r"random seed|seed=|nondetermin", 0.8),
    (r"\b(modulenotfounderror|importerror)\b|cannot find module|no module named", -3.0),
    (r"\bsyntaxerror\b|unexpected token|parse error", -3.0),
    (r"\b(typeerror|attributeerror|nameerror|referenceerror|keyerror)\b", -2.2),
    (r"error\[e\d{4}\]|cannot find symbol|undefined: |compilation failed|does not compile|cannot use .* as", -3.0),
    (r"snapshot.*(mismatch|obsolete|failed)|snapshots? (do|does) not match", -2.0),
    (r"nullpointerexception|null pointer|nil pointer dereference|cannot read propert", -2.2),
    (r"assert(ion)?(error)?|expected .* (but )?(got|received|was)|left: .* right:|!=|does not equal", -1.2),
    (r"error: type|type error|mypy|tsc|is not assignable", -2.0),
)
_COMPILED = tuple((re.compile(p, re.IGNORECASE), w) for p, w in _CUES)
BIAS = -0.4   # real failures are the more common outcome


@dataclass(frozen=True)
class Answer:
    question: str
    value: bool
    probability: float
    decided_by: str          # "local" or "endpoint"


class FlakyClassifier:
    """p(flaky) for a failure tail. Deterministic; no model, no network."""

    name = "flaky-cues/1"

    def cues(self, log: str) -> list[tuple[str, float]]:
        return [(rx.pattern, w) for rx, w in _COMPILED if rx.search(log)]

    def probability(self, log: str) -> float:
        score = BIAS + sum(w for _, w in self.cues(log))
        return 1.0 / (1.0 + math.exp(-score))


class Cascade:
    """Ask ``local`` first; on ABSTAIN call ``endpoint(question, state) -> bool``.

    The default threshold, 1.0, sends nearly every question to the endpoint: the shipped
    flaky classifier missed its pre-stated bar (docs/CASCADE.md). Lower it only for a local
    classifier you have measured.
    """

    def __init__(self, local: FlakyClassifier, endpoint: Callable[[str, str], bool],
                 threshold: float = 1.0, ledger=None) -> None:
        if not 0.5 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0.5, 1.0]")
        self.local, self.endpoint, self.threshold, self.ledger = local, endpoint, threshold, ledger

    def ask(self, question: str, state: str) -> Answer:
        p = self.local.probability(state)
        if max(p, 1.0 - p) >= self.threshold:
            ans = Answer(question, p >= 0.5, round(p, 6), "local")
        else:
            ans = Answer(question, bool(self.endpoint(question, state)), round(p, 6), "endpoint")
        if self.ledger is not None:
            self.ledger.append("cascade", question, {
                "decided_by": ans.decided_by, "answer": ans.value,
                "local_probability": ans.probability, "local_model": self.local.name,
                "threshold": self.threshold})
        return ans
