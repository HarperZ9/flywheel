"""Known-answer and planted-failure tests for full-track 4096-pt Welch PSD oracle (Wave 30A-1)."""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

from gather.deconstruct.audio_deconstruct import deconstruct_audio


def _write_wav(path: Path, sr: int, left: list[float], right: list[float] | None = None) -> Path:
    ch = 1 if right is None else 2
    frames = bytearray()
    if right is None:
        for s in left:
            v = max(-32768, min(32767, int(round(max(-1.0, min(1.0, s)) * 32767))))
            frames.extend(struct.pack("<h", v))
    else:
        for a, b in zip(left, right):
            va = max(-32768, min(32767, int(round(max(-1.0, min(1.0, a)) * 32767))))
            vb = max(-32768, min(32767, int(round(max(-1.0, min(1.0, b)) * 32767))))
            frames.extend(struct.pack("<hh", va, vb))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(ch)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    return path


def _generate_pink_noise(n: int, seed: int = 42) -> list[float]:
    """Paul Kellet 7-pole pink noise filter (-3.0 dB/oct known answer)."""
    rng = random.Random(seed)
    b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
    out: list[float] = []
    for _ in range(n):
        w = rng.uniform(-1.0, 1.0)
        b0 = 0.99886 * b0 + w * 0.0555179
        b1 = 0.99332 * b1 + w * 0.0750759
        b2 = 0.96900 * b2 + w * 0.1538520
        b3 = 0.86650 * b3 + w * 0.3104856
        b4 = 0.55000 * b4 + w * 0.5329522
        b5 = -0.7616 * b5 - w * 0.0168980
        pink = b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362
        b6 = w * 0.115926
        out.append(pink * 0.12)
    return out


def _cascade_lpf(samples: list[float], sr: int, cutoff_hz: float, stages: int = 4) -> list[float]:
    alpha = (2.0 * math.pi * cutoff_hz / sr) / (1.0 + 2.0 * math.pi * cutoff_hz / sr)
    cur = list(samples)
    for _ in range(stages):
        nxt: list[float] = []
        y = 0.0
        for x in cur:
            y = y + alpha * (x - y)
            nxt.append(y)
        cur = nxt
    return cur


def test_pink_noise_tilt_known_answer_and_muffled_planted_failure(tmp_path: Path) -> None:
    sr = 48000
    pink = _generate_pink_noise(sr * 2, seed=101)
    pink_doc = deconstruct_audio(_write_wav(tmp_path / "pink.wav", sr, pink))
    spec = pink_doc["spectral"]

    assert spec["fft_size"] == 4096
    assert spec["welch_frames"] >= 40
    assert spec["parseval_rel_error"] < 1e-9
    # Pink noise theoretical spectral tilt is -3.01 dB/oct.
    assert -4.5 <= spec["spectral_tilt_db_per_oct"] <= -1.8
    for key in ("sub_20_60", "bass_60_250", "low_mid_250_500", "mid_500_2k", "presence_2k_6k", "air_6k_20k"):
        assert key in spec and key in spec["band_shares"]
    assert spec["presence_2k_6k"] > 0.05
    assert spec["air_6k_20k"] > 0.02
    assert pink_doc["mastering"]["low_end_phase_correlation"] == 1.0

    # Planted failure: heavily low-passed muffled audio MUST expose steep negative tilt & missing air.
    muffled = _cascade_lpf(pink, sr, cutoff_hz=350.0, stages=4)
    muf_doc = deconstruct_audio(_write_wav(tmp_path / "muffled.wav", sr, muffled))
    m_spec = muf_doc["spectral"]
    assert m_spec["spectral_tilt_db_per_oct"] < -12.0
    assert m_spec["air_6k_20k"] < 0.005


def test_leading_silence_fade_in_does_not_fool_welch_analyzer(tmp_path: Path) -> None:
    sr = 16000
    # 0.5 s of digital silence (8,000 samples > old 1,024-sample window!) followed by bright 3.5 kHz tone + 100 Hz bass.
    silence = [0.0] * (sr // 2)
    body = [
        0.35 * math.sin(2.0 * math.pi * 100.0 * i / sr)
        + 0.45 * math.sin(2.0 * math.pi * 3500.0 * i / sr)
        for i in range(sr)
    ]
    doc = deconstruct_audio(_write_wav(tmp_path / "lead_silence.wav", sr, silence + body))
    spec = doc["spectral"]
    assert spec["trimmed_start_frame"] >= sr // 2 - 1
    assert spec["presence_2k_6k"] > 0.45
    assert spec["centroid_mean_hz"] > 1500.0


def test_low_end_phase_correlation_catches_inverted_sub_bass(tmp_path: Path) -> None:
    sr = 16000
    n = sr
    # Good stereo: mono-locked 60 Hz sub-bass + wide out-of-phase 3.5 kHz air/presence.
    good_l = [0.5 * math.sin(2.0 * math.pi * 60.0 * i / sr) + 0.25 * math.sin(2.0 * math.pi * 3500.0 * i / sr) for i in range(n)]
    good_r = [0.5 * math.sin(2.0 * math.pi * 60.0 * i / sr) - 0.25 * math.sin(2.0 * math.pi * 3500.0 * i / sr) for i in range(n)]
    good_doc = deconstruct_audio(_write_wav(tmp_path / "good_sub.wav", sr, good_l, good_r))
    assert good_doc["mastering"]["low_end_phase_correlation"] >= 0.98

    # Planted failure: phase-inverted 60 Hz sub-bass MUST report negative correlation (< -0.9).
    bad_l = [0.5 * math.sin(2.0 * math.pi * 60.0 * i / sr) + 0.2 * math.sin(2.0 * math.pi * 1000.0 * i / sr) for i in range(n)]
    bad_r = [-0.5 * math.sin(2.0 * math.pi * 60.0 * i / sr) + 0.2 * math.sin(2.0 * math.pi * 1000.0 * i / sr) for i in range(n)]
    bad_doc = deconstruct_audio(_write_wav(tmp_path / "bad_sub.wav", sr, bad_l, bad_r))
    assert bad_doc["mastering"]["low_end_phase_correlation"] < -0.90


def test_macro_dynamic_range_and_centroid_std_distinguish_dynamic_vs_flat(tmp_path: Path) -> None:
    sr = 16000
    # Flat 4-second constant tone: near-zero macro DR and near-zero centroid std.
    flat = [0.35 * math.sin(2.0 * math.pi * 440.0 * i / sr) for i in range(sr * 4)]
    flat_doc = deconstruct_audio(_write_wav(tmp_path / "flat.wav", sr, flat))
    assert flat_doc["mastering"]["macro_dynamic_range_db"] < 0.5
    assert flat_doc["spectral"]["centroid_std_hz"] < 20.0

    # Dynamic 4-second arc: quiet low-freq intro (2s @ 0.08, 220 Hz) -> loud bright chorus (2s @ 0.72, 2600 Hz).
    quiet = [0.08 * math.sin(2.0 * math.pi * 220.0 * i / sr) for i in range(sr * 2)]
    loud = [0.72 * math.sin(2.0 * math.pi * 2600.0 * i / sr) for i in range(sr * 2)]
    dyn_doc = deconstruct_audio(_write_wav(tmp_path / "dynamic.wav", sr, quiet + loud))
    assert dyn_doc["mastering"]["macro_dynamic_range_db"] >= 12.0
    assert dyn_doc["spectral"]["centroid_std_hz"] >= 500.0
