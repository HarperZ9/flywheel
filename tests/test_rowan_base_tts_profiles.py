from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from desktop.tool.rowan_tts.engines import FakeBasePromptEngine, load_base_voice_profiles
from desktop.tool.rowan_tts.jobs import RowanTtsState, ServiceError
from desktop.tool.rowan_tts.provenance import sha256_file, sha256_text


def test_profile_config_pins_reference_and_rejects_collisions(tmp_path: Path):
    ref = tmp_path / "ref.wav"
    _write_wav(ref)
    good = _profile_config(tmp_path, ref)

    profiles = load_base_voice_profiles(good, max_profiles=1)

    assert list(profiles) == ["rowan-lively02"]
    assert profiles["rowan-lively02"].reference_audio_sha256 == sha256_file(ref)
    assert profiles["rowan-lively02"].reference_text == "reference words"

    dup = _profile_config(tmp_path, ref, duplicate=True)
    with pytest.raises(ValueError, match="duplicate profile id"):
        load_base_voice_profiles(dup, max_profiles=4)

    extra = _profile_config(tmp_path, ref, second_id="rowan-other")
    with pytest.raises(ValueError, match="too many profiles"):
        load_base_voice_profiles(extra, max_profiles=1)

    remote = _profile_config(tmp_path, ref, reference_audio_path="https://example.test/ref.wav")
    with pytest.raises(ValueError, match="local path"):
        load_base_voice_profiles(remote, max_profiles=1)

    wrong_hash = _profile_config(tmp_path, ref, reference_audio_sha256="0" * 64)
    with pytest.raises(ValueError, match="reference audio hash mismatch"):
        load_base_voice_profiles(wrong_hash, max_profiles=1)


def test_fake_base_prompt_engine_reuses_bounded_profile_cache(tmp_path: Path):
    ref = tmp_path / "ref.wav"
    _write_wav(ref)
    profiles = load_base_voice_profiles(_profile_config(tmp_path, ref), max_profiles=1)
    engine = FakeBasePromptEngine(profiles=profiles, max_prompt_cache=1)
    state = RowanTtsState(engine=engine, out_dir=tmp_path / "out", token="test-token")
    try:
        first = state.submit({"text": "first", "profile": "rowan-lively02", "seed": 1})
        state.wait(first, 2)
        second = state.submit({"text": "second", "profile": "rowan-lively02", "seed": 2})
        state.wait(second, 2)

        first_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
        second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
        assert first_manifest["model"]["prompt_cache_hit"] is False
        assert first_manifest["model_observed"] is True
        assert first_manifest["model_observation_basis"] == "engine_metadata"
        assert second_manifest["model"]["prompt_cache_hit"] is True
        assert second_manifest["model"]["prompt_cache_size"] == 1
        assert second_manifest["model_observed"] is True
        assert second_manifest["model_observation_basis"] == "engine_metadata"
        assert second_manifest["model"]["profile"]["reference_audio_sha256"] == sha256_file(ref)
    finally:
        state.stop()


def test_base_profile_rejects_unknown_profile_and_voice_prompt(tmp_path: Path):
    ref = tmp_path / "ref.wav"
    _write_wav(ref)
    profiles = load_base_voice_profiles(_profile_config(tmp_path, ref), max_profiles=1)
    state = RowanTtsState(
        engine=FakeBasePromptEngine(profiles=profiles),
        out_dir=tmp_path / "out",
        token="test-token",
    )
    try:
        with pytest.raises(ServiceError) as unknown:
            state.submit({"text": "hello", "profile": "rowan-other"})
        assert unknown.value.status == 400
        assert unknown.value.code == "BAD_PROFILE"

        with pytest.raises(ServiceError) as prompted:
            state.submit({"text": "hello", "profile": "rowan-lively02", "voice_prompt": "ignored"})
        assert prompted.value.status == 400
        assert prompted.value.code == "BAD_VOICE_PROMPT"
    finally:
        state.stop()


def _profile_config(
    tmp_path: Path,
    ref: Path,
    *,
    duplicate: bool = False,
    second_id: str | None = None,
    reference_audio_path: str | None = None,
    reference_audio_sha256: str | None = None,
) -> Path:
    reference_text = "reference words"
    profile = {
        "id": "rowan-lively02",
        "reference_audio_path": reference_audio_path or str(ref),
        "reference_audio_sha256": reference_audio_sha256 or sha256_file(ref),
        "reference_text": reference_text,
        "reference_text_sha256": sha256_text(reference_text),
        "x_vector_only_mode": False,
        "source": {
            "kind": "qwen-voice-design-audition",
            "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            "revision": "5ecdb67327fd37bb2e042aab12ff7391903235d3",
            "variant_id": "lively_expressive_australian",
        },
    }
    profiles = [profile]
    if duplicate:
        profiles.append(dict(profile))
    if second_id:
        other = dict(profile)
        other["id"] = second_id
        profiles.append(other)
    path = tmp_path / f"profiles-{len(profiles)}.json"
    path.write_text(
        json.dumps({"schema": "rowan.local-tts-base-profiles/v1", "profiles": profiles}),
        encoding="utf-8",
    )
    return path


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x01" * 240)
