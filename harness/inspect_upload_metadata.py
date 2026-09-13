from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
import re


MAX_INSPECT_UPLOAD_BYTES = 16 * 1024 * 1024
INSPECT_DATA_REF_PREFIX = "data_inspect.source:"
INSPECT_MEDIA_TYPES = {"application/vnd.flywheel.inspect-json", "application/json"}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def inspect_data_ref(sha256: str) -> str:
    return INSPECT_DATA_REF_PREFIX + sha256[:32]


def valid_inspect_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def sanitize_inspect_filename(value: object) -> str:
    if value in (None, ""):
        return ""
    if type(value) is not str or len(value) > 160:
        raise ValueError
    lowered = value.lower()
    if (lowered.startswith("file:") or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
            or "/" in value or "\\" in value or ":" in value):
        raise ValueError
    if PureWindowsPath(value).name != value or PurePosixPath(value).name != value:
        raise ValueError
    if value in {".", ".."}:
        raise ValueError
    return value


def inspect_operation(sha256: str, byte_length: int, filename: str = "") -> dict:
    source = {"kind": "client-upload", "format": "inspect-json",
              "sha256": sha256, "byte_length": byte_length}
    name = sanitize_inspect_filename(filename)
    if name:
        source["filename"] = name
    return {"source": source, "data_refs": [inspect_data_ref(sha256)],
            "credential_refs": []}


def validate_inspect_operation(value: dict) -> None:
    source = value.get("source")
    if type(source) is not dict:
        raise ValueError
    allowed = {"kind", "format", "sha256", "byte_length", "filename"}
    if set(source) - allowed:
        raise ValueError
    sha, byte_length = source.get("sha256"), source.get("byte_length")
    if (source.get("kind") != "client-upload"
            or source.get("format") != "inspect-json"
            or not valid_inspect_sha256(sha)
            or type(byte_length) is not int
            or not 1 <= byte_length <= MAX_INSPECT_UPLOAD_BYTES
            or value.get("data_refs") != [inspect_data_ref(sha)]
            or value.get("credential_refs") != []):
        raise ValueError
    sanitize_inspect_filename(source.get("filename", ""))
