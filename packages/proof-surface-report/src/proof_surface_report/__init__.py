"""proof-surface-report: render proof-surface JSON artifacts as Markdown.

An adapter that validates a proof-surface packet or EMET witness receipt against
the shared ``proof-surface`` contract package and renders a reviewer-facing
Markdown handoff. It rejects authority-shaped wording and makes no certification,
trust, or release decision.
"""
from __future__ import annotations

from .core import (
    load_artifact,
    main,
    reject_authority_language,
    render_report,
    validate_packet,
    validate_receipt,
)

__all__ = [
    "load_artifact",
    "main",
    "reject_authority_language",
    "render_report",
    "validate_packet",
    "validate_receipt",
]

__version__ = "0.1.0"
