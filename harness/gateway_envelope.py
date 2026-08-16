"""Pure parsing of complete final gateway authorization envelopes."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .evidence_json import strict_load_json
from .gateway_operation import (
    CanonicalOperation, GatewayOperationError, REQUEST_SCHEMA,
    canonicalize_operation,
)
from .gateway_secret_boundary import validate_no_raw_secrets
from .journey_types import JOURNEY_REF_PATTERN, SHA256_PATTERN
from .operation_grants import GRANT_REF_PATTERN

_BASE_FIELDS = frozenset((
    "schema", "journey_ref", "expected_event_head", "client_request_id",
    "grant_ref",
))
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


@dataclass(frozen=True)
class GatewayAuthorizationEnvelope:
    action: str
    journey_ref: str
    expected_event_head: str
    client_request_id: str
    grant_ref: str
    operation: CanonicalOperation


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def parse_gateway_envelope(
        action: str, raw: bytes | str) -> GatewayAuthorizationEnvelope:
    """Validate the complete final request without filesystem side effects."""
    try:
        body = strict_load_json(raw, max_bytes=1_048_576, max_depth=16)
        if type(body) is not dict or body.get("schema") != REQUEST_SCHEMA:
            raise ValueError
        if (not _matches(JOURNEY_REF_PATTERN, body.get("journey_ref"))
                or not _matches(SHA256_PATTERN, body.get("expected_event_head"))
                or not _matches(_REQUEST_ID, body.get("client_request_id"))
                or not _matches(GRANT_REF_PATTERN, body.get("grant_ref"))):
            raise ValueError
        operation_value = {
            key: value for key, value in body.items() if key not in _BASE_FIELDS
        }
        validate_no_raw_secrets(body)
        operation = canonicalize_operation(action, operation_value)
        if set(body) != _BASE_FIELDS | set(operation_value):
            raise ValueError
        return GatewayAuthorizationEnvelope(
            action, body["journey_ref"], body["expected_event_head"],
            body["client_request_id"], body["grant_ref"], operation,
        )
    except GatewayOperationError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise GatewayOperationError("INVALID_REQUEST") from None
