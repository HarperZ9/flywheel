"""Falsifier for the gen/verify pipeline (harness/pipeline.py).

The two load-bearing properties: (1) pipelined results are IDENTICAL to serial
(pure scheduling, order-preserving), and (2) pipelined is strictly faster when
generation and verification use different resources. Plus: one erroring item
never wedges the pipeline.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.pipeline import pipelined_run, serial_run, GEN_ERROR, VERIFY_ERROR


def test_identical_results_to_serial():
    items = list(range(20))
    gen = lambda x: x + 100                 # candidate
    ver = lambda x, c: (x, c, c * 2)        # result
    assert pipelined_run(items, gen, ver, verify_workers=3) == serial_run(items, gen, ver)


def test_pipelined_is_strictly_faster():
    # gen (I/O) and verify (CPU/subprocess) both release the GIL via sleep, so
    # verify(i) overlaps generate(i+1). Serial ~= n*(g+v); pipelined ~= n*g + v.
    n, g, v = 12, 0.03, 0.03
    items = list(range(n))
    def gen(x):
        time.sleep(g); return x
    def ver(x, c):
        time.sleep(v); return c
    t0 = time.monotonic(); serial_run(items, gen, ver); t_serial = time.monotonic() - t0
    t0 = time.monotonic(); pipelined_run(items, gen, ver, verify_workers=2); t_pipe = time.monotonic() - t0
    assert t_pipe < t_serial * 0.8, f"pipelined {t_pipe:.2f}s not < 0.8*serial {t_serial:.2f}s"


def test_pipelined_results_match_under_timing():
    n = 12
    items = list(range(n))
    def gen(x):
        time.sleep(0.01); return x * 10
    def ver(x, c):
        time.sleep(0.01); return c + 1
    assert pipelined_run(items, gen, ver, verify_workers=4) == serial_run(items, gen, ver)


def test_generation_error_isolated():
    def gen(x):
        if x == 3:
            raise ValueError("boom")
        return x
    ver = lambda x, c: c * 2
    res = pipelined_run(range(6), gen, ver, verify_workers=2)
    assert res[3][0] == GEN_ERROR
    assert res[0] == 0 and res[5] == 10       # others unaffected, order preserved


def test_verification_error_isolated():
    gen = lambda x: x
    def ver(x, c):
        if x == 2:
            raise RuntimeError("verify boom")
        return c + 1
    res = pipelined_run(range(5), gen, ver, verify_workers=2)
    assert res[2][0] == VERIFY_ERROR
    assert res[0] == 1 and res[4] == 5


def test_empty_items():
    assert pipelined_run([], lambda x: x, lambda x, c: c) == []
