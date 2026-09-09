"""Canonical Bulletin upload-response metadata checks."""
from __future__ import annotations

from urllib.parse import quote, urlsplit


def _same_media(value: object, row: dict) -> bool:
    return _media_mismatch_fields(value, row) == []


def _media_mismatch_fields(value: object, row: dict) -> list[str]:
    if type(value) is not dict:
        return ["media"]
    mismatches = []
    if value.get("id") != row["expected_media_id"]:
        mismatches.append("id")
    media_type = value.get("media_type")
    if media_type != row["media_type"]:
        mismatches.append("media_type")
    legacy_type = value.get("type")
    if legacy_type is not None and legacy_type != media_type:
        mismatches.append("type")
    if value.get("kind") != row["kind"]:
        mismatches.append("kind")
    if value.get("bytes") != row["bytes"]:
        mismatches.append("bytes")
    url = value.get("url")
    try:
        parsed = urlsplit(url) if type(url) is str else None
    except ValueError:
        mismatches.append("url")
        return mismatches
    expected_path = f"/v1/media/{quote(row['expected_media_id'], safe='')}"
    if (parsed is None or parsed.scheme or parsed.netloc
            or parsed.path != expected_path or parsed.query or parsed.fragment):
        mismatches.append("url")
    return mismatches
