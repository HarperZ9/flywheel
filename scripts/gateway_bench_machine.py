"""gateway_bench_machine.py -- the machine a gateway benchmark ran on, for its record.

Used by scripts/bench_gateway_overhead.py. Nothing here names the machine's
owner: no host name, user name or path.
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


def _cpu() -> str:
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], text=True,
                                  capture_output=True, timeout=10).stdout.strip()
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"cpu model not read ({type(exc).__name__})", file=sys.stderr)
    return platform.processor() or "unknown"


def _ram_gb() -> "float | None":
    try:
        if sys.platform == "win32":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in
                    ("total", "free", "page", "page_free", "virt", "virt_free", "ext")]
            status = Status(length=ctypes.sizeof(Status))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.total / 2 ** 30, 1)
        import os
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except (OSError, ValueError, AttributeError) as exc:
        print(f"memory size not read ({type(exc).__name__})", file=sys.stderr)
        return None


def machine() -> dict:
    """The machine, with nothing that names its owner: no host, user or path."""
    return {"cpu": _cpu(), "logical_cpus": __import__("os").cpu_count(), "ram_gb": _ram_gb(),
            "os": f"{platform.system()} {platform.release()} (build {platform.version()})",
            "python": platform.python_version()}
