"""lean_oracle.py -- the apex oracle: the kernel decides, nothing else.

Aria (arXiv 2607.06341) is the existence proof for this architecture: give
an agent full freedom and let a proof kernel be the sole acceptance
authority -- the proof object IS the receipt. This is that lane on Lean 4:
candidate code is written to a file, `lean` checks it, and the verdict is
the kernel's exit. No learned model, no heuristic, no partial credit. The
receipt carries the code hash, the toolchain identity, and the kernel's
own words on failure. A missing toolchain is a DECLARED state (passed:
null), never a fake pass -- and the strongest claim this platform can ever
carry is one this oracle accepted.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SCHEMA = "flywheel.lean-receipt/v1"
_TIMEOUT = 90


def _lean_exe() -> "str | None":
    exe = shutil.which("lean")
    if exe:
        return exe
    home = Path(os.path.expanduser("~")) / ".elan" / "bin" / "lean.exe"
    return str(home) if home.is_file() else None


def lean_available() -> bool:
    return _lean_exe() is not None


def _run(argv: list, code: str) -> tuple:
    """Default runner: write the candidate, let the kernel judge it.
    Popen + tree-kill (the oracle.py discipline): a hostile candidate
    costs one timeout, never a wedged harness."""
    from .oracle import _kill_tree
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "candidate.lean"
        path.write_text(code, encoding="utf-8")
        proc = subprocess.Popen(argv + [str(path)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        try:
            out, _ = proc.communicate(timeout=_TIMEOUT)
            return proc.returncode, (out or b"").decode("utf-8",
                                                        errors="replace")
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.communicate(timeout=10)
            except Exception:
                pass
            return 124, f"kernel timed out after {_TIMEOUT}s"


def _toolchain(exe: str) -> str:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True,
                           text=True, timeout=30)
        return (r.stdout or "").strip().splitlines()[0] if r.stdout else ""
    except Exception:
        return "unknown"


def lean_check(code: str, *, runner=None) -> dict:
    """Judge `code` with the Lean kernel. `runner(argv, code) -> (rc, out)`
    is injectable for tests; passed is True/False from the kernel, or None
    (DECLARED) when no toolchain exists to ask.

    Admitted holes are refused BEFORE the kernel runs: Lean exits 0 on
    `sorry` with only a warning, so a naive exit-code check would accept
    a false statement wearing an admitted hole (found live 2026-07-14).
    The hygiene screen catches sorry/axiom up front, and the kernel's
    own sorry warning is treated as refusal belt-and-braces."""
    sha = hashlib.sha256((code or "").encode("utf-8")).hexdigest()
    from .benchmark_hygiene import screen_statements
    flagged = screen_statements([code or ""]).get("flagged", [])
    if flagged:
        defect = flagged[0]["defect"]
        return {"schema": SCHEMA, "passed": False, "code_sha256": sha,
                "toolchain": "",
                "kernel_output": f"refused before the kernel ran: the "
                                 f"candidate carries '{defect}' (an "
                                 "admitted hole or smuggled axiom is "
                                 "not a proof)",
                "note": "acceptance decided solely by the Lean kernel, "
                        "and only over candidates that actually ask it "
                        "to decide"}
    exe = _lean_exe()
    if runner is None and exe is None:
        return {"schema": SCHEMA, "passed": None, "code_sha256": sha,
                "toolchain": "",
                "kernel_output": "no lean toolchain installed; the lane is "
                                 "DECLARED, not live",
                "note": "the kernel is the sole acceptance authority; "
                        "without it nothing is claimed"}
    if runner is not None:
        rc, out = runner(["lean"], code)
        toolchain = "injected"
    else:
        rc, out = _run([exe], code)
        toolchain = _toolchain(exe)
    # belt-and-braces: Lean quotes the word variously (declaration uses
    # 'sorry' / `sorry` / sorry) and a sorry/admit exit is 0 with only a
    # warning. Match the warning under any quoting, and also treat any
    # explicit 'sorry'/'sorryAx' warning as refusal.
    warn = (out or "").lower()
    uses_hole = bool(re.search(r"uses\s+[`'\"]?sorry", warn)) \
        or "declaration uses" in warn and "sorry" in warn
    return {"schema": SCHEMA, "passed": rc == 0 and not uses_hole,
            "code_sha256": sha,
            "toolchain": toolchain,
            "kernel_output": (out or "").strip()[:2000],
            "note": "acceptance decided solely by the Lean kernel; a "
                    "sorry/admit warning is refusal; hygiene refuses "
                    "kernel-bypass constructs before the exit is trusted; "
                    "re-run the code under the named toolchain to re-derive"}
