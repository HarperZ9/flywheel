"""center — the live neutral-center reconcile (Neutral Center v1).

A human NAMES and weights a criterion; a subject is rendered into >=2 perceptible forms; two minds
with different perception reconcile it toward its telos against that named criterion; a witnessed
Certificate naming the criterion is emitted. Grounded in the transpile-conservation principle
(faithfulness is to a named criterion; the witness is external) and the reconcile spine.

v1: the human holds the criterion seat; the minds and judge are pluggable interfaces (default = stubs;
the live engine organs — atelier=generate, eye=perceive — drop in behind the same interfaces later).
"""
from .criterion import CriterionSpec
from .certificate import Certificate, Verdict
from .minds import Mind, StubMind
from .judge import Judge, StubJudge
from .loop import reconcile_at_center

__all__ = ["CriterionSpec", "Certificate", "Verdict", "Mind", "StubMind",
           "Judge", "StubJudge", "reconcile_at_center"]
