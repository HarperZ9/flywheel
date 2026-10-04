"""Hashes cover the bytes Git stores, on every platform and autocrlf setting.

Two parts. The helper tests pin how ``harness.canonical_bytes`` classifies a
pin: MATCH only for the exact bytes, EOL_ONLY (never MATCH) when line endings
are the only difference. The checkout gate hashes every tracked file in this
checkout with ``git hash-object --no-filters`` and requires the result to equal
the blob Git stores, except for paths the repository deliberately checks out
as CRLF (``eol=crlf``). CI runs it on Linux and on Windows with
``core.autocrlf`` both true and false; before ``* text=auto eol=lf`` it failed
on 7537 files in a fresh clone with autocrlf=true.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import canonical_bytes as cb  # noqa: E402

LF = b"line one\nline two\n"
CRLF = LF.replace(b"\n", b"\r\n")


def test_exact_bytes_match_and_name_their_basis():
    r = cb.classify("f.txt", LF, cb.sha256(LF), "unit")
    assert (r.verdict, r.basis, r.matched_form) == (cb.MATCH, "unit", None)


@pytest.mark.parametrize("on_disk,pinned,form", [(CRLF, LF, "lf"), (LF, CRLF, "crlf")])
def test_line_ending_only_difference_is_its_own_verdict(on_disk, pinned, form):
    r = cb.classify("f.txt", on_disk, cb.sha256(pinned), "unit")
    assert r.verdict == cb.EOL_ONLY and r.matched_form == form
    assert "line endings differ" in r.note
    assert cb.EXIT[r.verdict] not in (cb.EXIT[cb.MATCH], cb.EXIT[cb.DRIFT])


def test_a_content_change_is_drift_even_after_normalizing():
    r = cb.classify("f.txt", CRLF + b"x", cb.sha256(LF), "unit")
    assert r.verdict == cb.DRIFT


def test_worst_orders_drift_over_eol_over_match():
    assert cb.worst([cb.MATCH, cb.EOL_ONLY]) == cb.EOL_ONLY
    assert cb.worst([cb.EOL_ONLY, cb.DRIFT, cb.MATCH]) == cb.DRIFT
    assert cb.worst([cb.MATCH]) == cb.MATCH


def _git(*args: str, data: str | None = None) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], input=data, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


def _is_checkout() -> bool:
    try:
        return _git("rev-parse", "--is-inside-work-tree").strip() == "true"
    except (OSError, subprocess.CalledProcessError):
        return False


def test_blob_bytes_reads_what_git_stores():
    if not _is_checkout():
        pytest.skip("not a git checkout")
    oid = _git("rev-parse", "HEAD:pyproject.toml").strip()
    data = cb.blob_bytes(ROOT, "HEAD", "pyproject.toml")
    header = f"blob {len(data)}\0".encode()
    import hashlib
    assert hashlib.sha1(header + data).hexdigest() == oid


def _tracked_blobs() -> dict[str, str]:
    """path -> blob id for every regular tracked file (symlinks and gitlinks skipped)."""
    blobs = {}
    for entry in _git("ls-files", "-s", "-z").split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            mode, oid = meta.split()[:2]
            if mode in ("100644", "100755"):
                blobs[path] = oid
    return blobs


def _crlf_paths(paths) -> set[str]:
    out = _git("check-attr", "-z", "--stdin", "eol",
               data="\0".join(paths) + "\0").split("\0")
    return {out[i] for i in range(0, len(out) - 2, 3) if out[i + 2] == "crlf"}


@pytest.mark.skipif(not _is_checkout(), reason="not a git checkout")
def test_every_checked_out_file_has_the_bytes_git_stores():
    blobs = _tracked_blobs()
    edited = set(_git("diff", "--name-only", "-z", "HEAD").split("\0"))
    crlf = _crlf_paths(blobs)
    paths = [p for p in blobs if p not in edited and p not in crlf and (ROOT / p).is_file()]
    hashed = _git("hash-object", "--no-filters", "--stdin-paths",
                  data="\n".join(paths) + "\n")
    differ = [p for p, oid in zip(paths, hashed.split()) if oid != blobs[p]]
    autocrlf = subprocess.run(["git", "-C", str(ROOT), "config", "core.autocrlf"],
                              capture_output=True, text=True).stdout.strip() or "unset"
    assert len(paths) > 100, "too few files hashed to mean anything"
    assert not differ, (f"{len(differ)} files differ from their blobs with core.autocrlf="
                        f"{autocrlf}, first: {differ[:5]}. See docs/CANONICAL-BYTES.md.")
