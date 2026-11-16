"""Public standards registry validation entrypoint."""
from __future__ import annotations

from typing import Any

from .standards_profile import validate_profile_object


def validate_profile(profile: object) -> dict[str, Any]:
    """Validate a data-only standards profile without assessing conformance."""
    try:
        return validate_profile_object(profile)
    except Exception as exc:  # pragma: no cover - fail-closed guard
        return {
            "schema": "flywheel.standards-profile-validation/v1",
            "verdict": "INVALID",
            "profile": None,
            "assessment": "not_assessed",
            "errors": [{"path": "$", "code": "validator_error",
                        "message": str(exc)}],
            "gaps": [],
            "does_not_prove": (
                "Profile validation failed closed and does not prove legal "
                "compliance, source truth, certification, or approval."),
        }
