"""Re-derivable micro-measurement: raw vs PNG grab cost.

The README cites per-grab timings for the raw fast path. Per the project's own
re-derivability doctrine, the numbers should be reproducible from something
shipped -- this is that something. It is a single-region point measurement on
whatever machine runs it, not a benchmark suite; run it to get your own figures.

    python scripts/bench_raw_vs_png.py            # default 640x480, 30 iters
    python scripts/bench_raw_vs_png.py 1280 720 50

Prints median and mean milliseconds for grab_raw (capture only) and grab_png
(capture + BGRA->RGB + zlib encode). Requires a native capture backend; exits
cleanly with a message if none is available.
"""

from __future__ import annotations

import statistics
import sys
import time

# Run from a checkout without installing: make src importable.
sys.path.insert(0, "src")

from coherence_membrane.native_capture import (  # noqa: E402
    CaptureUnavailable,
    capture_available,
    grab_png,
    grab_raw,
)


def _time(fn, region, iters: int) -> list[float]:
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn(region)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


def main(argv: list[str]) -> int:
    w = int(argv[0]) if len(argv) > 0 else 640
    h = int(argv[1]) if len(argv) > 1 else 480
    iters = int(argv[2]) if len(argv) > 2 else 30
    region = (0, 0, w, h)

    if not capture_available():
        print(f"no native capture backend on platform {sys.platform!r}; nothing to measure")
        return 2

    try:
        grab_raw(region)  # warm up (one-time ctypes prototype setup, etc.)
        grab_png(region)
    except CaptureUnavailable as exc:
        print(f"capture unavailable: {exc}")
        return 2

    raw = _time(grab_raw, region, iters)
    png = _time(grab_png, region, iters)

    def line(name: str, s: list[float]) -> str:
        return (f"{name:9s} median={statistics.median(s):6.1f} ms  "
                f"mean={statistics.fmean(s):6.1f} ms  "
                f"min={min(s):6.1f} ms  max={max(s):6.1f} ms")

    print(f"region {w}x{h}, {iters} iters, platform {sys.platform!r}")
    print(line("grab_raw", raw))
    print(line("grab_png", png))
    print(f"raw is {statistics.median(png) / statistics.median(raw):.2f}x cheaper per grab (median)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
