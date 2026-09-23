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

An exit of 0 is the weakest rung of the Lean reference's validation ladder.
The receipt's `validation_level` names the highest rung a candidate cleared:
the kernel exit, then `#print axioms`, then a leanchecker replay of the
compiled module in a fresh process (harness/lean_replay.py). The replay is
the rung that refuses a declaration a metaprogram stored with the kernel
check switched off; the exit code and the axiom list both pass that file.
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

# The classical trio: everything else in a footprint is an escape hatch the
# kernel did not re-check (Lean.ofReduceBool from native_decide,
# Lean.trustCompiler from @[implemented_by], sorryAx from an admitted hole).
_ALLOWED_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
_FOOTPRINT_RE = re.compile(r"'([^']+)'\s+depends on axioms:\s*\[([^\]]*)\]")
_NO_AXIOMS_RE = re.compile(r"'([^']+)'\s+does not depend on any axioms")

_NOTE = ("acceptance decided solely by the Lean kernel; a sorry/admit warning "
         "is refusal; hygiene refuses kernel-bypass constructs before the exit "
         "is trusted; the axiom footprint of every named theorem is audited "
         "against the classical trio on accept; the compiled module is then "
         "replayed through leanchecker in a fresh process; re-run the code "
         "under the named toolchain to re-derive")


def _decl_names(code: str) -> list:
    """Named theorems/lemmas in the candidate, for the footprint audit."""
    return re.findall(r"(?:^|\n)\s*(?:theorem|lemma)\s+([A-Za-z_][\w'.]*)",
                      code or "")


def _audit_footprint(out: str) -> tuple:
    """Parse #print axioms output into {name: [axioms]} plus the set of
    axioms outside the classical trio. 'does not depend on any axioms'
    lines simply do not match and contribute nothing forbidden."""
    footprint: dict = {}
    forbidden: list = []
    for name, axes in _FOOTPRINT_RE.findall(out or ""):
        used = [a.strip() for a in axes.split(",") if a.strip()]
        footprint[name] = used
        forbidden.extend(a for a in used if a not in _ALLOWED_AXIOMS)
    for name in _NO_AXIOMS_RE.findall(out or ""):
        footprint.setdefault(name, [])
    return footprint, sorted(set(forbidden))


def _lean_exe() -> "str | None":
    exe = shutil.which("lean")
    if exe:
        return exe
    home = Path(os.path.expanduser("~")) / ".elan" / "bin" / "lean.exe"
    return str(home) if home.is_file() else None


def lean_available() -> bool:
    return _lean_exe() is not None


def _run(argv: list, code: str) -> tuple:
    """Default runner: write the candidate, let the kernel judge it. The
    spawn reaps the whole process tree on timeout (lean_replay.run_killable,
    the oracle.py discipline): a hostile candidate costs one timeout."""
    from .lean_replay import run_killable
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "candidate.lean"
        path.write_text(code, encoding="utf-8")
        return run_killable(argv + [str(path)], timeout=_TIMEOUT,
                            label="kernel")


def _toolchain(exe: str) -> str:
    try:
        r = subprocess.run([exe, "--version"], capture_output=True,
                           text=True, timeout=30)
        return (r.stdout or "").strip().splitlines()[0] if r.stdout else ""
    except Exception:
        return "unknown"


def _receipt(sha: str, passed, toolchain: str, output: str, note: str, *,
             footprint=None, level: str = "none", replay=None,
             reason: str = "") -> dict:
    """One receipt shape for every exit. `validation_level` names the highest
    rung of the Lean reference's ladder the candidate cleared, and
    `leanchecker` is the replay record, or None when no replay ran."""
    from .lean_replay import LADDER
    doc = {"schema": SCHEMA, "passed": passed, "code_sha256": sha,
           "toolchain": toolchain, "kernel_output": output, "note": note,
           "validation_level": level, "validation_ladder": list(LADDER),
           "leanchecker": replay}
    if footprint is not None:
        doc["axiom_footprint"] = footprint
    if reason:
        doc["unverifiable_reason"] = reason
    return doc


def _refused_up_front(code: str, sha: str) -> "dict | None":
    """Admitted holes and kernel-bypass constructs are refused before the
    kernel runs: Lean exits 0 on `sorry` with only a warning, so a naive
    exit-code check would accept a false statement wearing one (found live
    2026-07-14). The kernel's own sorry warning is refusal as well."""
    from .benchmark_hygiene import screen_statements
    flagged = screen_statements([code or ""]).get("flagged", [])
    if not flagged:
        return None
    return _receipt(
        sha, False, "",
        f"refused before the kernel ran: the candidate carries "
        f"'{flagged[0]['defect']}' (an admitted hole or smuggled axiom is "
        "not a proof)",
        "acceptance decided solely by the Lean kernel, and only over "
        "candidates that actually ask it to decide")


def _uses_hole(out: str) -> bool:
    """Lean quotes the word variously (declaration uses 'sorry' / `sorry` /
    sorry), and a sorry/admit exit is 0 with only a warning."""
    warn = (out or "").lower()
    return bool(re.search(r"uses\s+[`'\"]?sorry", warn)) \
        or "declaration uses" in warn and "sorry" in warn


def _audit(code: str, run, sha: str, toolchain: str) -> tuple:
    """#print axioms over every named theorem. Returns (refusal or None,
    footprint, audited); audited is True only when every name answered."""
    names = _decl_names(code or "")
    if not names:
        return None, {}, False
    audit_code = (code or "") + "\n" + "\n".join(
        f"#print axioms {n}" for n in names) + "\n"
    arc, aout = run(audit_code)
    if arc != 0:
        return _receipt(
            sha, False, toolchain,
            "accepted by exit code but the axiom footprint audit failed to "
            "run; fail closed. Audit output: " + (aout or "").strip()[:800],
            "an accept the footprint cannot vouch for is not an accept",
            footprint={}, level="exit_code"), {}, False
    footprint, forbidden = _audit_footprint(aout)
    if forbidden:
        return _receipt(
            sha, False, toolchain,
            "kernel exit 0 but the proof leans on axioms outside the "
            "classical trio: " + ", ".join(forbidden)
            + " (a decision the kernel did not re-check is not a proof)",
            "footprint audited via #print axioms; allowed: propext, "
            "Classical.choice, Quot.sound",
            footprint=footprint, level="exit_code"), footprint, False
    return None, footprint, all(n in footprint for n in names)


def _after_replay(sha: str, toolchain: str, out: str, footprint: dict,
                  audited: bool, rep: dict) -> dict:
    """Fold the leanchecker result in. A replay that could not run is
    UNVERIFIABLE (passed None), never a pass; one that refused is a FAIL."""
    from .lean_replay import level
    below = level(kernel_ok=True, audited=audited, replayed=False)
    passed_below = ("kernel exit 0 and the footprint audit passed" if audited
                    else "kernel exit 0 (axiom rung not reached)")
    if rep["ok"] is None:
        return _receipt(
            sha, None, toolchain,
            passed_below + ", but leanchecker could not replay the module: "
            + rep["detail"],
            "fail closed: an accept leanchecker did not replay is not a pass",
            footprint=footprint, level=below, replay=rep["record"],
            reason="leanchecker-unavailable")
    if rep["ok"] is False:
        return _receipt(
            sha, False, toolchain, passed_below + ", but " + rep["detail"],
            "leanchecker replays the declarations the compiled module adds; "
            "a declaration the elaborator stored without a kernel check is "
            "refused there",
            footprint=footprint, level=below, replay=rep["record"])
    return _receipt(sha, True, toolchain, (out or "").strip()[:2000], _NOTE,
                    footprint=footprint, replay=rep["record"],
                    level=level(kernel_ok=True, audited=audited,
                                replayed=True))


def lean_check(code: str, *, runner=None) -> dict:
    """Judge `code` with the Lean kernel. `runner(argv, code) -> (rc, out)`
    is injectable for tests; passed is True/False from the kernel, or None
    (DECLARED) when no toolchain exists to ask or leanchecker cannot run.

    Each rung runs only after the one below it passed: the hygiene screen,
    the kernel exit with a sorry warning read as refusal, #print axioms over
    every named theorem, and a leanchecker replay of the compiled module.
    The replay catches a declaration a metaprogram added with the kernel
    check switched off, which the rungs below it all pass."""
    from .lean_replay import replay
    sha = hashlib.sha256((code or "").encode("utf-8")).hexdigest()
    refused = _refused_up_front(code, sha)
    if refused:
        return refused
    exe = _lean_exe()
    if runner is None and exe is None:
        return _receipt(sha, None, "", "no lean toolchain installed; the lane "
                        "is DECLARED, not live",
                        "the kernel is the sole acceptance authority; "
                        "without it nothing is claimed",
                        reason="lean-missing")
    if runner is not None:
        run, toolchain = (lambda c: runner(["lean"], c)), "injected"
    else:
        run, toolchain = (lambda c: _run([exe], c)), _toolchain(exe)
    rc, out = run(code)
    if rc != 0 or _uses_hole(out):
        return _receipt(sha, False, toolchain, (out or "").strip()[:2000],
                        _NOTE, footprint={})
    refusal, footprint, audited = _audit(code, run, sha, toolchain)
    if refusal:
        return refusal
    rep = replay(code or "", lean=exe, runner=runner, toolchain=toolchain)
    return _after_replay(sha, toolchain, out, footprint, audited, rep)


# The Oracle-Protocol adapter lives in its own module for the line budget;
# the registry and the tests import it from here.
from .lean_oracle_adapter import LeanOracle  # noqa: E402,F401
