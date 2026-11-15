from __future__ import annotations

import hashlib
import json
import math
import re

CANONICALIZATION = "json-sorted-compact-lf"
_SHA256_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class CanonicalJSONError(ValueError):
    pass


def canonical_json_text(value: object) -> str:
    _validate_canonical_value(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise CanonicalJSONError(str(exc)) from exc


def canonical_json_bytes(value: object) -> bytes:
    return canonical_json_text(value).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_sha256(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def is_sha256_ref(value: object) -> bool:
    return isinstance(value, str) and _SHA256_REF_RE.fullmatch(value) is not None


def _validate_canonical_value(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError("canonical JSON object keys must be strings")
            _validate_canonical_value(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_canonical_value(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise CanonicalJSONError("canonical JSON cannot encode NaN or Infinity")
