"""One bounded, non-echoing raw-secret boundary for gateway requests."""
from __future__ import annotations

from .gateway_secret_validation import validate_no_raw_secrets as _validate


def validate_no_raw_secrets(value: object) -> None:
    try:
        _validate(value)
    except ValueError:
        from .gateway_operation import GatewayOperationError
        raise GatewayOperationError("INVALID_REQUEST") from None
