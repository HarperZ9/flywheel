"""pipeline.py -- overlap generation with verification (colibri async-prefetch,
borrowed as technique). The propose/verify loop is our slowest lane: generation
goes to one model server (serial, I/O-bound) and verification runs a subprocess
oracle (CPU-bound). Those use DIFFERENT resources, so verify(i) can run while
generate(i+1) is still waiting on the model -- colibri's "hide I/O behind compute".

Both sides release the GIL (urllib HTTP wait; subprocess.communicate wait), so
plain threads genuinely overlap them. Generation stays serial in the caller's
thread (one server -> no contention); each candidate's verification is handed to
a small worker pool as soon as it exists, so generation never blocks on it.

Pure SCHEDULING: it runs the SAME oracle calls on the SAME candidates and returns
results in input order -- identical to a serial run, strictly less wall-clock when
gen and verify use different resources. It is NOT on the accept path; it does not
change what the oracle decides, only when it runs.
"""
from __future__ import annotations

import concurrent.futures as cf
from typing import Callable, Iterable

GEN_ERROR = "GEN_ERROR"
VERIFY_ERROR = "VERIFY_ERROR"


def pipelined_run(items: Iterable, generate: Callable, verify: Callable,
                  *, verify_workers: int = 2) -> list:
    """For each item: candidate = generate(item); result = verify(item, candidate).
    Generation runs serially in this thread; verification runs on a worker pool so
    it overlaps the next generation. Returns results in input order. A generate()
    that raises yields ("GEN_ERROR", repr) and skips verify; a verify() that raises
    yields ("VERIFY_ERROR", repr) -- one bad item never wedges the pipeline."""
    items = list(items)
    results: list = [None] * len(items)
    if not items:
        return results
    with cf.ThreadPoolExecutor(max_workers=max(1, verify_workers)) as pool:
        futures: dict = {}
        for i, item in enumerate(items):
            try:
                cand = generate(item)
            except Exception as e:
                results[i] = (GEN_ERROR, repr(e))
                continue
            futures[pool.submit(verify, item, cand)] = i
        for fut in cf.as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = (VERIFY_ERROR, repr(e))
    return results


def serial_run(items: Iterable, generate: Callable, verify: Callable) -> list:
    """The un-pipelined baseline, for the falsifier: same results, more wall-clock."""
    out = []
    for item in items:
        try:
            cand = generate(item)
        except Exception as e:
            out.append((GEN_ERROR, repr(e)))
            continue
        try:
            out.append(verify(item, cand))
        except Exception as e:
            out.append((VERIFY_ERROR, repr(e)))
    return out
