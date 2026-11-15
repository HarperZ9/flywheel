"""Substrate 6 — ANALOG: a continuous signal through a lossy filter (and the noise bend).

The first non-discrete substrate-kind: no bits, no levels — a continuous waveform through an analog
transform (a filter), read by a continuous criterion (is a tone present?). This is the literal
substrate of the aperture metaphors: the pupil is an analog aperture; the neuron's membrane potential
is analog before the all-or-nothing spike (analog->digital IS the threshold transpile).

Signal x(t) = a_low*sin(2pi*2Hz) + a_high*sin(2pi*40Hz) + noise, each tone present-or-not at random.
Transforms (analog, lossy in degrees-of-freedom / bandwidth, not bits):
  lowpass : moving-average — passes 2Hz, removes 40Hz.   (faithful to phi_low, lossy to phi_high)
  highpass: signal minus lowpass — passes 40Hz, removes 2Hz.
Criteria (continuous readouts via a Goertzel single-freq amplitude):
  phi_low  = the 2Hz tone is present     phi_high = the 40Hz tone is present
THE ANALOG BEND we test for: digital faithfulness was ~binary (factors or not). Analog faithfulness is
GRADED — phi survives only up to a NOISE FLOOR; we sweep SNR and watch it degrade smoothly. Energy note:
a passive filter conserves/redistributes energy (Parseval); the "loss" is the stopband energy; the
passband (criterion-relevant) energy is preserved.

Stdlib only (math, random), deterministic.
"""
from __future__ import annotations
import math, random

FS, L = 200, 200          # 200 Hz, 1 s -> 200 samples
F_LOW, F_HIGH = 2.0, 40.0
THRESH = 0.40             # tone-present amplitude threshold


def tone(freq, amp, n):
    return [amp * math.sin(2 * math.pi * freq * i / FS) for i in range(n)]


def add(a, b): return [x + y for x, y in zip(a, b)]


def goertzel_amp(sig, freq):
    re = sum(s * math.cos(2 * math.pi * freq * i / FS) for i, s in enumerate(sig))
    im = sum(s * math.sin(2 * math.pi * freq * i / FS) for i, s in enumerate(sig))
    return 2.0 * math.sqrt(re * re + im * im) / len(sig)


def lowpass(sig, w=20):
    out = []
    for i in range(len(sig)):
        lo, hi = max(0, i - w // 2), min(len(sig), i + w // 2 + 1)
        out.append(sum(sig[lo:hi]) / (hi - lo))
    return out


def highpass(sig):
    lp = lowpass(sig)
    return [s - l for s, l in zip(sig, lp)]


def rms(sig):
    return math.sqrt(sum(s * s for s in sig) / len(sig))


def make(rng, sigma):
    a_low = 1.0 if rng.random() < 0.5 else 0.0
    a_high = 1.0 if rng.random() < 0.5 else 0.0
    sig = [0.0] * L
    sig = add(sig, tone(F_LOW, a_low, L))
    sig = add(sig, tone(F_HIGH, a_high, L))
    sig = [s + rng.gauss(0, sigma) for s in sig]
    return sig, a_low > 0, a_high > 0


def main():
    rng = random.Random(7)
    print(f"signal: 2Hz + 40Hz tones (each present at random) + noise.  fs={FS}, {L} samples\n")

    # --- claims at low noise (sigma=0.1) ---
    sigma = 0.1
    n = 400
    cl = ch = lossH = energy = 0.0
    for _ in range(n):
        sig, plow, phigh = make(rng, sigma)
        lp = lowpass(sig)
        cl += ((goertzel_amp(lp, F_LOW) > THRESH) == plow)        # phi_low from lowpass: faithful
        ch += ((goertzel_amp(lp, F_HIGH) > THRESH) == phigh)      # phi_high from lowpass: lossy
        energy += (rms(lp) ** 2) / (rms(sig) ** 2 + 1e-9)
    cl /= n; ch /= n; energy /= n
    print("transform lowpass — criterion recovery:")
    print(f"  phi_low (2Hz, in passband)  recovered {cl:.3f}   <- faithful")
    print(f"  phi_high (40Hz, in stopband) recovered {ch:.3f}   <- lossy (tone removed)")
    print(f"  passband energy retained ~{energy:.2f} of total (stopband energy is the 'loss')\n")

    # --- the analog bend: graded faithfulness vs SNR ---
    print("the analog bend — phi_low recovery through lowpass as noise rises (graded, not binary):")
    print("   sigma   SNR(approx)   phi_low recovery")
    for sigma in (0.1, 0.3, 0.6, 1.0, 1.6, 2.4):
        n = 400; ok = 0
        for _ in range(n):
            sig, plow, _ = make(rng, sigma)
            ok += ((goertzel_amp(lowpass(sig), F_LOW) > THRESH) == plow)
        snr = (0.707 / sigma) if sigma else float("inf")          # tone RMS ~0.707 over noise sigma
        print(f"   {sigma:4.1f}    {snr:6.2f}        {ok/n:.3f}")

    print("\n--- verdict (substrate 6: analog) ---")
    p1 = cl > 0.95                                  # phi_low survives though the filter discards a band
    p3 = (cl - ch) > 0.3                            # same transform faithful to low, lossy to high
    print(f"(1) lossy-but-faithful: lowpass discards the 40Hz band yet phi_low recovered {cl:.3f}"
          f"  -> {'HOLDS' if p1 else 'FALLS'}")
    print(f"(3) criterion-relativity: lowpass faithful to phi_low ({cl:.3f}) / lossy to phi_high ({ch:.3f})"
          f"  -> {'HOLDS' if p3 else 'FALLS'}")
    print("(bend) analog faithfulness is GRADED: phi survives smoothly down to a NOISE FLOOR, not the")
    print("       binary all-or-nothing of the digital substrates — a refinement, not a refutation.")
    print("\nSTICKS (with the graded-faithfulness refinement)" if (p1 and p3)
          else "\nFALLS", "— substrate 6 (analog).")


if __name__ == "__main__":
    main()
