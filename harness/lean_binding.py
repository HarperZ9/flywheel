"""lean_binding.py -- bind a Lean proof to the statement its task pinned.

Before this module the math oracle never read its task: any closed theorem
passed, `theorem unrelated : True := trivial` included (record
project-docs/records/2026-09-23-lean-oracle-task-binding.md). The fix follows
that record and `leanprover/comparator`:

1. The task pins a challenge before any candidate exists: a theorem name, its
   statement, and an optional header (imports and the definitions the
   statement uses).
2. The candidate compiles once, to one `.olean`. A kernel error or a sorry
   warning is FAIL. Every later step judges that one artifact, and its hash
   is rechecked after each step.
3. The challenge compiles, in a fresh directory, as the header followed by
   `theorem <name> : <statement> := sorry`.
4. The bind script (lean_bind_script.py) reads the candidate's `.olean` as
   data and checks that the pinned theorem exists with the challenge's exact
   elaborated type, that every constant the statement reaches means the same
   thing on both sides (a shadowed or redefined definition is refused), and
   which axioms the theorem depends on, walked from the artifact.
5. Any axiom outside the classical trio is FAIL.
6. leanchecker replays the same `.olean` (harness/lean_replay.py).

What none of this checks: whether the pinned statement says what a person
meant. The receipt marks that `spec_fidelity: UNVERIFIED`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

SCHEMA = "flywheel.lean-receipt/v2"
CHALLENGE_MODULE = "FlywheelChallenge"
#: A cold `import Lean` took 84 s on the measuring machine (n=1, 2026-10-04);
#: warm runs took 2 to 7 s. The bind step gets room for the cold case.
BIND_TIMEOUT = 300
_NAME_RE = re.compile(r"[^\W\d][\w'.]*\Z")
#: unverifiable_reason values this module adds to lean_replay's R_* set.
R_CHALLENGE = "challenge-compile-failed"
R_BIND = "binding-check-error"
R_UNSUPPORTED = "binding-unsupported"
R_SHADOW = "challenge-module-shadowed"
R_HASH = "statement-hash-mismatch"
SPEC_FIDELITY = {
    "status": "UNVERIFIED",
    "detail": ("the kernel checked the proof against the pinned statement; "
               "whether that statement says what its author intended is a "
               "human review this oracle does not perform")}
KERNEL = ("the Lean 4 kernel of the toolchain named here, then a leanchecker "
          "replay (plain mode) of the same compiled module")
AXIOMS_SOURCE = ("dependency walk of the pinned theorem over the compiled "
                 ".olean and its imports, not #print axioms and not the "
                 "precomputed axiom table an .olean can carry")


def parse_challenge(raw) -> tuple:
    """(challenge, "") for a usable pinned challenge, ({}, why) otherwise."""
    if not raw:
        return {}, "the task pins no challenge statement"
    if not isinstance(raw, dict):
        return {}, "the task's challenge is not an object"
    name, stmt = raw.get("theorem"), raw.get("statement")
    header = raw.get("header", "") or ""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return {}, "the challenge names no valid theorem"
    if not isinstance(stmt, str) or not stmt.strip():
        return {}, "the challenge carries no statement"
    if not isinstance(header, str):
        return {}, "the challenge header is not Lean source text"
    pinned = raw.get("statement_sha256", "") or ""
    return {"theorem": name, "statement": stmt.strip(), "header": header,
            "statement_sha256": pinned}, ""


def challenge_source(ch: dict) -> str:
    head = ch["header"].rstrip()
    stmt = f"theorem {ch['theorem']} : {ch['statement']} := sorry\n"
    return f"{head}\n\n{stmt}" if head else stmt


def challenge_sha256(ch: dict) -> str:
    body = json.dumps({k: ch[k] for k in ("header", "statement", "theorem")},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _bind_doc(out: str) -> dict:
    """The bind script's JSON, or an error doc when it printed none."""
    for line in reversed((out or "").strip().splitlines()):
        if line.startswith("{"):
            try:
                doc = json.loads(line)
            except ValueError:
                break
            return doc if isinstance(doc, dict) else {}
    return {"status": "error",
            "detail": "the bind check printed no result: " + (out or "")[:400]}


class _Injected:
    """The same steps as the live path, through an injected runner."""
    olean_sha = staticmethod(lambda: "injected")

    def __init__(self, runner):
        self.runner = runner

    def compile_candidate(self, code):
        return self.runner(["lean", "-o", "Candidate.olean"], code)

    def compile_challenge(self, src):
        return self.runner(["lean", "-o", f"{CHALLENGE_MODULE}.olean"], src)

    def bind(self, code, thm):
        return self.runner(["lean", "--run", "bind", "Candidate.olean",
                            CHALLENGE_MODULE, thm], code)

    def replay(self, code):
        from .lean_replay import MODULE, R_CHECKER, _checked, _result
        try:
            return _checked(*self.runner(["leanchecker", MODULE], code))
        except OSError as exc:
            return _result(None, f"leanchecker could not be started ({exc})",
                           reason=R_CHECKER)


class _Live:
    """One temporary tree: the candidate source and build, the challenge
    source and build, and the bind script. The candidate build directory is
    never on the bind step's search path."""

    def __init__(self, root: Path, lean: str, checker: str, libdir: str):
        self.root, self.lean = root, lean
        self.checker, self.libdir = checker, libdir
        for d in ("c", "cb", "ch", "chb"):
            (root / d).mkdir()
        self.olean = root / "cb" / "Candidate.olean"

    def olean_sha(self):
        return _sha_file(self.olean)

    def _compile(self, src: str, sub: str, module: str):
        from .lean_replay import run_killable
        path = self.root / sub / f"{module}.lean"
        path.write_text(src, encoding="utf-8")
        out = self.root / (sub + "b") / f"{module}.olean"
        return run_killable([self.lean, f"--root={self.root / sub}", "-o",
                             str(out), str(path)], label=f"lean {module}")

    def compile_candidate(self, code):
        return self._compile(code, "c", "Candidate")

    def compile_challenge(self, src):
        return self._compile(src, "ch", CHALLENGE_MODULE)

    def bind(self, code, thm):
        from .lean_bind_script import SOURCE
        from .lean_replay import run_killable
        inherited = os.environ.get("LEAN_PATH", "")
        entries = inherited.split(os.pathsep) if inherited else []
        for entry in entries:
            base = Path(entry)
            if (base / CHALLENGE_MODULE).exists() or \
                    (base / f"{CHALLENGE_MODULE}.olean").exists():
                return None, f"the search path entry {entry} also holds " \
                             f"a module named {CHALLENGE_MODULE}"
        script = self.root / "Bind.lean"
        script.write_text(SOURCE, encoding="utf-8")
        env = dict(os.environ)
        env["LEAN_PATH"] = os.pathsep.join([*entries, str(self.root / "chb")])
        env["LEAN_SYSROOT"] = str(Path(self.libdir).parent.parent)
        return run_killable([self.lean, "--run", str(script), str(self.olean),
                             CHALLENGE_MODULE, thm], env=env,
                            timeout=BIND_TIMEOUT, label="lean bind check")

    def replay(self, code):
        from .lean_replay import _check_live
        return _check_live(self.checker, self.libdir, self.root / "cb")


def bound_check(code: str, raw_challenge, *, runner=None) -> dict:
    """Judge `code` against the pinned challenge. passed is True only when
    every step in the module docstring passed; False when the candidate was
    refused; None when a step could not judge (the reason says which)."""
    from .lean_oracle import _lean_exe, _refused_up_front, _toolchain
    from .lean_binding_judge import receipt
    sha = hashlib.sha256((code or "").encode("utf-8")).hexdigest()
    ch, why = parse_challenge(raw_challenge)
    if not ch:
        return receipt(sha, None, "", why, {}, reason="challenge-unpinned")
    refused = _refused_up_front(code, sha)
    if refused:
        return receipt(sha, False, "", refused["kernel_output"], ch)
    if runner is not None:
        from .lean_binding_judge import judge
        return judge(code, ch, _Injected(runner), sha, "injected")
    exe = _lean_exe()
    if exe is None:
        return receipt(sha, None, "", "no lean toolchain installed; the lane "
                       "is DECLARED, not live", ch, reason="lean-missing")
    from .lean_replay import R_CHECKER, toolchain_paths
    checker, libdir, why = toolchain_paths(exe)
    if checker is None:
        return receipt(sha, None, "", why, ch, reason=R_CHECKER)
    from .lean_binding_judge import judge
    with tempfile.TemporaryDirectory(prefix="flywheel-lean-bind-",
                                     ignore_cleanup_errors=True) as td:
        steps = _Live(Path(td), exe, checker, libdir)
        return judge(code, ch, steps, sha, _toolchain(exe))
