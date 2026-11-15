"""Tests for the AudioArtifactOrgan -- the membrane's second sense."""

from __future__ import annotations

import hashlib
import io
import wave
from array import array

import pytest

from coherence_membrane.observation import Status
from coherence_membrane.organs.audio import AudioArtifactOrgan, audio_envelope_hash


def _wav(samples, channels=1, rate=8000, sampwidth=2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(array("h", samples).tobytes())
    return buf.getvalue()


def test_observe_wav_bytes():
    wav = _wav([((i % 100) - 50) * 200 for i in range(2000)])
    obs = AudioArtifactOrgan().observe(wav)[0]
    assert obs.organ == "audio-artifact"
    assert obs.status == Status.PASS
    assert obs.data["identity_sha256"] == hashlib.sha256(wav).hexdigest()
    assert obs.data["format"] == "wav"
    assert obs.data["channels"] == 1 and obs.data["sample_rate"] == 8000
    assert obs.data["decoded"] is True
    assert len(obs.data["perceptual_audio_hash"]) == 16


def test_observe_is_reproducible():
    wav = _wav([((i % 64) - 32) * 300 for i in range(1024)])
    organ = AudioArtifactOrgan()
    a = organ.observe(wav)[0]
    b = organ.observe(wav)[0]
    assert a.data["identity_sha256"] == b.data["identity_sha256"]
    assert a.data["perceptual_audio_hash"] == b.data["perceptual_audio_hash"]


def test_different_sound_has_different_fingerprint():
    quiet = _wav([0] * 2000)
    loud = _wav([((i % 50) - 25) * 1000 for i in range(2000)])
    fa = AudioArtifactOrgan().observe(quiet)[0].data["perceptual_audio_hash"]
    fb = AudioArtifactOrgan().observe(loud)[0].data["perceptual_audio_hash"]
    assert fa != fb


def test_non_wav_is_identity_only():
    obs = AudioArtifactOrgan().observe(b"this is not a wav file")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["perceptual_audio_hash"] is None
    assert obs.data["identity_sha256"] == hashlib.sha256(b"this is not a wav file").hexdigest()


def test_unsupported_sample_width_is_identity_only():
    wav8 = _wav([0, 1, 2, 3] * 100, sampwidth=1)  # 8-bit unsupported for hashing
    obs = AudioArtifactOrgan().observe(wav8)[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["perceptual_audio_hash"] is None
    assert obs.data["format"] == "wav"  # still recognised + identity witnessed


def test_missing_path_is_unverified(tmp_path):
    obs = AudioArtifactOrgan().observe(tmp_path / "nope.wav")[0]
    assert obs.status == Status.UNVERIFIED
    assert obs.data["decoded"] is False


def test_envelope_hash_of_empty_is_zero():
    assert audio_envelope_hash([]) == 0


def test_selftest_passes():
    result = AudioArtifactOrgan().selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 4


def test_organ_does_not_mutate_input_file(tmp_path):
    wav = _wav([0, 100, -100, 50] * 50)
    p = tmp_path / "clip.wav"
    p.write_bytes(wav)
    before = p.read_bytes()
    AudioArtifactOrgan().observe(p)
    assert p.read_bytes() == before  # inert
