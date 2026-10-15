"""Falsifiers for the footprint suite's own instruments (no model, no network)."""
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _m():
    spec = importlib.util.spec_from_file_location("measure_footprint",
                                                  ROOT / "scripts" / "measure_footprint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_installed_size_leaves_out_pip(tmp_path):
    m = _m()
    (tmp_path / "pip").mkdir()
    (tmp_path / "pip" / "big.py").write_bytes(b"x" * 1000)
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / "a.py").write_bytes(b"y" * 10)
    (tmp_path / "flywheel_verify-1.8.0.dist-info").mkdir()
    (tmp_path / "flywheel_verify-1.8.0.dist-info" / "RECORD").write_bytes(b"z" * 5)
    assert m.installed_bytes(tmp_path) == 15


def test_memory_reading_sees_this_process():
    rss = _m().rss_bytes(os.getpid())
    assert rss is None or rss > 1_000_000


def test_stats_report_median_and_spread():
    s = _m()._stats([1.0, 2.0, 3.0, 4.0, None])
    assert s["n"] == 4 and s["median"] == 2.5 and s["p10"] <= s["median"] <= s["p90"]


def test_the_measured_process_is_never_a_venv_launcher(tmp_path):
    m = _m()
    venv = tmp_path / "v"
    (venv / ("Scripts" if sys.platform == "win32" else "bin")).mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = C:/Python312\nversion = 3.12.10\n")
    cmd = m.command(m.venv_python(venv), tmp_path / "sp")
    if sys.platform == "win32":
        assert cmd[0].endswith("python.exe") and "Scripts" not in cmd[0] and cmd[1] == "-S"
        assert "addsitedir" in cmd[-1]
    else:
        assert cmd[1] == "-c"
