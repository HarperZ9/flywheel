from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .provenance import reject_source_tokens, sha256_file, sha256_text

PROFILE_SCHEMA = "rowan.local-tts-base-profiles/v1"
PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
MAX_BASE_PROFILE_COUNT = 4


@dataclass(frozen=True)
class BaseVoiceProfile:
    id: str
    reference_audio_path: Path
    reference_audio_sha256: str
    reference_text: str
    reference_text_sha256: str
    x_vector_only_mode: bool
    source: dict[str, Any]
    config_path: Path
    config_sha256: str

    def manifest(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "reference_audio_path": str(self.reference_audio_path),
            "reference_audio_sha256": self.reference_audio_sha256,
            "reference_text_sha256": self.reference_text_sha256,
            "x_vector_only_mode": self.x_vector_only_mode,
            "source": self.source,
            "config_path": str(self.config_path),
            "config_sha256": self.config_sha256,
        }


def load_base_voice_profiles(
    config_path: Path | str,
    *,
    max_profiles: int = MAX_BASE_PROFILE_COUNT,
) -> dict[str, BaseVoiceProfile]:
    path = Path(config_path).resolve()
    if max_profiles < 1 or max_profiles > MAX_BASE_PROFILE_COUNT:
        raise ValueError(f"max_profiles must be between 1 and {MAX_BASE_PROFILE_COUNT}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"profile config schema must be {PROFILE_SCHEMA}")
    rows = raw.get("profiles")
    if not isinstance(rows, list) or not rows:
        raise ValueError("profile config must contain profiles")
    if len(rows) > max_profiles:
        raise ValueError("too many profiles for configured bound")
    profiles: dict[str, BaseVoiceProfile] = {}
    config_sha = sha256_file(path)
    for row in rows:
        profile = _parse_profile(path, config_sha, row)
        if profile.id in profiles:
            raise ValueError(f"duplicate profile id: {profile.id}")
        profiles[profile.id] = profile
    return profiles


def _parse_profile(config_path: Path, config_sha: str, row: Any) -> BaseVoiceProfile:
    if not isinstance(row, dict):
        raise ValueError("profile row must be an object")
    profile_id = _string(row, "id")
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise ValueError("profile id must be a stable lowercase identifier")
    ref_audio = _local_path(config_path.parent, _string(row, "reference_audio_path"))
    expected_audio_sha = _sha_value(_string(row, "reference_audio_sha256"))
    observed_audio_sha = sha256_file(ref_audio)
    if observed_audio_sha != expected_audio_sha:
        raise ValueError("reference audio hash mismatch")
    ref_text = _string(row, "reference_text")
    if not ref_text.strip():
        raise ValueError("reference_text must not be empty")
    reject_source_tokens("reference_text", ref_text)
    expected_text_sha = _sha_value(_string(row, "reference_text_sha256"))
    observed_text_sha = sha256_text(ref_text)
    if observed_text_sha != expected_text_sha:
        raise ValueError("reference text hash mismatch")
    x_vector_only_mode = row.get("x_vector_only_mode", False)
    if not isinstance(x_vector_only_mode, bool):
        raise ValueError("x_vector_only_mode must be a boolean")
    source = row.get("source")
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    for key in ("kind", "repo_id", "revision", "variant_id"):
        value = source.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"source.{key} must be a non-empty string")
    return BaseVoiceProfile(
        id=profile_id,
        reference_audio_path=ref_audio,
        reference_audio_sha256=observed_audio_sha,
        reference_text=ref_text,
        reference_text_sha256=observed_text_sha,
        x_vector_only_mode=x_vector_only_mode,
        source=dict(source),
        config_path=config_path,
        config_sha256=config_sha,
    )


def _string(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _sha_value(value: str) -> str:
    lowered = value.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", lowered):
        raise ValueError("sha256 values must be lowercase hex")
    return lowered


def _local_path(base: Path, value: str) -> Path:
    lowered = value.lower()
    if "://" in lowered or lowered.startswith("file:") or value.startswith("\\\\"):
        raise ValueError("reference_audio_path must be a local path")
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValueError("reference_audio_path must point to an existing local file")
    return resolved
