"""witness — coherence membrane and temporal perception.

The apparatus constructs existence. The witness observes whether what
exists matches what was constructed. The two are architecturally separate.

Public API:
  membrane: anchor, verify, coherence, refuse, corroborate, audit, selftest
  organs:   watch, observe, confirm
  monitor:  report, reanchor
"""
from .membrane import (
    anchor,
    audit,
    coherence,
    corroborate,
    refuse,
    selftest,
    verify,
    witness_status,
)
from .monitor import reanchor, report
from .organs import confirm, observe, watch

__all__ = [
    "anchor", "verify", "coherence", "refuse", "corroborate", "audit",
    "selftest", "witness_status",
    "watch", "observe", "confirm",
    "report", "reanchor",
]
