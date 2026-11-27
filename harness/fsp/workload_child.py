"""A harmless demo workload: hashes a small buffer in a loop and reports progress.

It reads its throughput level (integer percent) from a control file the
enforcement shim writes, and writes a progress counter to a file. It reads
and writes only those two files in the demo's run directory.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import time


def _level(path: str) -> int:
    try:
        with open(path, encoding="ascii") as fh:
            return max(0, min(100, int(fh.read().strip() or 100)))
    except (OSError, ValueError):
        return 100


def _write(path: str, value: int) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(str(value))
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    level_path = os.path.join(args.dir, f"{args.name}.level")
    progress_path = os.path.join(args.dir, f"{args.name}.progress")
    done, last_write, buf = 0, 0.0, b"x" * 64
    while True:
        level = _level(level_path)
        if level == 0:
            time.sleep(0.1)
            continue
        start = time.perf_counter()
        for _ in range(2000):
            buf = hashlib.sha256(buf).digest()
        done += 1
        busy = time.perf_counter() - start
        # Cap the duty cycle at one half, then scale down by the level.
        time.sleep(busy + busy * (100 - level) / level)
        if time.monotonic() - last_write > 0.1:
            _write(progress_path, done)
            last_write = time.monotonic()


if __name__ == "__main__":
    main()
