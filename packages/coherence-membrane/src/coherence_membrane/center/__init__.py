"""center -- the neutral-center reconcile, as the spine's operation.

A human NAMES and weights a criterion; a subject is rendered into >=2 perceptible forms; two minds
with different perception reconcile it toward its telos against that named criterion; the project's
own Certificate carries the witnessed verdict (criterion + scores + winner in its evidence). The
minds and judge are pluggable interfaces (default stubs; live engine organs -- generate/perceive -- and
a model judge drop in behind them via `adapters`). This is the engine's *operation*, on the spine.
"""
from ..certificate import Certificate, Verdict
from .criterion import CriterionSpec
from .minds import Mind, StubMind
from .judge import Judge, StubJudge, DIMENSIONS
from .loop import reconcile_at_center, witness_candidates, winner_of, scores_of, criterion_of

__all__ = ["CriterionSpec", "Certificate", "Verdict", "Mind", "StubMind", "Judge", "StubJudge",
           "DIMENSIONS", "reconcile_at_center", "witness_candidates",
           "winner_of", "scores_of", "criterion_of"]
