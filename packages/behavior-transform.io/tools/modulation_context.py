"""Request context for tracking modulations through the pipeline.

Stores per-request state using contextvars so modulation results
can be retrieved later for response demodulation.
"""

from __future__ import annotations

import contextvars
import uuid

from categories import DetectionResult

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)
_detection_result_var: contextvars.ContextVar[DetectionResult | None] = contextvars.ContextVar(
    "detection_result", default=None
)


def generate_request_id() -> str:
    """Generate a unique request ID for tracking through pipeline."""
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    """Set the current request ID in context."""
    _request_id_var.set(request_id)


def get_request_id() -> str:
    """Get the current request ID from context."""
    return _request_id_var.get()


def set_detection_result(result: DetectionResult) -> None:
    """Store detection result in context for response demodulation."""
    _detection_result_var.set(result)


def get_detection_result() -> DetectionResult | None:
    """Retrieve stored detection result."""
    return _detection_result_var.get()


def clear_context() -> None:
    """Clear request context after processing."""
    _request_id_var.set("")
    _detection_result_var.set(None)
