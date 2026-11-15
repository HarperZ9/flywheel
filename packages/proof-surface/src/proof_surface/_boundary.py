"""The non-promotion / uniqueness boundary appended to every proof-surface output.

Uniform honesty discipline across the family: a packet records and verifies
evidence; it promotes no natural law, theorem, or safety result, and it never
asserts market uniqueness as fact. Stdlib-only.
"""

from __future__ import annotations

UNIQUENESS_DEFAULT = "HYPOTHESIS_ONLY"
NON_PROMOTION_STATEMENT = (
    "This packet promotes no natural law, theorem, biological, material, financial, "
    "or safety result; it records and verifies evidence, and marks what it cannot "
    "verify as UNVERIFIABLE."
)


def render_boundary() -> list[str]:
    """Markdown lines for the standard non-promotion / uniqueness boundary footer."""
    return [
        "",
        "## Boundary",
        "",
        f"- {NON_PROMOTION_STATEMENT}",
        "- Promoted natural laws: none.",
        f"- Uniqueness claim status: {UNIQUENESS_DEFAULT} (not asserted as fact).",
    ]
