#!/usr/bin/env python3
"""
download_parallel.py — multi-connection ranged HTTP downloader.

Beats per-connection CDN throttling by splitting the file into N byte ranges and
downloading them concurrently, each on its own connection, then concatenating in
order. Resumable: each part resumes from its current size; re-running finishes a
partial download. Stdlib only.

Usage:
  python download_parallel.py --url URL --out FILE --parts-dir DIR --conns 16
"""
from __future__ import annotations
import argparse
import concurrent.futures
import os
import sys
import time
import urllib.request


def resolve(url: str) -> tuple[str, int]:
    """Follow redirects and return (final_url, total_size) via a 1-byte range."""
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        final = r.url
        cr = r.headers.get("Content-Range", "")
        if "/" in cr:
            return final, int(cr.split("/")[-1])
        cl = r.headers.get("Content-Length")
        if cl:
            return final, int(cl)
    raise RuntimeError("could not determine content size")


def fetch_range(url: str, start: int, end: int, path: str) -> int:
    """Download bytes [start,end] into path, resuming if partially present."""
    want = end - start + 1
    have = os.path.getsize(path) if os.path.exists(path) else 0
    if have >= want:
        return want
    req = urllib.request.Request(
        url, headers={"Range": f"bytes={start + have}-{end}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "ab") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--parts-dir", required=True)
    ap.add_argument("--conns", type=int, default=16)
    a = ap.parse_args()

    final, size = resolve(a.url)
    print(f"size={size} bytes ({size/1e6:.1f} MB) conns={a.conns}", flush=True)
    os.makedirs(a.parts_dir, exist_ok=True)

    n = max(1, a.conns)
    step = size // n
    ranges = []
    for i in range(n):
        start = i * step
        end = size - 1 if i == n - 1 else (start + step - 1)
        ranges.append((i, start, end))

    t0 = time.time()

    def work(job):
        i, start, end = job
        path = os.path.join(a.parts_dir, f"part_{i:03d}")
        want = end - start + 1
        for attempt in range(1, 10):
            try:
                if fetch_range(final, start, end, path) >= want:
                    return i, want
            except Exception as e:  # noqa: BLE001 — retry any transient net error
                print(f"part {i} attempt {attempt}: {e}", flush=True)
                time.sleep(2)
        have = os.path.getsize(path) if os.path.exists(path) else 0
        return i, have

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(work, ranges))

    incomplete = 0
    for i, start, end in ranges:
        want = end - start + 1
        path = os.path.join(a.parts_dir, f"part_{i:03d}")
        have = os.path.getsize(path) if os.path.exists(path) else 0
        if have != want:
            print(f"part {i} incomplete {have}/{want}", flush=True)
            incomplete += 1
    if incomplete:
        print(f"{incomplete} parts incomplete; re-run to resume", flush=True)
        return 2

    with open(a.out, "wb") as out:
        for i in range(n):
            with open(os.path.join(a.parts_dir, f"part_{i:03d}"), "rb") as p:
                while True:
                    b = p.read(1 << 20)
                    if not b:
                        break
                    out.write(b)
    total = os.path.getsize(a.out)
    mbps = (total / 1e6) / max(1e-6, time.time() - t0)
    print(f"assembled {total} bytes in {time.time()-t0:.0f}s (~{mbps:.1f} MB/s); "
          f"expected {size}", flush=True)
    return 0 if total == size else 3


if __name__ == "__main__":
    sys.exit(main())
