"""Falsifiers for the streaming sandbox runner: live output, stop, timeout."""
import sys
import threading
import time

from harness.streaming_spawn import make_runner

LOOP = "import time\nfor i in range(400):\n    print('tick', i, flush=True)\n    time.sleep(0.05)\n"


def test_output_is_readable_while_running_and_cancel_stops_it(tmp_path):
    (tmp_path / "loop.py").write_text(LOOP, encoding="utf-8")
    cancel = threading.Event()
    run = make_runner(tmp_path, cancel)
    box = {}
    t = threading.Thread(target=lambda: box.update(r=run([sys.executable, "loop.py"],
                                                         tmp_path, None, 60)))
    t.start()
    end = time.time() + 15
    while time.time() < end and "tick 5" not in (tmp_path / "stdout.txt").read_text(
            encoding="utf-8") if (tmp_path / "stdout.txt").exists() else True:
        time.sleep(0.05)
    assert "tick 5" in (tmp_path / "stdout.txt").read_text(encoding="utf-8")
    cancel.set()
    t.join(15)
    rc, out = box["r"]
    assert rc == 130 and "tick 0" in out and "tick 399" not in out


def test_timeout_is_124(tmp_path):
    (tmp_path / "loop.py").write_text(LOOP, encoding="utf-8")
    rc, _ = make_runner(tmp_path)([sys.executable, "loop.py"], tmp_path, None, 1)
    assert rc == 124


def test_a_normal_exit_returns_its_code_and_output(tmp_path):
    rc, out = make_runner(tmp_path)([sys.executable, "-c", "print('hi'); raise SystemExit(3)"],
                                    tmp_path, None, 30)
    assert rc == 3 and out == "hi"
