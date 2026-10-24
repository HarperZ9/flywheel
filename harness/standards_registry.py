"""Public standards registry validation entrypoint."""
from __future__ import annotations

from typing import Any

from .standards_profile import validate_profile_object
from .standards_schema import VALIDATION_SCHEMA


def validate_profile(profile: object) -> dict[str, Any]:
    """Validate a data-only standards profile without assessing conformance."""
    try:
        return validate_profile_object(profile)
    except Exception as exc:  # pragma: no cover - fail-closed guard
        return {
            "schema": VALIDATION_SCHEMA,
            "verdict": "INVALID",
            "profile": None,
            "assessment": "not_assessed",
            "errors": [{"path": "$", "code": "validator_error",
                        "message": str(exc)}],
            "gaps": [],
            "scope": (
                "Validation stopped at a validator error and failed closed; the "
                "profile is treated as invalid and was not assessed."),
        }
