"""sound_studio.py: the music lane stops being a null.

A seeded chime study: the same mulberry32 stream that drives the aperture
plate and the typeface's micro-variation lays out a pentatonic tone row
over a soft drone, synthesized to 16-bit PCM WAV by the standard library.
The score (every event's time, frequency, duration, amplitude) is part of
the receipt, so a composition is re-derivable the way a plate or a face
is: same seed and parameters, same bytes, one hash.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import struct
import wave

SCHEMA = "flywheel.studio-sound/v1"
RATE = 22050

# a minor pentatonic row: calm, no wrong notes for a chime study
_STEPS = (0, 3, 5, 7, 10, 12, 15, 17)


def _mulberry32(seed: int):
    a = seed & 0xFFFFFFFF

    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = a
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t = (t ^ (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def _score(seed: int, duration: float, root: float) -> list:
    """The event list: chimes placed by the seeded stream, thinning toward
    the end so the study closes instead of stopping."""
    rnd = _mulberry32(seed)
    events = []
    t = 1.2 + rnd() * 1.5
    while t < duration - 3.0:
        step = _STEPS[int(rnd() * len(_STEPS)) % len(_STEPS)]
        octave = 1 + (1 if rnd() < 0.3 else 0)
        freq = root * (2.0 ** (step / 12.0)) * octave
        dur = 1.8 + rnd() * 2.4
        # quieter as the piece ages: the close is a thinning, not a cut
        amp = (0.16 + rnd() * 0.12) * (1.0 - 0.5 * (t / duration))
        events.append((round(t, 3), round(freq, 2), round(dur, 2),
                       round(amp, 4)))
        t += 0.8 + rnd() * 2.6
    return events


def compose_sound(seed: int = 58, duration: float = 24.0,
                  root: float = 220.0) -> dict:
    """Seed + duration + root -> WAV bytes under one receipt."""
    if not 6.0 <= duration <= 90.0:
        return {"refused": True,
                "refusals": ["duration must sit between 6 and 90 seconds; "
                             "a study, not a stream"]}
    if not 55.0 <= root <= 880.0:
        return {"refused": True,
                "refusals": ["root must sit between 55 and 880 Hz to keep "
                             "the row inside hearing comfort"]}

    events = _score(int(seed), float(duration), float(root))
    n = int(duration * RATE)
    samples = [0.0] * n

    # the drone: root and fifth, breathing slowly, never loud
    for i in range(n):
        t = i / RATE
        breathe = 0.5 + 0.5 * math.sin(2 * math.pi * t / 13.0)
        samples[i] += 0.05 * (1.0 + 0.4 * breathe) * (
            math.sin(2 * math.pi * root / 2 * t)
            + 0.6 * math.sin(2 * math.pi * root * 0.7495 * t))

    # the chimes: sine partials with a fast attack and a long decay
    for (t0, freq, dur, amp) in events:
        i0 = int(t0 * RATE)
        for j in range(int(dur * RATE)):
            i = i0 + j
            if i >= n:
                break
            t = j / RATE
            env = min(1.0, t / 0.02) * math.exp(-3.0 * t / dur)
            samples[i] += amp * env * (
                math.sin(2 * math.pi * freq * t)
                + 0.35 * math.sin(2 * math.pi * freq * 2.0 * t)
                + 0.12 * math.sin(2 * math.pi * freq * 2.99 * t))

    # a gentle fade at both ends; hard edges are clicks, not music
    fade = int(0.8 * RATE)
    for i in range(min(fade, n)):
        g = i / fade
        samples[i] *= g
        samples[n - 1 - i] *= g

    peak = max(1e-9, max(abs(s) for s in samples))
    norm = min(1.0, 0.89 / peak)
    pcm = struct.pack(
        f"<{n}h", *[int(max(-1.0, min(1.0, s * norm)) * 32767)
                    for s in samples])

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    wav = buf.getvalue()

    score_sha = hashlib.sha256(
        json.dumps(events, sort_keys=True).encode()).hexdigest()
    receipt = {
        "schema": SCHEMA,
        "seed": int(seed),
        "duration_s": float(duration),
        "root_hz": float(root),
        "n_events": len(events),
        "score": events,
        "score_sha256": score_sha,
        "wav_sha256": hashlib.sha256(wav).hexdigest(),
        "note": "the score is the receipt: same seed, same events, same "
                "bytes, re-derivable end to end",
    }
    return {"refused": False, "refusals": [], "receipt": receipt,
            "wav_b64": base64.b64encode(wav).decode("ascii")}
