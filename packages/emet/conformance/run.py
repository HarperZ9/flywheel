#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
run.py -- EMET conformance runner (language-agnostic).

Executes conformance/vectors.json against ANY implementation and reports PASS or
FAIL per vector. Exit 0 if and only if every vector passes.

A second, INDEPENDENT implementation passing these vectors is what DEMONSTRATES
re-derivability (SPEC.md section 12). The reference implementation passing them
proves internal consistency only.

Usage: python run.py [path-to-tool] [path-to-vectors.json]
  path-to-tool may be a .py script (run via this interpreter) OR any executable
  binary (run directly) -- so a Rust or Go build is tested the same way as Python.
"""
import os, sys, json, tempfile, shutil, subprocess, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(HERE), "membrane.py"))
VECT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "vectors.json")
SUBCMDS = ("anchor", "verify", "coherence", "refuse", "corroborate", "audit",
           "selftest", "receipt", "check", "rebind")
CORPUS = os.path.abspath(os.path.join(HERE, "markers.corpus"))

def invoke(tool):
    if tool.endswith(".py"):
        return [sys.executable, tool]
    if tool.endswith((".js", ".mjs")):
        return ["node", tool]
    return [tool]

def main():
    with open(VECT, encoding="utf-8") as f:
        spec = json.load(f)
    # Fail-closed on a drifted corpus: SPEC s.8 pins re-derivability to
    # spec_version + corpus_version + bytes. A mismatched corpus invalidates
    # every vector, so abort rather than silently run against the wrong data.
    pinned = spec.get("corpus_sha256")
    if pinned:
        with open(CORPUS, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual != pinned:
            sys.exit(
                "ABORT: corpus hash mismatch\n  file:   " + CORPUS
                + "\n  actual: " + actual + "\n  pinned: " + pinned
            )
    vectors = spec["vectors"]
    # An implementation may not yet implement an optional capability (e.g. the
    # portable witness receipt, SPEC s.17). Such an impl declares the capabilities
    # it lacks in EMET_SKIP_CAPABILITIES (comma-separated); vectors tagged with a
    # skipped capability are reported SKIP and excluded from the denominator, so a
    # partial impl is scored honestly against what it DOES claim, never silently
    # credited for what it omits. A vector with no "capability" is always run.
    skip_caps = {c.strip() for c in os.environ.get("EMET_SKIP_CAPABILITIES", "").split(",") if c.strip()}
    npass = 0
    ntotal = 0
    nskip = 0
    for v in vectors:
        cap = v.get("capability")
        if cap is not None and cap in skip_caps:
            print("SKIP " + v["id"] + " capability=" + cap)
            nskip += 1
            continue
        ntotal += 1
        tmp = tempfile.mkdtemp(prefix="emet_conf_")
        try:
            for name, content in v.get("files", {}).items():
                with open(os.path.join(tmp, name), "w", encoding="utf-8", newline="") as fh:
                    fh.write(content)
            env = dict(os.environ); env["EMET_CORPUS"] = CORPUS; env.update(v.get("env", {}))
            for name in v.get("anchor", []):
                subprocess.run(invoke(TOOL) + ["anchor", os.path.join(tmp, name)], cwd=tmp, capture_output=True, env=env)
            for name, extra in v.get("append", {}).items():
                with open(os.path.join(tmp, name), "a", encoding="utf-8", newline="") as fh:
                    fh.write(extra)
            # `run` entries are tmp-joined into file paths unless they are a
            # subcommand or a flag; a vector may also list entries under `literal`
            # (verbatim tokens, e.g. a rebind --claim identity or a
            # <path>=<identity> manifest pair) that must NOT be treated as paths.
            literal = set(v.get("literal", []))
            args = [a if (a in SUBCMDS or a.startswith("-") or a in literal)
                    else os.path.join(tmp, a) for a in v["run"]]
            p = subprocess.run(invoke(TOOL) + args, cwd=tmp, capture_output=True, text=True, env=env)
            ok = (v["expect_substr"] in p.stdout) and (p.returncode == v["expect_exit"])
            print(("PASS " if ok else "FAIL ") + v["id"] + " exit=" + str(p.returncode) + " want=" + str(v["expect_exit"]))
            if not ok:
                print("     stdout: " + p.stdout.strip().replace(chr(10), " / ")[:180])
            if ok:
                npass += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    tail = (" (" + str(nskip) + " skipped by capability)") if nskip else ""
    print("CONFORMANCE " + str(npass) + "/" + str(ntotal) + " vectors pass" + tail)
    sys.exit(0 if npass == ntotal else 1)

if __name__ == "__main__":
    main()
