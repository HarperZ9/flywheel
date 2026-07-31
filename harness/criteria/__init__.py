"""criteria -- the criterion object and its registry.

A criterion is data: hash-pinned, forkable, and readable by someone who never
runs this code. It is never runtime config, because config can be edited after a
miss and nobody sees it happen.
"""
from .spec import Criterion, DecisionRule, Domain, CriterionError  # noqa: F401
from .registry import (  # noqa: F401
    Registry, RegistryError, Incumbent, InvalidationCode,
)

__all__ = [
    "Criterion", "DecisionRule", "Domain", "CriterionError",
    "Registry", "RegistryError", "Incumbent", "InvalidationCode",
]
