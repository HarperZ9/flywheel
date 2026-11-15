"""The house transform and the SessionStart hook stay within five times their
budgets (docs/house-voice.md). The measured numbers come from
`python -m articulate.bench house`; five times the budget catches a regression
of an order of magnitude.

A wall-clock budget alone fails on a loaded machine, such as a full suite under
`pytest -n 8`, though the code did not change. So each sample runs next to a
calibration workload of the same kind: a pure-Python loop for the in-process
transform, an empty interpreter start for the hook. When the calibration runs
slower than its reference time on an idle machine, the sample is scaled down by
the same factor. A faster machine never gets a looser budget. The guard still
fails on a real slowdown, which slows the sample and not the calibration
(test_the_guard_fails_on_a_planted_slowdown). Set ARTICULATE_STRICT_TIMING=1 to
check the raw times with no scaling."""
import json
import os
import statistics
import subprocess
import sys
import time

from articulate import bench, house

CEILING = 5
# Idle reference times on Windows 11, Python 3.12.10: the loop below takes
# 8 to 10 ms, and an empty `python -I -S -B` start takes about 30 ms.
LOOP_REF_MS = 10.0
START_REF_MS = 30.0


def _ms(fn):
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000


def _loop():
    sum(i * i for i in range(200_000))


def _empty_start():
    subprocess.run([sys.executable, "-I", "-S", "-B", "-c", "pass"], capture_output=True, timeout=30)


def _load_adjusted_median(sample, calibrate, ref_ms, runs):
    """Median sample time, each sample divided by the load seen beside it."""
    strict = os.environ.get("ARTICULATE_STRICT_TIMING") == "1"
    adjusted = []
    for _ in range(runs):
        before = _ms(calibrate)
        took = _ms(sample)
        after = _ms(calibrate)
        load = 1.0 if strict else max(1.0, min(before, after) / ref_ms)
        adjusted.append(took / load)
    return statistics.median(adjusted), adjusted


def _transform_median(text, sample=None):
    house.transform(text)
    return _load_adjusted_median(sample or (lambda: house.transform(text)), _loop, LOOP_REF_MS, 7)


def test_bench_text_has_the_requested_length():
    assert len(bench.house_text(300).split()) == 300
    assert len(bench.house_text(2000).split()) == 2000


def test_warm_transform_within_budget():
    for words, budget in ((300, bench.HOUSE_BUDGET_MS["transform_300"]),
                          (2000, bench.HOUSE_BUDGET_MS["transform_2000"])):
        median, times = _transform_median(bench.house_text(words))
        assert median <= CEILING * budget, (words, times)


def test_the_guard_fails_on_a_planted_slowdown():
    budget = bench.HOUSE_BUDGET_MS["transform_300"]
    text = bench.house_text(300)

    def slow():
        house.transform(text)
        time.sleep(2 * CEILING * budget / 1000)

    median, times = _transform_median(text, slow)
    assert median > CEILING * budget, times


def test_session_start_hook_cold_within_budget(tmp_path):
    from articulate import bench_house
    shim = bench_house.shim_bundle(tmp_path / "plugin")
    env = dict(os.environ, ARTICULATE_CONFIG_DIR=str(tmp_path / "cfg"))
    env["ARTICULATE_HOUSE_VOICE"] = "on"
    event = json.dumps({"hook_event_name": "SessionStart", "source": "startup"}).encode()

    def hook():
        run = subprocess.run([sys.executable, "-I", "-S", "-B", "-X", "utf8", str(shim)],
                             input=event, capture_output=True, env=env, timeout=30)
        assert run.returncode == 0 and b"additionalContext" in run.stdout

    median, times = _load_adjusted_median(hook, _empty_start, START_REF_MS, 5)
    assert median <= CEILING * bench.HOUSE_BUDGET_MS["session_start"], times


def test_transform_reports_its_own_timing():
    rec = house.transform(bench.house_text(300))["receipt"]
    assert 0 <= rec["timing_ms"] < 60_000


def test_start_up_note_names_a_slow_interpreter_and_stays_quiet_otherwise():
    from articulate import bench_house
    slow = {"python_start": {"median": 160.0}}
    note = bench_house.start_up_note(slow)
    assert note and "160 ms" in note and "apply_cold_2000_no_site" in note
    assert bench_house.start_up_note({"python_start": {"median": 30.0}}) is None
