"""Latency of the house voice: the transform in a warm process, the CLI pipe
cold, and the SessionStart hook cold.

Run `python -m articulate.bench house`. It prints median and p95 per step in
milliseconds next to the budget from docs/house-voice.md. Text is generated
here; no corpus is read.
"""
import json
import os
import statistics
import subprocess
import sys
import time

HOUSE_BUDGET_MS = {"session_start": 100, "transform_300": 25, "transform_2000": 120,
                   "apply_cold_2000": 250, "apply_cold_2000_no_site": 250,
                   "stop_cold_2000": 200}
# Measured median of `python -c pass` in a clean virtual environment: 30 ms on
# Windows 11, Python 3.12.10. Above this, the note in start_up_note applies.
CLEAN_START_MS = 50
_SENTENCES = ["The parser reads each line once \u2014 it keeps a running count of open brackets.",
              "A file of 2,000 lines costs one pass.", "I ran the suite twice on Python 3.12.",
              "Both runs passed 412 of 412 tests in 9.8 seconds.",
              "The cache key drops the timestamp, so repeated requests hit."]


def house_text(words):
    """Synthetic model output of exactly `words` words, with em dashes to replace."""
    out, n, i = [], 0, 0
    while n < words:
        s = _SENTENCES[i % len(_SENTENCES)].split()
        out.extend(s[:words - n])
        n += len(s[:words - n])
        i += 1
    text = " ".join(out)
    return "Great question!\n\n" + text if words > 50 and False else text


def _stats(samples):
    s = sorted(samples)
    return {"median": round(statistics.median(s), 2),
            "p95": round(s[max(0, int(round(0.95 * len(s))) - 1)], 2), "runs": len(s)}


def _warm(words, runs):
    from . import house
    text = house_text(words)
    house.transform(text)
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        house.transform(text)
        times.append((time.perf_counter() - t0) * 1000)
    return _stats(times)


def _cold(args, stdin, runs):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        subprocess.run([sys.executable, "-B", "-X", "utf8", *args], input=stdin,
                       capture_output=True, env=env, timeout=60, check=True)
        times.append((time.perf_counter() - t0) * 1000)
    return _stats(times)


def shim_bundle(folder):
    """A minimal plugin layout in folder: server/house_hook.py beside src/articulate,
    so the SessionStart cost is measured the way the plugin runs it."""
    import pathlib
    import shutil
    here = pathlib.Path(__file__).resolve().parent
    root = pathlib.Path(folder)
    shutil.copytree(here, root / "src" / "articulate",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "server").mkdir(parents=True, exist_ok=True)
    shim = here.parent.parent / "claude-plugin" / "server" / "house_hook.py"
    shutil.copy(shim, root / "server" / "house_hook.py")
    return root / "server" / "house_hook.py"


def _plugin_cold(stdin, runs):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        shim = shim_bundle(tmp)
        return _cold(["-I", "-S", str(shim)], stdin, runs)


def _with_mode(mode, fn, *args):
    """Run fn with ARTICULATE_HOUSE_VOICE set to mode, then restore the old value.
    The hooks do nothing while the voice is off, its default, so they are timed on."""
    old = os.environ.get("ARTICULATE_HOUSE_VOICE")
    os.environ["ARTICULATE_HOUSE_VOICE"] = mode
    try:
        return fn(*args)
    finally:
        if old is None:
            os.environ.pop("ARTICULATE_HOUSE_VOICE", None)
        else:
            os.environ["ARTICULATE_HOUSE_VOICE"] = old


def measure(runs=15):
    start = json.dumps({"hook_event_name": "SessionStart", "source": "startup"}).encode()
    stop = json.dumps({"hook_event_name": "Stop", "last_assistant_message": house_text(2000)}).encode()
    rows = {"python_start": _cold(["-c", "pass"], b"", runs),
            "transform_300": _warm(300, runs), "transform_2000": _warm(2000, runs),
            "session_start": _with_mode("on", _plugin_cold, start, runs),
            "apply_cold_2000": _cold(["-m", "articulate.cli", "house", "apply", "-"],
                                     house_text(2000).encode(), runs),
            # The same pipe without site-packages start-up, which varies by machine.
            "apply_cold_2000_no_site": _cold(["-S", "-m", "articulate.cli", "house", "apply", "-"],
                                             house_text(2000).encode(), runs)}
    rows["stop_cold_2000"] = _with_mode("revise", _plugin_cold, stop, runs)
    for key, row in rows.items():
        if key in HOUSE_BUDGET_MS:
            row["budget_p95"] = HOUSE_BUDGET_MS[key]
            row["within"] = row["p95"] <= HOUSE_BUDGET_MS[key]
    return rows


def start_up_note(rows):
    """A plain reading of the cold rows when the interpreter itself starts slowly.

    The cold budgets hold Articulate's own work plus a clean interpreter start
    (about 20 to 40 ms on Windows and Linux). A site-packages folder with many
    .pth files adds its cost before any Articulate code runs; on the test
    machine that was about 130 ms. python_start measures it, so a reader can
    tell that cost from Articulate's."""
    start = rows["python_start"]["median"]
    if start <= CLEAN_START_MS:
        return None
    return ("python -c pass takes %.0f ms here before any Articulate code runs "
            "(in a clean virtual environment it measured about 30 ms); the cold rows "
            "with site-packages include that. Compare apply_cold_2000_no_site, or run "
            "in a clean virtual environment." % start)


def main(argv):
    runs = int(argv[0]) if argv else 15
    rows = measure(runs)
    out = {"python": sys.version.split()[0], "platform": sys.platform, "rows": rows}
    note = start_up_note(rows)
    if note:
        out["note"] = note
    print(json.dumps(out, indent=2))
    return 0
