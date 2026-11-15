"""Substrate 10 — SOUND / hearing (the audio sense; the everyday instance of the principle).

A musical note = fundamental f0 + harmonics (2f0,3f0,...) with decaying amplitude (the timbre). A
lossy bandlimiting transform (lowpass — a phone line, an MP3's high-frequency cut) discards most of the
spectral energy. Two criteria of sound:
  PITCH  = f0 / which note it is (melody, the linguistic content of speech)
  TIMBRE = the harmonic profile / which instrument, the 'fidelity'
Bandlimiting is faithful to PITCH (the fundamental is below the cut, so you still recognize the note /
understand the words) but lossy to TIMBRE (the high harmonics that make a violin a violin are gone).
This is why a phone call is intelligible (pitch/words conserved) yet unmistakably low-fidelity (timbre
lost): lossy-but-faithful, the form everyone has heard.

Pitch via autocorrelation; timbre via the energy at the 4th harmonic (Goertzel). Stdlib only.
"""
from __future__ import annotations
import math

FS, DUR = 8000, 0.25
N = int(FS * DUR)
NOTES = {"C3": 131, "E3": 165, "G3": 196, "C4": 262}


def synth(f0, harmonics=12):
    sig = []
    for i in range(N):
        t = i / FS
        sig.append(sum((1.0 / h) * math.sin(2 * math.pi * h * f0 * t) for h in range(1, harmonics + 1)))
    return sig


def lowpass(sig, w=10):
    out = []
    for i in range(len(sig)):
        lo, hi = max(0, i - w), min(len(sig), i + w + 1)
        out.append(sum(sig[lo:hi]) / (hi - lo))
    return out


def detect_f0(sig, fmin=90, fmax=350):
    best_lag, best = 0, -1.0
    for lag in range(int(FS / fmax), int(FS / fmin)):
        ac = sum(sig[i] * sig[i + lag] for i in range(0, len(sig) - lag, 2))   # stride 2 for speed
        if ac > best:
            best, best_lag = ac, lag
    return FS / best_lag if best_lag else 0.0


def goertzel_energy(sig, freq):
    re = sum(s * math.cos(2 * math.pi * freq * i / FS) for i, s in enumerate(sig))
    im = sum(s * math.sin(2 * math.pi * freq * i / FS) for i, s in enumerate(sig))
    return (re * re + im * im) / (len(sig) ** 2)


def main():
    print(f"notes synthesized with 12 harmonics; bandlimited by a lowpass (phone-line style).  fs={FS}\n")
    print("note   true f0   detected f0 (orig / filtered)   timbre@4th harm (orig / filtered)")
    pitch_ok = 0
    timbre_kept = []
    for name, f0 in NOTES.items():
        sig = synth(f0)
        lp = lowpass(sig)
        d_o, d_f = detect_f0(sig), detect_f0(lp)
        t_o = goertzel_energy(sig, 4 * f0)
        t_f = goertzel_energy(lp, 4 * f0)
        ratio = t_f / t_o if t_o > 0 else 0.0
        timbre_kept.append(ratio)
        ok = abs(d_f - f0) / f0 < 0.05
        pitch_ok += ok
        print(f"  {name:4s}   {f0:4d}      {d_o:6.1f} / {d_f:6.1f}            {t_o:.2e} / {t_f:.2e}  ({ratio:.0%})")

    pitch_rate = pitch_ok / len(NOTES)
    mean_timbre = sum(timbre_kept) / len(timbre_kept)
    print("\n--- verdict (substrate 10: sound / hearing) ---")
    p1 = pitch_rate >= 0.99
    p3 = pitch_rate >= 0.99 and mean_timbre < 0.25
    print(f"(1) lossy-but-faithful: bandlimiting discards the high harmonics yet PITCH recovered for "
          f"{pitch_ok}/{len(NOTES)} notes  -> {'HOLDS' if p1 else 'FALLS'}")
    print(f"(3) criterion-relativity: same transform faithful to PITCH ({pitch_rate:.0%}) but lossy to "
          f"TIMBRE (4th-harmonic energy kept ~{mean_timbre:.0%})  -> {'HOLDS' if p3 else 'FALLS'}")
    print("\nSTICKS" if (p1 and p3) else "\nFALLS", "— substrate 10 (sound): the phone-call instance — words/melody survive, fidelity does not.")


if __name__ == "__main__":
    main()
