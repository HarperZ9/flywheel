"""Shared strict JSON, public metadata, result, and contained-ref boundary."""
from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from .bundle import BundleError, safe_relative, scan_for_secrets
from .evidence_json import canonical_bytes, strict_load_json

ERROR_SCHEMA = "flywheel.evidence-transport-error/v1"
_SECRET_KEYS = frozenset(("api_key", "access_token", "refresh_token", "token",
    "password", "secret", "credential", "credentials", "private_key",
    "authorization", "cookie", "environment", "env"))
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"(?:\\\\|//)[^\\/\s]+[\\/][^\s]+")
_POSIX_PATH = re.compile(r"(?:^|[\s=(\[{,:;])/(?!/)[^\s]+|/"
    r"(?:Users|home|private|tmp|var|etc|root|opt|mnt|srv|usr|bin|sbin|lib|"
    r"Applications|Volumes|dev|proc|sys|run)(?:/|$)")
_FILE_URI = re.compile(r"(?i)(?<![A-Za-z0-9+.-])file:")


class TransportError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def error_response(exc: TransportError) -> tuple[dict, int]:
    return ({"schema": ERROR_SCHEMA,
             "error": {"code": exc.code, "message": exc.message}}, exc.status)


def parse_json(raw: bytes | str) -> dict:
    try:
        return strict_load_json(raw, max_bytes=1_048_576, max_depth=16)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        if "top-level" in str(exc):
            raise TransportError(
                "INVALID_REQUEST", "request body must be an object") from exc
        raise TransportError(
            "INVALID_JSON", "request body is not strict JSON") from exc


def exact_request(value: dict, expected, *, optional=()) -> dict:
    fields, optional_fields = frozenset(expected), frozenset(optional)
    extra, missing = value.keys() - fields, fields - value.keys() - optional_fields
    if extra:
        raise TransportError("UNKNOWN_FIELD", "request contains unsupported fields")
    if missing:
        raise TransportError("MISSING_FIELD", "request is missing required fields")
    return value


def _secret_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return (normalized in _SECRET_KEYS or
            normalized.endswith(("_api_key", "_private_key", "_password",
                                  "_secret", "_credential", "_token")))


def _https_url(value: str, parsed) -> bool:
    try:
        _ = parsed.port
        return (parsed.scheme.lower() == "https" and bool(parsed.hostname) and
                parsed.username is None and parsed.password is None and
                "\\" not in value and not any(char.isspace() for char in value))
    except ValueError:
        return False


def _parameter_names(parsed):
    fragment = parsed.fragment
    if "?" in fragment:
        fragment = fragment.partition("?")[2]
    elif not ("=" in fragment and "/" not in fragment.partition("=")[0]):
        fragment = ""
    return (name for component in (parsed.query, fragment)
            for name, _ in parse_qsl(component, keep_blank_values=True))


def public_ref(value: object) -> None:
    try:
        if type(value) is not str or scan_for_secrets(value):
            raise ValueError("reference is not public metadata")
        relative = safe_relative(value)
        if any(":" in part for part in relative.parts):
            raise ValueError("reference contains a URI or drive marker")
    except (BundleError, TypeError, ValueError) as exc:
        raise TransportError(
            "UNSAFE_METADATA", "metadata contains an unsafe reference", 422) from exc


def public_metadata(value: object) -> bool:
    if type(value) is dict:
        for key, item in value.items():
            key_is_url = public_metadata(key)
            if not key_is_url and _secret_key(key):
                raise TransportError(
                    "UNSAFE_METADATA", "metadata contains a secret-bearing field", 422)
            if key == "ref" or key.endswith(("_ref", "_refs")):
                for ref in item if type(item) is list else [item]:
                    public_ref(ref)
            else:
                public_metadata(item)
    elif type(value) is list:
        for item in value:
            public_metadata(item)
    elif type(value) is str:
        if scan_for_secrets(value):
            raise TransportError(
                "UNSAFE_METADATA", "metadata contains secret-shaped content", 422)
        if _FILE_URI.search(unquote(value)):
            raise TransportError(
                "UNSAFE_METADATA", "metadata contains an unsafe reference", 422)
        try:
            parsed = urlsplit(value)
        except ValueError:
            parsed = None
        if (parsed is not None and parsed.scheme.lower() == "https"
                and any(_secret_key(name) for name in _parameter_names(parsed))):
            raise TransportError(
                "UNSAFE_METADATA", "metadata contains a secret-bearing field", 422)
        if parsed is not None and _https_url(value, parsed):
            return True
        if (_WINDOWS_PATH.search(value) or _UNC_PATH.search(value)
                or _POSIX_PATH.search(value)):
            raise TransportError(
                "UNSAFE_METADATA", "metadata contains a host path", 422)
    return False


def public_result(action: str, value: dict) -> dict:
    try:
        if type(value) is not dict:
            raise TypeError("transport result must be an object")
        result = dict(value)
        if action == "check" and result.get("unverifiable_reason") and "reason" in result:
            result["reason"] = "registered oracle could not verify the submitted evidence"
        if action == "check" and result.get("unverifiable_reason") == "ORACLE_UNAVAILABLE":
            result.pop("oracle_id", None)
            result["does_not_prove"] = ["the requested claim was not checked"]
        if action in {"export", "recheck"} and "detail" in result:
            result["detail"] = "packet could not be verified from admitted evidence"
        result = strict_load_json(
            canonical_bytes(result), max_bytes=1_048_576, max_depth=32)
        public_metadata(result)
    except (TransportError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TransportError(
            "UNSAFE_RESULT", "evidence transport produced unsafe metadata", 500) from exc
    return result


def admitted_root(value: Path) -> Path:
    try:
        resolved = Path(value).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TransportError(
            "ROOT_UNAVAILABLE", "evidence root is unavailable", 500) from exc
    if not resolved.is_dir():
        raise TransportError("ROOT_UNAVAILABLE", "evidence root is unavailable", 500)
    return resolved


def relative_ref(ref: object) -> Path:
    try:
        return safe_relative(ref)
    except (BundleError, TypeError, ValueError) as exc:
        raise TransportError(
            "INVALID_REF", "reference must be public-safe and relative") from exc


def within_root(root: Path, ref: object, *, must_exist: bool) -> Path:
    rel = relative_ref(ref)
    candidate = root / rel
    try:
        resolved = candidate.resolve(strict=must_exist)
        contained = os.path.commonpath((os.path.normcase(str(root)),
            os.path.normcase(str(resolved)))) == os.path.normcase(str(root))
        if not contained:
            raise TransportError("INVALID_REF", "reference escapes the evidence root")
    except FileNotFoundError as exc:
        raise TransportError(
            "MISSING_REF", "referenced artifact does not exist", 404) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise TransportError("INVALID_REF", "reference cannot be admitted") from exc
    return root / rel


def json_ref_bytes(root: Path, ref: object) -> tuple[dict, bytes]:
    path = within_root(root, ref, must_exist=True)
    if not path.is_file():
        raise TransportError("INVALID_REF", "referenced artifact must be a file")
    try:
        raw = path.read_bytes()
        value = strict_load_json(raw, max_bytes=1_048_576, max_depth=32)
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TransportError(
            "INVALID_ARTIFACT", "referenced artifact is not strict JSON", 422) from exc
    if type(value) is not dict:
        raise TransportError(
            "INVALID_ARTIFACT", "referenced JSON must be an object", 422)
    public_metadata(value)
    return value, raw


def json_ref(root: Path, ref: object) -> dict:
    return json_ref_bytes(root, ref)[0]


def public_text(req: dict, name: str) -> str:
    value = req.get(name)
    if type(value) is not str or not value.strip():
        raise TransportError(
            "INVALID_METADATA", f"{name} must be a non-empty string", 422)
    public_metadata(value)
    return value
