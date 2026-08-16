"""One bounded, non-echoing raw-secret boundary for gateway requests."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlsplit

from .bundle import scan_for_secrets

_SECRET_FIELDS = frozenset((
    "api_key", "access_token", "refresh_token", "token", "password",
    "secret", "credential", "credentials", "private_key",
    "authorization", "proxy_authorization", "cookie", "set_cookie",
    "environment", "env",
))
_SAFE_HANDLE_FIELDS = frozenset(("credential_ref", "credential_refs"))
_HEADER = re.compile(
    r"(?i)(?:^|[\r\n])\s*(?:authorization|proxy-authorization|cookie|"
    r"set-cookie)\s*:")
_AUTH_VALUE = re.compile(r"(?i)(?:^|\s)(?:bearer|basic)\s+\S+")
_SECRET_SWITCH = re.compile(
    r"^(?:(?i:--?(?:api[-_]?key|access[-_]?token|refresh[-_]?token|token|"
    r"password|secret|credential|private[-_]?key|authorization|cookie|"
    r"header|user|proxy[-_]?user))|-[Hub])(?:=|\Z)")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:^|\s)(?:[A-Z0-9_]*?(?:API_KEY|ACCESS_TOKEN|REFRESH_TOKEN|"
    r"PASSWORD|SECRET|PRIVATE_KEY|CREDENTIAL)|api[-_]?key|token)\s*=")
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_CREDENTIAL_REF = re.compile(r"cred_[0-9a-f]{32}\Z")


def _invalid() -> None:
    from .gateway_operation import GatewayOperationError
    raise GatewayOperationError("INVALID_REQUEST")


def _secret_name(value: str) -> bool:
    name = value.lower().replace("-", "_")
    return name in _SECRET_FIELDS or name.endswith((
        "_api_key", "_access_token", "_refresh_token", "_password",
        "_secret", "_credential", "_private_key", "_token",
    ))


def _decoded(value: str) -> str:
    current = value
    for _ in range(3):
        if not _PERCENT_ESCAPE.search(current):
            break
        try:
            decoded = unquote(current, errors="strict")
        except (UnicodeError, ValueError):
            _invalid()
        if decoded == current:
            break
        current = decoded
        if len(current) > 65_536:
            _invalid()
    return current


def _url_has_secret(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            return True
        fragments = [parsed.query, parsed.fragment]
        if "?" in parsed.fragment:
            fragments.append(parsed.fragment.partition("?")[2])
        return any(_secret_name(name) for component in fragments
                   for name, _ in parse_qsl(component, keep_blank_values=True))
    except (TypeError, ValueError, UnicodeError):
        return True


def _secret_string(value: str) -> bool:
    decoded = _decoded(value)
    if scan_for_secrets(decoded):
        return True
    if (_HEADER.search(decoded) or _AUTH_VALUE.search(decoded)
            or _SECRET_ASSIGNMENT.search(decoded)
            or _SECRET_SWITCH.search(decoded)):
        return True
    return _url_has_secret(decoded)


def validate_no_raw_secrets(value: object) -> None:
    """Reject secret-bearing JSON shapes with one fixed public failure."""
    remaining = [4096]

    def visit(item: object, key: str, depth: int) -> None:
        remaining[0] -= 1
        if remaining[0] < 0 or depth > 16:
            _invalid()
        if type(item) is dict:
            for name, child in item.items():
                if (type(name) is not str or len(name) > 512
                        or name not in _SAFE_HANDLE_FIELDS
                        and _secret_name(_decoded(name))):
                    _invalid()
                visit(child, name, depth + 1)
            return
        if type(item) is list:
            for index, child in enumerate(item):
                if (index and type(item[index - 1]) is str
                        and _SECRET_SWITCH.fullmatch(_decoded(item[index - 1]))):
                    _invalid()
                visit(child, key, depth + 1)
            return
        if type(item) is str:
            if (len(item) > 65_536
                    or key in _SAFE_HANDLE_FIELDS
                    and _CREDENTIAL_REF.fullmatch(item) is None
                    or key not in _SAFE_HANDLE_FIELDS and _secret_string(item)):
                _invalid()
            return
        if item is None or type(item) in (bool, int, float):
            return
        _invalid()

    visit(value, "", 0)
