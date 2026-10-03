"""The typed refusal for an endpoint that needs an explicit model.

Pure data and one formatter: no I/O and no local imports, so reviewed modules
can import it at load time.
"""
from __future__ import annotations


class ModelSelectionRequired(ValueError):
    code = "MODEL_SELECTION_REQUIRED"
    status = 422

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.message = f"{endpoint} requires an explicit model selection"
        super().__init__(self.message)


def model_selection_response(exc: Exception) -> tuple[dict, int] | None:
    """The transport error body for a MODEL_SELECTION_REQUIRED refusal, else None."""
    if getattr(exc, "code", "") != "MODEL_SELECTION_REQUIRED":
        return None
    return {"schema": "flywheel.evidence-transport-error/v1",
            "error": {"code": "MODEL_SELECTION_REQUIRED",
                      "message": str(exc)}}, getattr(exc, "status", 422)
