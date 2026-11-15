#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Regenerate the EMET rationale walkthrough transcript, deterministically.

Runs the real EMET commands against input.txt in an isolated temp sandbox and
writes a normalized, re-derivable transcript. Same membrane.py bytes + same
input + same corpus_version -> byte-identical output. `--check` asserts the
committed transcript still matches a fresh render (CI drift-guard).
"""
import os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
MEMBRANE = os.path.join(REPO, "membrane.py")
CORPUS = os.path.join(REPO, "conformance", "markers.corpus")
INPUT = os.path.join(HERE, "input.txt")
OUT = os.path.join(HERE, "transcript.txt")
COMMANDS = [["selftest"], ["anchor", "input.txt"], ["verify", "input.txt"],
            ["refuse", "input.txt"], ["corroborate", "input.txt"], ["audit"]]

def normalize(text, sandbox):
    # Only volatile fields: the sandbox path and corroborate's env-dependent cat
    # channel. Hashes over fixed bytes and the timestamp-free audit chain are
    # already deterministic.
    text = text.replace(sandbox, "<SANDBOX>").replace(sandbox.replace(os.sep, "/"), "<SANDBOX>")
    return re.sub(r"cat_subproc=.*", "cat_subproc=<env-dependent>", text)

def render():
    if shutil.which("git") is None:
        sys.exit("render.py: git is required on PATH for a deterministic transcript")
    sandbox = tempfile.mkdtemp(prefix="emet-walkthrough-")
    try:
        shutil.copy(INPUT, os.path.join(sandbox, "input.txt"))
        env = dict(os.environ, EMET_CORPUS=CORPUS)
        blocks = []
        for cmd in COMMANDS:
            p = subprocess.run([sys.executable, MEMBRANE, *cmd], cwd=sandbox, env=env,
                               capture_output=True, text=True)
            body = normalize(p.stdout.rstrip("\n"), sandbox)
            blocks.append("$ python membrane.py " + " ".join(cmd) + "\n" + body
                          + "\n(exit " + str(p.returncode) + ")")
        return "\n\n".join(blocks) + "\n"
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

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
