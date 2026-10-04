"""lean_external_kernel.py -- re-check the bound theorem with a second kernel.

After the binding check and the leanchecker replay accept, the same compiled
module goes to a kernel that shares no code with Lean's C++ kernel:

1. lean4export writes the pinned theorem and its dependency closure from the
   candidate's `.olean`, and the challenge's theorem from the challenge's.
2. Python (harness/lean_ndjson.py) reads both exports: the candidate's
   declaration must be a theorem whose alpha-invariant statement hash equals
   the challenge's, and every constant the statement reaches must be declared
   identically in both.
3. nanoda type-checks every declaration in the candidate's export, with the
   classical trio as the only permitted axioms, and must name the pinned
   theorem among them.

verdict ACCEPTED counts as the second agreeing kernel. REJECTED (nanoda
refused, or the exported statement differs) is a disagreement, and the bound
check fails closed. UNAVAILABLE and ERROR judged nothing, and the bound check
is UNVERIFIABLE: one kernel never makes a PASS.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

ACCEPTED, REJECTED = "ACCEPTED", "REJECTED"
UNAVAILABLE, ERROR, NOT_RUN = "UNAVAILABLE", "ERROR", "NOT_RUN"
EXPORT_TIMEOUT = 180
NANODA_TIMEOUT = 300
_CHECKED = re.compile(r"Checked (\d+) declarations with no errors")
#: nanoda reports a failed kernel check by panicking (Rust's exit 101) or by
#: returning an error, which it prints after "Error:" with exit 1. Errors that
#: mean it could not read its input judged nothing (observed 2026-10-04).
_PANIC_RC = 101
_INPUT_ERRORS = ("Error: Failed to open", "Error: failed to open",
                 "Error: expected", "Error: export format version")


def not_run(detail: str = "") -> dict:
    return {"verdict": NOT_RUN, "detail": detail}


def nanoda_config(export_path: str, theorem: str) -> dict:
    from .lean_oracle import _ALLOWED_AXIOMS
    return {"export_file_path": export_path, "use_stdin": False,
            "permitted_axioms": sorted(_ALLOWED_AXIOMS),
            "unpermitted_axiom_hard_error": True,
            "nat_extension": True, "string_extension": True,
            "pp_declars": [theorem], "pp_to_stdout": True,
            "print_success_message": True}


def classify(rc, out: str) -> tuple:
    """(verdict, declarations checked or None) from nanoda's exit and text."""
    text = out or ""
    m = _CHECKED.search(text)
    if rc == 0 and m:
        return ACCEPTED, int(m.group(1))
    if rc == _PANIC_RC and "panicked at" in text:
        return REJECTED, None
    head = text.lstrip()
    if rc == 1 and head.startswith("Error:") and \
            not head.startswith(_INPUT_ERRORS):
        return REJECTED, None
    return ERROR, None


def _out(verdict: str, detail: str, tools: dict, **kw) -> dict:
    from .lean_external_tools import record
    doc = record(tools) if tools else {}
    doc.update({"verdict": verdict, "detail": (detail or "").strip()[:800],
                "statement_sha256": "", "export_sha256": "",
                "declarations_checked": None})
    doc.update(kw)
    return doc


def _export(steps, which: str, theorem: str):
    """(text, "") or ("", why) for one export."""
    try:
        rc, text = steps.export(which, theorem)
    except OSError as exc:
        return "", f"lean4export could not be started ({exc})"
    if rc is None or rc != 0:
        return "", f"lean4export of the {which} failed: {(text or '')[:400]}"
    return text, ""


def external_check(steps, ch: dict, bind_doc: dict) -> dict:
    """Run the three steps in the module docstring; the receipt block."""
    from .lean_ndjson import Export, ExportError, meaning_mismatches
    if steps is None:
        return _out(UNAVAILABLE, "these steps have no external kernel", {})
    tools, why = steps.tools()
    if not tools:
        return _out(UNAVAILABLE, why, {})
    thm = ch["theorem"]
    texts = {}
    for which in ("candidate", "challenge"):
        texts[which], why = _export(steps, which, thm)
        if why:
            return _out(ERROR, why, tools)
    try:
        cand, chal = Export(texts["candidate"]), Export(texts["challenge"])
    except ExportError as exc:
        return _out(ERROR, f"an export could not be read: {exc}", tools)
    ex_sha = hashlib.sha256(texts["candidate"].encode("utf-8")).hexdigest()
    githash = bind_doc.get("lean_githash") or ""
    got = str(cand.meta.get("lean", {}).get("githash", ""))
    if githash and got != githash:
        return _out(ERROR, f"the export came from Lean {got[:12]}, not the "
                    f"toolchain that compiled the candidate ({githash[:12]})",
                    tools, export_sha256=ex_sha)
    stmt = chal.statement_sha256(thm)
    kw = {"statement_sha256": stmt, "export_sha256": ex_sha,
          "export_format": str(cand.meta.get("format", {}).get("version"))}
    if cand.decls.get(thm, ("",))[0] != "thm":
        return _out(REJECTED, f"the candidate's export holds no theorem "
                    f"named {thm}", tools, **kw)
    if cand.statement_sha256(thm) != stmt:
        return _out(REJECTED, f"the exported {thm} states a different "
                    "proposition than the challenge", tools, **kw)
    diffs = meaning_mismatches(cand, chal, thm)
    if diffs:
        return _out(REJECTED, "; ".join(diffs[:8]), tools, **kw)
    try:
        rc, out = steps.nanoda(texts["candidate"], thm)
    except OSError as exc:
        return _out(UNAVAILABLE, f"nanoda could not be started ({exc})",
                    tools, **kw)
    verdict, count = classify(rc, out)
    if verdict == ERROR and rc == 124:
        out = f"nanoda timed out: {out}"
    return _out(verdict, out, tools, declarations_checked=count, **kw)


class LiveExternal:
    """lean4export and nanoda run as processes, from the pinned build."""

    def __init__(self, root: Path, libdir: str, bindir: Path):
        self.root, self.libdir, self.bindir = root, libdir, bindir
        self._tools = None

    def tools(self):
        from .lean_external_tools import resolve
        self._tools, why = resolve()
        return self._tools, why

    def export(self, which: str, theorem: str):
        from .lean_binding import CHALLENGE_MODULE
        from .lean_replay import run_killable, search_path
        build, module = ((self.root / "cb", "Candidate") if which ==
                         "candidate" else (self.root / "chb", CHALLENGE_MODULE))
        entries = search_path(self.libdir, build,
                              os.environ.get("LEAN_PATH", ""))
        for entry in entries[:-1]:
            base = Path(entry)
            if (base / module).exists() or (base / f"{module}.olean").exists():
                return None, (f"the search path entry {entry} also holds a "
                              f"module named {module}")
        env = dict(os.environ)
        env["LEAN_PATH"] = os.pathsep.join(entries)
        # lean4export links the toolchain's shared runtime, which Windows
        # finds through PATH.
        env["PATH"] = os.pathsep.join([str(self.bindir),
                                       env.get("PATH", "")])
        return run_killable([self._tools["lean4export"]["binary"], module,
                             "--", theorem], env=env, timeout=EXPORT_TIMEOUT,
                            label="lean4export")

    def nanoda(self, text: str, theorem: str):
        from .lean_replay import run_killable
        export = self.root / "candidate.ndjson"
        export.write_text(text, encoding="utf-8")
        cfg = self.root / "nanoda.json"
        cfg.write_text(json.dumps(nanoda_config(str(export), theorem)),
                       encoding="utf-8")
        return run_killable([self._tools["nanoda"]["binary"], str(cfg)],
                            timeout=NANODA_TIMEOUT, label="nanoda")


class InjectedExternal:
    """The same steps through an injected runner. A runner that raises
    OSError for a tool models that tool missing."""

    def __init__(self, runner, code: str, challenge_src: str):
        self.runner, self.code, self.src = runner, code, challenge_src

    def tools(self):
        try:
            self.runner(["nanoda_bin", "--help"], self.code)
        except OSError as exc:
            return {}, f"nanoda is not installed ({exc})"
        from .lean_external_tools import PINS
        return {k: dict(v, binary_sha256="injected")
                for k, v in PINS.items()}, ""

    def export(self, which: str, theorem: str):
        from .lean_binding import CHALLENGE_MODULE
        module = "Candidate" if which == "candidate" else CHALLENGE_MODULE
        src = self.code if which == "candidate" else self.src
        return self.runner(["lean4export", module, "--", theorem], src)

    def nanoda(self, text: str, theorem: str):
        return self.runner(["nanoda_bin", "nanoda.json"], text)
