#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Regenerate the EMET *witness* walkthrough transcript, deterministically.

This is the companion render to walkthrough/render.py. Where that one traces a
single artifact through the membrane commands, this one demonstrates the WITNESS
arc end to end, in three real captures the essay annotates:

  (1) THE STRUCTURAL GATE - run the repo Python so that it imports `verdict` and
      calls governed(LATTICE, "TRUSTED"): it RAISES VerdictError at construction
      time, inside the TCB, before a byte reaches stdout (Boundary 1 is
      structural, not a review rule). Then governed(REVERT, "REVERTIBLE")
      returns the token VERBATIM - the gate guards WHAT, never alters bytes.

  (2) THE INDEPENDENT WITNESS - run `python test_organs.py` from the repo root.
      The RUN, not a review, confirms the organs report the re-derivable FACT
      (REVERTIBLE / NOT_REVERTIBLE), the ALLOW/BLOCK permission words gone.

  (3) ONE WITNESS THRICE - run the language-agnostic conformance runner against
      the Python reference (membrane.py) and the Node port (impl/js/emet.js).
      Both print CONFORMANCE 35/35. They AGREE - and they share an author, so
      the agreement shows the spec is implementable, not yet independently
      re-derivable (SPEC s.12). The annotation in the essay is the load-bearing
      part: same-author agreement is not an independent witness.

Determinism: each capture is a function of fixed repo bytes plus the stdlib, so
same `verdict.py` / `organs.py` / `membrane.py` / `emet.js` + same vectors ->
byte-identical transcript. The only volatile field is an absolute temp path the
structural-gate snippet runs from; it is normalized to <SANDBOX>. `--check`
asserts the committed transcript still matches a fresh render (CI drift-guard).

Stdlib only. No third-party imports. Like walkthrough/render.py.
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
OUT = os.path.join(HERE, "transcript.txt")

# The structural-gate probe. Run by the SAME interpreter, importing the repo's
# verdict.py. Two facts are captured: (1) emitting an authority verdict RAISES
# inside the TCB; (2) a governed token returns VERBATIM. Kept to stdlib + the
# repo module so the capture is itself re-derivable.
GATE_PROBE = r'''
import sys, traceback
sys.path.insert(0, REPO_PLACEHOLDER)
import verdict

# (a) Boundary 1 is STRUCTURAL: an authority verdict fails at construction,
#     before any byte could reach stdout.
try:
    verdict.governed(verdict.LATTICE, "TRUSTED")
    print("LEAK: governed(LATTICE, 'TRUSTED') returned without raising")
except verdict.VerdictError as e:
    print("raised VerdictError: " + str(e).split(";")[0])

# (b) A governed token returns VERBATIM: the gate guards WHAT, never WHAT-BYTES.
tok = verdict.governed(verdict.REVERT, "REVERTIBLE")
print("governed(REVERT, 'REVERTIBLE') -> " + repr(tok)
      + "  (verbatim: " + str(tok == "REVERTIBLE") + ")")
'''


def normalize(text, *volatile):
    out = text.replace("\r\n", "\n")
    for v in volatile:
        if not v:
            continue
        out = out.replace(v, "<SANDBOX>").replace(v.replace(os.sep, "/"), "<SANDBOX>")
    # The repo path can appear in a traceback frame or the probe echo; pin it.
    out = out.replace(REPO, "<REPO>").replace(REPO.replace(os.sep, "/"), "<REPO>")
    # unittest prints a wall-clock duration ("Ran 3 tests in 0.439s"); the only
    # volatile field in the witness run. Pin it so the transcript re-derives.
    out = re.sub(r"Ran (\d+) tests? in [0-9.]+s", r"Ran \1 tests in <dur>s", out)
    return out


def _run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    # Conformance runner and unittest write to stdout/stderr respectively; fold
    # both so the witness lines are captured wherever they land.
    body = (p.stdout or "") + (p.stderr or "")
    return body, p.returncode


def _block(title, shown_cmd, body, code, sandbox=None):
    body = normalize(body.rstrip("\n"), sandbox)
    return (title + "\n$ " + shown_cmd + "\n" + body
            + "\n(exit " + str(code) + ")")


def render():
    blocks = []

    # (1) THE STRUCTURAL GATE - run from an isolated sandbox so the only volatile
    #     field (the cwd) is a temp path we control and normalize.
    sandbox = tempfile.mkdtemp(prefix="emet-witness-")
    try:
        probe = GATE_PROBE.replace("REPO_PLACEHOLDER", repr(REPO))
        body, code = _run([sys.executable, "-c", probe], cwd=sandbox)
        blocks.append(_block(
            "# (1) THE STRUCTURAL GATE  -  Boundary 1 fails inside the TCB",
            "python -c 'import verdict; verdict.governed(verdict.LATTICE, \"TRUSTED\")'",
            body, code, sandbox))
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    # (2) THE INDEPENDENT WITNESS - the RUN of the organs behavior proof.
    body, code = _run([sys.executable, os.path.join(REPO, "test_organs.py")], REPO)
    blocks.append(_block(
        "# (2) THE INDEPENDENT WITNESS  -  the run, not a review",
        "python test_organs.py",
        body, code))

    # (3) ONE WITNESS THRICE - the same vectors against two same-author impls.
    runner = os.path.join("conformance", "run.py")
    for tool in ("membrane.py", os.path.join("impl", "js", "emet.js")):
        body, code = _run([sys.executable, runner, tool], REPO)
        # Keep only the verdict tail (PASS lines are deterministic but long); the
        # essay needs the CONFORMANCE line and exit code.
        tail = "\n".join(l for l in body.splitlines()
                         if l.startswith("CONFORMANCE") or l.startswith("FAIL"))
        blocks.append(_block(
            "# (3) ONE WITNESS THRICE  -  same vectors, " + tool.replace(os.sep, "/"),
            "python conformance/run.py " + tool.replace(os.sep, "/"),
            tail or body, code))

    return "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    out = render()
    if "--check" in sys.argv:
        expected = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if out != expected:
            sys.exit("transcript drift: run `python render.py` to regenerate")
        print("transcript OK")
    else:
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        print("wrote " + OUT)
