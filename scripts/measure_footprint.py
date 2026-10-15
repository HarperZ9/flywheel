"""measure_footprint.py -- how big Flywheel's terminal harness is and how fast it starts.

Measures one installed build (a venv with flywheel-verify in it):

  installed size     bytes under site-packages, pip's own folders excluded
  version time       wall time of `flywheel --version`
  cold to prompt     process start until the `flywheel>` prompt, bytecode cache deleted
  warm to prompt     the same with the cache present
  memory at prompt   resident memory (working set) of the process when the prompt shows

`flywheel code` runs with the backend pinned to a scripted stub on loopback, so
no local model server is probed and no model is called. The process is the
interpreter running Flywheel's console entry directly with the venv's
site-packages, not the console-script shim; on Windows a venv's python.exe is
itself a launcher that starts the base interpreter as a child, so the base
interpreter is run with the venv's site-packages added. The memory reading is
then the harness process itself.

  python scripts/measure_footprint.py --venv PATH --runs 10 --out result.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = "import sys; from harness.cli_entry import console_main; sys.exit(console_main())"
PROMPT = b"flywheel> "


def venv_python(venv: Path) -> Path:
    win = venv / "Scripts" / "python.exe"
    return win if win.exists() else venv / "bin" / "python"


def command(py: Path, sp: Path) -> list:
    """The process to time and measure: the real interpreter, never a launcher."""
    if sys.platform != "win32":
        return [str(py), "-c", ENTRY]
    cfg = {k.strip(): v.strip() for k, v in (
        line.split("=", 1) for line in
        (py.parent.parent / "pyvenv.cfg").read_text(encoding="utf-8").splitlines() if "=" in line)}
    base = Path(cfg["home"]) / "python.exe"
    boot = f"import site; site.addsitedir({str(sp)!r}); " + ENTRY
    return [str(base), "-S", "-c", boot]     # -S: no global site-packages, only the venv's


def site_packages(py: Path) -> Path:
    out = subprocess.run([str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                         capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def installed_bytes(sp: Path) -> int:
    skip = ("pip", "pip-", "_distutils_hack", "distutils-precedence.pth", "setuptools", "pkg_resources")
    total = 0
    for p in sp.iterdir():
        if p.name.startswith(skip):
            continue
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        total += sum(f.stat().st_size for f in files)
    return total


def clear_bytecode(sp: Path) -> None:
    for d in sp.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def rss_bytes(pid: int) -> "int | None":
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        h = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
        if not h:
            return None
        try:
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
            return int(pmc.WorkingSetSize) if ok else None
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def time_to_prompt(cmd: list, port: int, timeout: float = 30.0) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")}
        env.update({"FLYWHEEL_HOME": str(Path(tmp) / "home"),
               "OPENAI_API_KEY": "stub-not-a-key", "CODEX_BASE_URL": f"http://127.0.0.1:{port}/v1",
               "PYTHONUNBUFFERED": "1"})  # warm runs need the bytecode cache written
        start = time.perf_counter()
        proc = subprocess.Popen(cmd + ["code", "--backend", "codex", "--no-save"],
                                cwd=str(work), env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        seen, elapsed, rss = b"", None, None
        try:
            while time.perf_counter() - start < timeout:
                chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
                if not chunk:
                    break
                seen += chunk
                if PROMPT in seen:
                    elapsed = time.perf_counter() - start
                    rss = rss_bytes(proc.pid)
                    break
        finally:
            proc.kill()
            proc.wait(timeout=10)
        return {"seconds": elapsed, "rss_bytes": rss}


def version_time(cmd: list, cwd: str) -> float:
    start = time.perf_counter()
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")}
    subprocess.run(cmd + ["--version"], capture_output=True, check=True, cwd=cwd, env=env)
    return time.perf_counter() - start


def _stats(xs: list) -> dict:
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return {"n": len(xs), "median": xs[0] if xs else None}
    qs = statistics.quantiles(xs, n=10)
    return {"n": len(xs), "median": round(statistics.median(xs), 4),
            "p10": round(qs[0], 4), "p90": round(qs[-1], 4)}


def measure(venv: Path, runs: int = 10) -> dict:
    py = venv_python(venv)
    sp = site_packages(py)
    clear_bytecode(sp)
    size = installed_bytes(sp)      # as installed, before any run writes a bytecode cache
    cmd = command(py, sp)
    neutral = tempfile.mkdtemp(prefix="fw-footprint-")   # cwd with no harness/ in it
    where = subprocess.run(cmd[:-1] + [cmd[-1].replace(ENTRY, "import harness; print(harness.__file__)")],
                           capture_output=True, text=True, check=True, cwd=neutral).stdout.strip()
    if not Path(where).resolve().is_relative_to(sp.resolve()):
        raise SystemExit(f"harness imported from {where}, not from the venv under test")
    port = free_port()
    stub = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "ci_stub_model.py"), str(port),
                             "Done."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        cold, warm, rss_cold, rss_warm, ver, failed = [], [], [], [], [], 0
        for i in range(runs):
            order = ("cold", "warm") if i % 2 == 0 else ("warm", "cold")
            for kind in order:
                if kind == "cold":
                    clear_bytecode(sp)
                else:
                    time_to_prompt(cmd, port)          # make sure the cache is there
                r = time_to_prompt(cmd, port)
                if r["seconds"] is None:
                    failed += 1
                (cold if kind == "cold" else warm).append(r["seconds"])
                (rss_cold if kind == "cold" else rss_warm).append(r["rss_bytes"])
            ver.append(version_time(cmd, neutral))
    finally:
        stub.kill()
        stub.wait(timeout=10)
    version = subprocess.run(cmd + ["--version"], capture_output=True, cwd=neutral,
                             text=True).stdout.strip()
    return {"build": version, "python": sys.version.split()[0], "platform": sys.platform,
            "runs": runs, "failed_runs": failed, "installed_bytes": size,
            "version_seconds": _stats(ver), "cold_to_prompt_seconds": _stats(cold),
            "warm_to_prompt_seconds": _stats(warm),
            "rss_at_prompt_bytes_warm": _stats(rss_warm),
            "rss_at_prompt_bytes_cold": _stats(rss_cold)}


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--venv", required=True)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    result = measure(Path(args.venv), args.runs)
    text = json.dumps(result, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["failed_runs"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
