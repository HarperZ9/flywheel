"""Pure-stdlib 4096-pt Hann Welch PSD, spectral tilt, macro DR, and <120 Hz phase oracle.

Zero third-party dependencies (math, cmath only). Designed to keep audio_deconstruct.py
under Flywheel's 300-line/file and 50-line/function budgets while delivering accurate
full-track spectral and stereo low-end diagnostics.
"""
from __future__ import annotations

import math
from typing import Any

WELCH_FFT_SIZE = 4096
WELCH_HOP_SIZE = 2048
SILENCE_FLOOR = 1e-4

BANDS: tuple[tuple[str, str, float, float], ...] = (
    ("sub_bass", "sub_20_60", 20.0, 60.0),
    ("bass", "bass_60_250", 60.0, 250.0),
    ("low_mid", "low_mid_250_500", 250.0, 500.0),
    ("mid", "mid_500_2k", 500.0, 2000.0),
    ("presence", "presence_2k_6k", 2000.0, 6000.0),
    ("air", "air_6k_20k", 6000.0, 20000.0),
)


def _db(linear: float, floor: float = -120.0) -> float:
    return round(20.0 * math.log10(linear), 4) if linear > 1e-12 else floor


def _fft_radix2(xs: list[complex]) -> list[complex]:
    """Iterative Cooley-Tukey radix-2 FFT (exact Parseval, pure stdlib)."""
    n = len(xs)
    if n <= 1:
        return list(xs)
    out = list(xs)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            out[i], out[j] = out[j], out[i]
    size = 2
    while size <= n:
        half = size >> 1
        step = -2.0 * math.pi / size
        w_step = complex(math.cos(step), math.sin(step))
        for start in range(0, n, size):
            w = 1.0 + 0.0j
            for k in range(half):
                u = out[start + k]
                v = out[start + k + half] * w
                out[start + k] = u + v
                out[start + k + half] = u - v
                w *= w_step
        size <<= 1
    return out


def trim_digital_silence(samples: list[float], threshold: float = SILENCE_FLOOR) -> tuple[int, int]:
    """Return [start, end) indices skipping leading and trailing digital silence."""
    n = len(samples)
    start = 0
    while start < n and abs(samples[start]) <= threshold:
        start += 1
    end = n
    while end > start and abs(samples[end - 1]) <= threshold:
        end -= 1
    return (start, end) if start < end else (0, n)


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = max(0.0, min(1.0, q)) * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(len(sorted_vals) - 1, lo + 1)
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def compute_macro_dynamic_range_db(mono: list[float], sr: int) -> float:
    """Compute macro dynamic range (p95 - p10 dBFS) over 500 ms RMS windows."""
    start, end = trim_digital_silence(mono)
    active = mono[start:end]
    win = max(1, int(round(sr * 0.5)))
    hop = max(1, win // 2)
    if len(active) < win:
        return 0.0
    rms_dbs: list[float] = []
    for i in range(0, len(active) - win + 1, hop):
        seg = active[i:i + win]
        rms = math.sqrt(sum(x * x for x in seg) / win)
        if rms > 3.16e-4:  # > -70 dBFS active signal
            rms_dbs.append(20.0 * math.log10(rms))
    if len(rms_dbs) < 2:
        return 0.0
    rms_dbs.sort()
    return round(max(0.0, _percentile(rms_dbs, 0.95) - _percentile(rms_dbs, 0.10)), 4)


def _lpf_2nd_order(xs: list[float], sr: int, cutoff_hz: float = 120.0) -> list[float]:
    """2nd-order Butterworth low-pass biquad (pure stdlib) isolating <120 Hz."""
    if not xs or sr <= 0:
        return []
    fc = min(cutoff_hz, 0.45 * sr)
    k = math.tan(math.pi * fc / sr)
    norm = 1.0 / (1.0 + math.sqrt(2.0) * k + k * k)
    b0 = k * k * norm
    b1 = 2.0 * b0
    b2 = b0
    a1 = 2.0 * (k * k - 1.0) * norm
    a2 = (1.0 - math.sqrt(2.0) * k + k * k) * norm
    out: list[float] = []
    x1 = x2 = y1 = y2 = 0.0
    for x0 in xs:
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x0
        y2, y1 = y1, y0
        out.append(y0)
    return out


def compute_low_end_phase_correlation(
    left: list[float], right: list[float], sr: int, channels: int, cutoff_hz: float = 120.0,
) -> float:
    """Compute stereo L/R phase correlation below cutoff_hz (1.0 for mono)."""
    if channels <= 1 or not left or len(left) != len(right):
        return 1.0
    lo_l = _lpf_2nd_order(left, sr, cutoff_hz)
    lo_r = _lpf_2nd_order(right, sr, cutoff_hz)
    # Apply twice (LR4-like -24 dB/oct rolloff) so >500 Hz stereo width cannot leak in.
    lo_l = _lpf_2nd_order(lo_l, sr, cutoff_hz)
    lo_r = _lpf_2nd_order(lo_r, sr, cutoff_hz)
    dot = sum(a * b for a, b in zip(lo_l, lo_r))
    el = sum(a * a for a in lo_l)
    er = sum(b * b for b in lo_r)
    denom = math.sqrt(el * er)
    if denom <= 1e-12:
        return 1.0
    return round(max(-1.0, min(1.0, dot / denom)), 6)


def _compute_spectral_tilt_db_per_oct(freqs: list[float], psd: list[float], sr: int) -> float:
    """Octave-weighted log-log regression of PSD (dB) vs log2(freq) over [60, min(16k, 0.45*sr)]."""
    hi_hz = min(16000.0, 0.45 * sr)
    pts: list[tuple[float, float, float]] = []
    for f, p in zip(freqs, psd):
        if 60.0 <= f <= hi_hz and p > 1e-18:
            pts.append((math.log2(f), 10.0 * math.log10(p), 1.0 / f))
    if len(pts) < 2:
        return 0.0
    w_sum = sum(w for _, _, w in pts)
    mx = sum(w * x for x, _, w in pts) / w_sum
    my = sum(w * y for _, y, w in pts) / w_sum
    num = sum(w * (x - mx) * (y - my) for x, y, w in pts)
    den = sum(w * (x - mx) ** 2 for x, _, w in pts)
    return round(num / den, 4) if den > 1e-12 else 0.0


def _collect_welch_frames(active: list[float], n_fft: int, hop: int, max_frames: int) -> list[list[float]]:
    if len(active) <= n_fft:
        return [active + [0.0] * (n_fft - len(active))]
    starts = list(range(0, len(active) - n_fft + 1, hop))
    if len(starts) > max_frames:
        step = (len(starts) - 1) / float(max_frames - 1)
        starts = [starts[int(round(i * step))] for i in range(max_frames)]
    return [active[s:s + n_fft] for s in starts]


def _frame_psd_pair(
    fa: list[float], fb: list[float] | None, win: list[float], n_fft: int, win_pow: float,
) -> list[tuple[list[float], float, float]]:
    half = n_fft // 2
    wa = [x * w for x, w in zip(fa, win)]
    wb = [x * w for x, w in zip(fb, win)] if fb is not None else [0.0] * n_fft
    spec = _fft_radix2([complex(a, b) for a, b in zip(wa, wb)])
    specs: list[tuple[list[complex], float]] = []
    if fb is None:
        specs.append((spec, sum(a * a for a in wa)))
    else:
        xa = [0j] * n_fft
        xb = [0j] * n_fft
        for k in range(n_fft):
            zk, zmk = spec[k], spec[(n_fft - k) % n_fft].conjugate()
            xa[k] = 0.5 * (zk + zmk)
            xb[k] = -0.5j * (zk - zmk)
        specs.append((xa, sum(a * a for a in wa)))
        specs.append((xb, sum(b * b for b in wb)))
    results: list[tuple[list[float], float, float]] = []
    for sp, te in specs:
        fe = sum(abs(c) ** 2 for c in sp) / n_fft
        psd = [((abs(sp[k]) ** 2) * (1.0 if k in (0, half) else 2.0)) / (n_fft * win_pow) for k in range(half + 1)]
        results.append((psd, te, fe))
    return results


def _summarize_bands(freqs: list[float], mags2: list[float]) -> tuple[dict[str, dict[str, float]], dict[str, float], float]:
    total_p = sum(mags2) or 1e-12
    bands: dict[str, dict[str, float]] = {}
    flat_shares: dict[str, float] = {}
    for legacy_name, flat_name, lo, hi in BANDS:
        e = sum(p for f, p in zip(freqs, mags2) if lo <= f < hi)
        share = round(e / total_p, 6)
        bands[legacy_name] = {"energy": round(e, 8), "share": share, "db": _db(math.sqrt(e))}
        flat_shares[flat_name] = share
    return bands, flat_shares, total_p


def welch_spectral_analysis(
    mono: list[float], sr: int, *, n_fft: int = WELCH_FFT_SIZE, hop: int = WELCH_HOP_SIZE, max_frames: int = 192,
) -> dict[str, Any]:
    """Full-track 4096-pt Hann-windowed Welch PSD skipping leading/trailing silence."""
    start, end = trim_digital_silence(mono)
    frames = _collect_welch_frames(mono[start:end], n_fft, hop, max_frames)
    win = [0.5 * (1.0 - math.cos(2.0 * math.pi * i / (n_fft - 1))) for i in range(n_fft)]
    win_pow = sum(w * w for w in win) or 1.0
    half = n_fft // 2
    freqs = [k * sr / n_fft for k in range(half + 1)]
    psd_acc = [0.0] * (half + 1)
    centroids: list[float] = []
    te_sum = fe_sum = 0.0
    for idx in range(0, len(frames), 2):
        fb = frames[idx + 1] if (idx + 1) < len(frames) else None
        for psd, te, fe in _frame_psd_pair(frames[idx], fb, win, n_fft, win_pow):
            te_sum += te
            fe_sum += fe
            fp = sum(psd)
            if fp > 1e-18:
                centroids.append(sum(f * p for f, p in zip(freqs, psd)) / fp)
            for k in range(half + 1):
                psd_acc[k] += psd[k]
    n_used = max(1, len(frames))
    mags2 = [v / n_used for v in psd_acc]
    bands, flat_shares, total_p = _summarize_bands(freqs, mags2)
    centroid_welch = sum(f * p for f, p in zip(freqs, mags2)) / total_p
    c_mean = sum(centroids) / len(centroids) if centroids else centroid_welch
    c_std = math.sqrt(sum((c - c_mean) ** 2 for c in centroids) / len(centroids)) if len(centroids) >= 2 else 0.0
    pos = [max(p, 1e-15) for p in mags2[1:]]
    flatness = round(math.exp(sum(math.log(p) for p in pos) / len(pos)) / max(1e-15, sum(pos) / len(pos)), 6)
    return {
        "fft_size": n_fft, "hop_size": hop, "welch_frames": n_used,
        "trimmed_start_frame": start, "trimmed_end_frame": end,
        "bands": bands, "band_shares": flat_shares, **flat_shares,
        "spectral_centroid_hz": round(centroid_welch, 3),
        "centroid_mean_hz": round(c_mean, 3), "centroid_std_hz": round(c_std, 3),
        "spectral_tilt_db_per_oct": _compute_spectral_tilt_db_per_oct(freqs, mags2, sr),
        "spectral_flatness": flatness,
        "parseval_time_energy": round(te_sum / n_used, 8),
        "parseval_freq_energy": round(fe_sum / n_used, 8),
        "parseval_rel_error": round(abs(te_sum - fe_sum) / max(1e-12, te_sum), 12),
    }
