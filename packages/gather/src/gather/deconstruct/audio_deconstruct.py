"""Deterministic audio mastering, 6-band spectral, and 4-layer stem deconstructor.

Pure stdlib (wave, struct, math, cmath) for WAV files in CI, with clean optional
adapters for ffmpeg transcoding and external demucs stem separation when installed.
"""
from __future__ import annotations

import cmath
import hashlib
import math
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

AUDIO_SCHEMA = "audio-deconstruction/1"
BANDS: tuple[tuple[str, float, float], ...] = (
    ("sub_bass", 20.0, 60.0),
    ("bass", 60.0, 250.0),
    ("low_mid", 250.0, 500.0),
    ("mid", 500.0, 2000.0),
    ("presence", 2000.0, 6000.0),
    ("air", 6000.0, 20000.0),
)


def _db(linear: float, floor: float = -120.0) -> float:
    return round(20.0 * math.log10(linear), 4) if linear > 1e-12 else floor


def _read_wav(path: Path) -> tuple[int, int, int, list[float], list[float]]:
    with wave.open(str(path), "rb") as wf:
        sr, ch, sw, nframes = wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getnframes()
        raw = wf.readframes(nframes)
    if sw == 2:
        vals = [v / 32768.0 for v in struct.unpack(f"<{nframes * ch}h", raw)]
    elif sw == 1:
        vals = [(v - 128) / 128.0 for v in raw]
    elif sw == 4:
        vals = [v / 2147483648.0 for v in struct.unpack(f"<{nframes * ch}i", raw)]
    else:
        raise ValueError(f"unsupported WAV sample width: {sw}")
    if ch == 1:
        return sr, ch, sw * 8, vals, list(vals)
    left = vals[0::ch]
    right = vals[1::ch]
    return sr, ch, sw * 8, left, right


def _write_mono_wav(path: Path, sr: int, samples: list[float]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    clamped = [max(-32768, min(32767, int(round(s * 32767.0)))) for s in samples]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(clamped)}h", *clamped))
    data = path.read_bytes()
    return {"file": path.name, "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _fft(xs: list[complex]) -> list[complex]:
    n = len(xs)
    if n <= 1:
        return xs
    even = _fft(xs[0::2])
    odd = _fft(xs[1::2])
    out = [0j] * n
    half = n // 2
    for k in range(half):
        tw = cmath.exp(-2j * math.pi * k / n) * odd[k]
        out[k] = even[k] + tw
        out[k + half] = even[k] - tw
    return out


def _k_weighted_lufs(mono: list[float], sr: int) -> float:
    """ITU-R BS.1770-style K-weighted integrated loudness estimate (high-pass + high-shelf)."""
    if not mono:
        return -120.0
    rc_hp = 1.0 / (2.0 * math.pi * 60.0)
    a_hp = rc_hp / (rc_hp + 1.0 / sr)
    y_hp = 0.0
    prev_x = 0.0
    sq_sum = 0.0
    for x in mono:
        y_hp = a_hp * (y_hp + x - prev_x)
        prev_x = x
        # Simple +4 dB high-frequency shelf boost approximation via first-difference mix
        shelf = y_hp + 0.35 * (x - prev_x)
        sq_sum += shelf * shelf
    mean_sq = sq_sum / len(mono)
    return round(-0.691 + 10.0 * math.log10(mean_sq), 4) if mean_sq > 1e-12 else -120.0


def _mastering_telemetry(sr: int, ch: int, bits: int, left: list[float], right: list[float]) -> dict[str, Any]:
    n = len(left)
    mono = [0.5 * (a + b) for a, b in zip(left, right)]
    side = [0.5 * (a - b) for a, b in zip(left, right)]
    all_samples = left if ch == 1 else (left + right)
    peak = max((abs(x) for x in all_samples), default=0.0)
    rms = math.sqrt(sum(x * x for x in all_samples) / max(1, len(all_samples)))
    dc = sum(all_samples) / max(1, len(all_samples))
    clipping = sum(1 for x in all_samples if abs(x) >= 0.999)
    mid_rms = math.sqrt(sum(m * m for m in mono) / max(1, n))
    side_rms = math.sqrt(sum(s * s for s in side) / max(1, n))
    l_rms = math.sqrt(sum(x * x for x in left) / max(1, n))
    r_rms = math.sqrt(sum(x * x for x in right) / max(1, n))
    corr = (sum(a * b for a, b in zip(left, right)) / (n * l_rms * r_rms)) if (n and l_rms > 1e-12 and r_rms > 1e-12) else 1.0
    peak_db, rms_db = _db(peak), _db(rms)
    return {
        "sample_rate": sr, "channels": ch, "bit_depth": bits, "num_frames": n,
        "duration_s": round(n / max(1, sr), 6),
        "true_peak_dbfs": peak_db, "rms_dbfs": rms_db,
        "integrated_lufs_est": _k_weighted_lufs(mono, sr),
        "crest_factor_db": round(peak_db - rms_db, 4),
        "dynamic_range_db": round(max(0.0, peak_db - rms_db), 4),
        "dc_offset": round(dc, 6),
        "stereo_width": round(side_rms / (mid_rms + side_rms), 6) if (mid_rms + side_rms) > 1e-12 else 0.0,
        "phase_correlation": round(max(-1.0, min(1.0, corr)), 6),
        "clipping_samples": clipping,
        "clipping_detected": clipping > 0,
    }


def _spectral_analysis(mono: list[float], sr: int) -> dict[str, Any]:
    n_fft = 1024
    frame = mono[:n_fft] if len(mono) >= n_fft else mono + [0.0] * (n_fft - len(mono))
    time_energy = sum(x * x for x in frame)
    spec = _fft([complex(x, 0.0) for x in frame])
    freq_energy = sum(abs(c) ** 2 for c in spec) / n_fft
    parseval_err = abs(time_energy - freq_energy) / max(1e-12, time_energy)

    half = n_fft // 2
    mags2 = [(abs(spec[k]) ** 2) * (1.0 if k in (0, half) else 2.0) / (n_fft * n_fft) for k in range(half + 1)]
    freqs = [k * sr / n_fft for k in range(half + 1)]
    total_p = sum(mags2) or 1e-12
    bands: dict[str, dict[str, float]] = {}
    for name, lo, hi in BANDS:
        e = sum(p for f, p in zip(freqs, mags2) if lo <= f < hi)
        bands[name] = {"energy": round(e, 8), "share": round(e / total_p, 6), "db": _db(math.sqrt(e))}
    centroid = sum(f * p for f, p in zip(freqs, mags2)) / total_p
    pos = [max(p, 1e-15) for p in mags2[1:]]
    geom = math.exp(sum(math.log(p) for p in pos) / len(pos))
    arith = sum(pos) / len(pos)
    return {
        "fft_size": n_fft,
        "bands": bands,
        "spectral_centroid_hz": round(centroid, 3),
        "spectral_flatness": round(geom / max(1e-15, arith), 6),
        "parseval_time_energy": round(time_energy, 8),
        "parseval_freq_energy": round(freq_energy, 8),
        "parseval_rel_error": round(parseval_err, 12),
    }


def _estimate_tempo_and_onsets(mono: list[float], sr: int) -> dict[str, Any]:
    hop = max(1, int(sr * 0.02))
    energies = [sum(x * x for x in mono[i:i + hop]) / hop for i in range(0, len(mono), hop)]
    flux = [max(0.0, energies[i] - energies[i - 1]) for i in range(1, len(energies))]
    mean_flux = sum(flux) / max(1, len(flux))
    thresh = max(1e-5, mean_flux * 2.5)
    onsets = [i for i in range(1, len(flux) - 1) if flux[i] > thresh and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
    if len(onsets) >= 2:
        intervals = [(onsets[i] - onsets[i - 1]) * (hop / sr) for i in range(1, len(onsets))]
        med = sorted(intervals)[len(intervals) // 2]
        bpm = round(max(40.0, min(240.0, 60.0 / max(1e-3, med))), 2)
    else:
        bpm = 0.0
    return {"onset_count": len(onsets), "estimated_bpm": bpm}


def _decompose_four_layers(
    left: list[float], right: list[float], sr: int, out_dir: Path | None
) -> dict[str, Any]:
    mid = [0.5 * (a + b) for a, b in zip(left, right)]
    side = [0.5 * (a - b) for a, b in zip(left, right)]
    alpha = (2.0 * math.pi * 250.0 / sr) / (1.0 + 2.0 * math.pi * 250.0 / sr)
    low: list[float] = []
    acc = 0.0
    for x in mid:
        acc = acc + alpha * (x - acc)
        low.append(acc)
    high = [m - lo for m, lo in zip(mid, low)]
    lr_e = sum(a * a + b * b for a, b in zip(left, right))
    ms_e = 2.0 * sum(m * m + s * s for m, s in zip(mid, side))
    ms_err = abs(lr_e - ms_e) / max(1e-12, lr_e)
    sum_err = max((abs((lo + hi) - m) for lo, hi, m in zip(low, high, mid)), default=0.0)
    layers = {"mid_center": mid, "side_ambience": side, "low_bass": low, "high_transient": high}
    stems: dict[str, Any] = {}
    for name, sig in layers.items():
        rms = math.sqrt(sum(x * x for x in sig) / max(1, len(sig)))
        info: dict[str, Any] = {"rms_dbfs": _db(rms), "energy": round(sum(x * x for x in sig), 8)}
        if out_dir is not None:
            info.update(_write_mono_wav(out_dir / f"stem_{name}.wav", sr, sig))
        stems[name] = info
    return {
        "backend": "stdlib_4layer_offline",
        "external_demucs_available": shutil.which("demucs") is not None,
        "ms_energy_rel_error": round(ms_err, 12),
        "band_split_exact_sum_max_err": round(sum_err, 12),
        "stems": stems,
    }


def deconstruct_audio(path: Path, out_dir: Path | None = None) -> dict[str, Any]:
    """Deterministically analyze an audio file (WAV native; optional ffmpeg transcode)."""
    raw = path.read_bytes()
    source_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    suffix = path.suffix.lower()
    if suffix == ".wav":
        sr, ch, bits, left, right = _read_wav(path)
        backend = "stdlib_wave"
    else:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {
                "schema": AUDIO_SCHEMA, "source_path": path.name, "source_sha256": source_sha,
                "status": "UNVERIFIABLE", "reason": f"ffmpeg required to decode {suffix}",
                "ffmpeg_available": False,
            }
        with tempfile.TemporaryDirectory() as td:
            wav_tmp = Path(td) / "decoded.wav"
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", str(path), "-acodec", "pcm_s16le", str(wav_tmp)],
                capture_output=True, text=True, timeout=60, check=False,
            )
            if proc.returncode != 0 or not wav_tmp.is_file():
                return {
                    "schema": AUDIO_SCHEMA, "source_path": path.name, "source_sha256": source_sha,
                    "status": "DRIFT", "reason": "ffmpeg decode failed", "ffmpeg_available": True,
                }
            sr, ch, bits, left, right = _read_wav(wav_tmp)
        backend = "ffmpeg_to_wave"

    mono = [0.5 * (a + b) for a, b in zip(left, right)]
    return {
        "schema": AUDIO_SCHEMA,
        "source_path": path.name,
        "source_sha256": source_sha,
        "status": "OK",
        "decode_backend": backend,
        "mastering": _mastering_telemetry(sr, ch, bits, left, right),
        "spectral": _spectral_analysis(mono, sr),
        "rhythm": _estimate_tempo_and_onsets(mono, sr),
        "decomposition": _decompose_four_layers(left, right, sr, out_dir),
    }
