"""Hash the bytes Git stores, and say so when line endings are all that differ.

A pinned sha256 over a text file names one exact byte string. Git for Windows
defaults to ``core.autocrlf=true`` and rewrites LF files to CRLF on checkout,
so the same commit gives different bytes on different machines, and a stranger
who hashes the checkout gets a false DRIFT. This module is the one place that
answers three questions for every verifier that pins a text file:

* What are the canonical bytes? The blob Git stores at a revision, read with
  ``git cat-file blob``, which no checkout setting can change.
* Did a mismatch come from line endings alone? ``classify`` hashes the LF form
  and the CRLF form as well, and reports ``EOL_ONLY`` with the form that
  matched. It never reports MATCH for a converted form: an EOL-only result is
  its own verdict, so no existing check gets weaker.
* Which normalization was used? Every result carries the ``basis`` it hashed.

Standard library only, so it stays inside the verifier closure.

    python -m harness.canonical_bytes check PATH SHA256 [--rev REV] [--repo DIR]

Exit codes: 0 MATCH, 1 DRIFT, 3 EOL_ONLY (bytes differ only in line endings).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from . import safe_program

MATCH, DRIFT, EOL_ONLY = "MATCH", "DRIFT", "EOL_ONLY"
EXIT = {MATCH: 0, DRIFT: 1, EOL_ONLY: 3}


@dataclass(frozen=True)
class PinResult:
    path: str
    expected: str
    actual: str
    verdict: str
    basis: str
    matched_form: str | None = None
    note: str = ""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def eol_forms(data: bytes) -> dict[str, str]:
    """sha256 of the raw bytes, of the LF form and of the CRLF form."""
    lf = data.replace(b"\r\n", b"\n")
    return {"raw": sha256(data), "lf": sha256(lf),
            "crlf": sha256(lf.replace(b"\n", b"\r\n"))}


def classify(path: str, data: bytes, expected: str, basis: str) -> PinResult:
    """Compare ``data`` with a pinned digest; never accept a converted form."""
    expected = expected.lower()
    forms = eol_forms(data)
    if forms["raw"] == expected:
        return PinResult(path, expected, forms["raw"], MATCH, basis)
    for form in ("lf", "crlf"):
        if forms[form] == expected:
            if form == "lf":
                note = ("line endings differ: the pin is the LF form of these bytes. "
                        "Hash the stored blob (--rev) or check out with core.autocrlf=false.")
            else:
                note = ("line endings differ: the pin is the CRLF form of these bytes, "
                        "computed on a CRLF checkout. Content matches; see docs/CANONICAL-BYTES.md.")
            return PinResult(path, expected, forms["raw"], EOL_ONLY, basis, form, note)
    return PinResult(path, expected, forms["raw"], DRIFT, basis)


def git(*args: str, cwd=None, text: bool = True, input=None) -> subprocess.CompletedProcess:
    """Run git through the guarded program lookup (never the working folder)."""
    cmd, env = safe_program.launch(["git", *args], cwd=cwd)
    return subprocess.run(cmd, env=env, cwd=cwd, input=input, capture_output=True,
                          text=text, check=False)


def blob_bytes(repo: Path, rev: str, path: str) -> bytes:
    """The bytes Git stores for ``path`` at ``rev``. No filters, no autocrlf."""
    proc = git("-C", str(repo), "cat-file", "blob", f"{rev}:{path}", text=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise FileNotFoundError(f"{rev}:{path} not readable from {repo}: {detail}")
    return proc.stdout


def check_pin(repo: Path, path: str, expected: str, rev: str | None = None) -> PinResult:
    """Check one pin, against the blob at ``rev`` or the file on disk."""
    if rev:
        return classify(path, blob_bytes(repo, rev, path), expected, f"git blob at {rev}")
    data = (Path(repo) / path).read_bytes()
    return classify(path, data, expected, "file bytes on disk, no normalization")


def render(result: PinResult) -> str:
    line = f"{result.verdict:8} {result.path}  basis: {result.basis}"
    if result.verdict != MATCH:
        line += f"\n         expected {result.expected}\n         actual   {result.actual}"
    if result.note:
        line += f"\n         {result.note}"
    return line


def worst(verdicts: list[str]) -> str:
    """DRIFT outranks EOL_ONLY, which outranks MATCH."""
    for v in (DRIFT, EOL_ONLY):
        if v in verdicts:
            return v
    return MATCH


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness.canonical_bytes",
                                 description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check one file against a pinned sha256")
    c.add_argument("path")
    c.add_argument("sha256")
    c.add_argument("--rev", help="hash the blob Git stores at this revision")
    c.add_argument("--repo", default=".", help="repository root (default: .)")
    c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    result = check_pin(Path(a.repo), a.path, a.sha256, a.rev)
    print(json.dumps(asdict(result), sort_keys=True) if a.json else render(result))
    return EXIT[result.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
