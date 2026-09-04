"""proof_run.py -- hand the emitted file to Lean and read back what it said.

Emitting a proof file is not checking it. This module runs `lean` on what
`proof_lean` wrote and turns the result into the same three-way verdict the
rest of the check speaks, so a caller branches on one vocabulary.

    PASS           the kernel closed every obligation, and the axioms it
                   names are the ones the file declared
    FAIL           the kernel refused an obligation, or `confirmed` came out
                   resting on `sorryAx`
    UNVERIFIABLE   no kernel ran: Lean is not installed, or it timed out, or
                   it failed in a way that is not a statement about the file

A refusal here is worth as much as agreement. The Python check and the Lean
file are two readings of one answer, built from different code, and where they
disagree one of them is wrong. That is the finding, not a defect in the
artifact, so a file the kernel rejects is still written out.

Running Lean means running a program, so nothing here goes looking for one on
its own. A caller asks by name or passes an explicit path, the same way a
command authority is asked for rather than assumed.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .verdict import Verdict

# `#print axioms Some.Name` prints one of these two lines. Both are matched
# rather than only the first, because a file resting on nothing is the good
# case and reading it as "no answer" would report the strongest result as the
# weakest one.
AXIOMS = re.compile(r"depends on axioms: \[([^\]]*)\]")
NO_AXIOMS = re.compile(r"does not depend on any axioms")
VERSION = re.compile(r"version ([0-9][^,\s]*)")
# Lean opens each diagnostic with `<file>:<line>:<col>: error: `, then wraps the
# message over as many lines as it needs. Matching the opener and reading to the
# next one keeps the proposition that failed, which is the half worth reading.
LOCATION = re.compile(r"^(?P<file>.*?):(?P<line>\d+):(?P<col>\d+): "
                      r"(?P<level>error|warning): ", re.M)
# `#print axioms` reports on the same stream, so a diagnostic that runs to
# the end of the output would swallow it into the error message.
AXIOM_LINE = re.compile(r"^'[^']*' (?:depends on axioms|does not depend)", re.M)
TIMEOUT = 180


def lean_path(explicit=None) -> str | None:
    """The Lean to run, or None. Never guesses beyond PATH."""
    if explicit:
        found = Path(explicit)
        return str(found) if found.exists() else None
    return shutil.which("lean")


def lean_version(lean: str) -> str:
    try:
        out = subprocess.run([lean, "--version"], capture_output=True, text=True,
                             timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    found = VERSION.search(out.stdout or "")
    return f"lean {found.group(1)}" if found else "lean"


def diagnostics(output: str) -> list[str]:
    """Lean's errors, one to a line, with the directory taken off the front.

    A report can be written to a file that leaves this machine, and the path a
    proof was checked at is not a fact about the answer. The file name, line
    and column stay, because they point into the artifact the caller has.
    """
    found = list(LOCATION.finditer(output))
    out = []
    for index, match in enumerate(found):
        if match.group("level") != "error":
            continue
        end = found[index + 1].start() if index + 1 < len(found) else len(output)
        raw = output[match.end():end]
        stop = AXIOM_LINE.search(raw)
        body = " ".join(raw[:stop.start() if stop else len(raw)].split())
        out.append(f"{Path(match.group('file')).name}:{match.group('line')}:"
                   f"{match.group('col')}: {body}")
    return out


def _unverifiable(reason: str, checker: str = "") -> dict:
    return {"verdict": Verdict.UNVERIFIABLE.value, "checker": checker,
            "axioms": [], "errors": [], "reason": reason}


def read_result(output: str, returncode: int) -> dict:
    """What Lean's own output says about the file it just read."""
    found = AXIOMS.search(output)
    axioms = ([part.strip() for part in found.group(1).split(",") if part.strip()]
              if found else [])
    errors = diagnostics(output)
    if "sorryAx" in axioms or errors:
        # `sorryAx` is Lean's own name for an obligation that did not close.
        # It reaches the axiom list through the same channel a real assumption
        # does, which is why the list is the thing to read rather than the
        # exit code.
        return {"verdict": Verdict.FAIL.value, "checker": "", "axioms": axioms,
                "errors": errors[:5],
                "reason": errors[0] if errors else "confirmed rests on sorryAx"}
    if returncode != 0:
        return _unverifiable(f"lean exited {returncode} without reporting an "
                             f"error about the file")
    if not found and not NO_AXIOMS.search(output):
        return _unverifiable("lean printed no axiom list, so nothing was checked")
    return {"verdict": Verdict.PASS.value, "checker": "", "axioms": axioms,
            "errors": [], "reason": "every obligation closed"}


def run_proof(path, *, lean=None, timeout: int = TIMEOUT) -> dict:
    """Run Lean on a file already on disk and report what it decided."""
    binary = lean_path(lean)
    if binary is None:
        return _unverifiable("lean is not on PATH, so the file was written but "
                             "not checked")
    checker = lean_version(binary)
    try:
        done = subprocess.run([binary, str(path)], capture_output=True, text=True,
                              timeout=timeout, cwd=str(Path(path).parent))
    except subprocess.TimeoutExpired:
        return _unverifiable(f"lean did not finish in {timeout}s", checker)
    except OSError as exc:
        return _unverifiable(f"lean could not be run: {exc}", checker)
    result = read_result((done.stdout or "") + (done.stderr or ""), done.returncode)
    result["checker"] = checker
    return result


def prove(source: str, path=None, *, lean=None, timeout: int = TIMEOUT) -> dict:
    """Write the Lean source, check it, and say where it went.

    With no path the file lands in a temporary directory and is left there.
    A caller that asked for a proof and got a refusal wants to read the file
    that was refused, and deleting it would leave only a sentence about it.
    """
    if path is None:
        path = Path(tempfile.mkdtemp(prefix="flywheel-proof-")) / "Answer.lean"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    result = run_proof(path, lean=lean, timeout=timeout)
    result["file"] = str(path)
    return result
