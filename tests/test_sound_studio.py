"""The chime study must be an instrument, not a vibe: deterministic bytes
under one receipt, a valid WAV of the declared length, audible content,
and named refusals at the parameter fences."""

import base64
import io
import wave

from harness.sound_studio import RATE, compose_sound


def test_same_seed_composes_the_same_bytes():
    a = compose_sound(seed=58)
    b = compose_sound(seed=58)
    assert not a["refused"]
    assert a["receipt"]["wav_sha256"] == b["receipt"]["wav_sha256"]
    assert a["receipt"]["score_sha256"] == b["receipt"]["score_sha256"]
    c = compose_sound(seed=59)
    assert c["receipt"]["wav_sha256"] != a["receipt"]["wav_sha256"]


def test_the_wav_is_valid_and_the_declared_length():
    out = compose_sound(seed=58, duration=12.0)
    raw = base64.b64decode(out["wav_b64"])
    with wave.open(io.BytesIO(raw), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == RATE
        assert abs(w.getnframes() / RATE - 12.0) < 0.05


def test_the_study_is_audible_not_silence():
    import struct
    out = compose_sound(seed=58, duration=10.0)
    raw = base64.b64decode(out["wav_b64"])
    with wave.open(io.BytesIO(raw), "rb") as w:
        frames = w.readframes(w.getnframes())
    vals = struct.unpack(f"<{len(frames) // 2}h", frames)
    rms = (sum(v * v for v in vals) / len(vals)) ** 0.5
    assert rms > 500, f"the study is near-silent (rms {rms:.0f})"
    assert max(abs(v) for v in vals) < 32700, "clipping"


def test_the_score_rides_the_receipt():
    out = compose_sound(seed=58)
    r = out["receipt"]
    assert r["n_events"] == len(r["score"]) > 4
    t0, freq, dur, amp = r["score"][0]
    assert 0 < t0 and 55 <= freq <= 4000 and 0 < dur and 0 < amp < 1


def test_named_refusals_at_the_fences():
    assert "duration" in compose_sound(duration=3)["refusals"][0]
    assert "root" in compose_sound(root=20)["refusals"][0]
