"""AI4Science promotion gates: no unmeasured / unreproduced / unreviewed discovery.

Harvest of dogfood pass 0104. The three gates it names, made machine-checkable:
reject an unmeasured discovery claim, require independent reproduction, and
require human review (no open objection) before a peer-reviewed rung.
"""

from __future__ import annotations

from typing import Any

from .._validate import Issue

_NEEDS_MEASUREMENT = {"MEASURED", "REPRODUCED", "PEER_REVIEWED"}
_NEEDS_REPRODUCTION = {"REPRODUCED", "PEER_REVIEWED"}


def validate_promotion_gates(data: dict[str, Any], issues: list[Issue]) -> None:
    promotion = data.get("promotion")
    measurement = (
        data.get("measurement") if isinstance(data.get("measurement"), dict) else {}
    )
    reproduction = (
        data.get("reproduction") if isinstance(data.get("reproduction"), dict) else {}
    )
    objections = data.get("reviewer_objections")
    if promotion in _NEEDS_MEASUREMENT and measurement.get("measured") is not True:
        issues.append(
            Issue(
                "$.promotion",
                f"an unmeasured claim may not be promoted to {promotion} "
                "(reject unmeasured discovery claim)",
            )
        )
    if (
        promotion in _NEEDS_REPRODUCTION
        and reproduction.get("status") != "INDEPENDENTLY_REPRODUCED"
    ):
        issues.append(
            Issue(
                "$.promotion",
                f"promotion to {promotion} requires reproduction status "
                "INDEPENDENTLY_REPRODUCED",
            )
        )
    if promotion == "PEER_REVIEWED" and _has_open_objection(objections):
        issues.append(
            Issue(
                "$.promotion",
                "an open reviewer objection blocks peer-reviewed promotion "
                "(require human review)",
            )
        )


def _has_open_objection(objections: Any) -> bool:
    return isinstance(objections, list) and any(
        isinstance(o, dict) and o.get("status") == "open" for o in objections
    )
