"""oracle_inputs.py — the fixture set a receipt carries so it can re-run alone.

A receipt holding only the candidate can be re-checked only when the candidate
carries its own tests. Every task in this repo runs pytest against a fixture
directory the candidate does not contain, so the fresh-environment fallback in
grounding.py reached none of them before this module existed. Carrying the
fixtures is what gives that fallback reach on real work.

Capture is bounded on purpose. These entries travel inside a receipt that may
be published, and an unbounded snapshot of a working directory is a disclosure
surface rather than a feature. Text only, per-file and total caps, build and
cache directories skipped. Anything that does not fit is dropped whole, never
truncated: a truncated fixture produces a run that fails for a reason nobody
can read, and under the asymmetry in grounding.py a dropped fixture costs a
confirmation and can never grant one.

Bounds keep the snapshot small without keeping it safe. A `.env` in a working
directory is comfortably under every cap and would sail into a publishable
receipt, so credential files are withheld by a separate rule in
receipt_secrets.py, applied on both ends of the boundary, and what got withheld
is handed back to the caller rather than disappearing.

Restore applies the SAME exclusions as capture, because capture runs on our
side and restore runs on receipt data we did not write. The one that must not
be skipped is the junit file: canonical_hash reads its outcomes back, so a
receipt permitted to carry _oracle_junit.xml would be carrying its own answer
key into the directory where it is about to be graded.

Trust boundary, stated plainly. Restoring these files makes a re-check execute
more third-party content than the candidate alone, since a conftest.py runs at
collection time. That widens an exposure that already exists rather than
opening a new one: re-witnessing already writes envelope.candidate and runs
envelope.oracle_cmd under a shell, both read from the same untrusted receipt.
Re-running someone else's receipt runs someone else's code, and all this
changes is how much of it there is.
"""
from __future__ import annotations

from pathlib import Path

from .receipt_secrets import withhold_reason

MAX_FILES = 64
MAX_FILE_BYTES = 32 * 1024
MAX_TOTAL_BYTES = 128 * 1024

# Produced by a build rather than supplied by a task. __pycache__ matters most:
# it would embed a stale compile of the very module the re-run replaces.
SKIP_DIRS = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git",
    ".hypothesis", ".tox", ".venv", "venv", "node_modules", "htmlcov",
})
# Written by the oracle itself. _oracle_junit.xml is the answer key.
SKIP_NAMES = frozenset({"_oracle_junit.xml", ".coverage"})


def safe_relative(name: str) -> str | None:
    """A workdir-relative path from an untrusted receipt, or None if unusable.

    Anything that could land outside the destination is REFUSED rather than
    sanitised. A rewritten path that still writes somewhere is worse than one
    that does not run at all: refusing costs a confirmation, sanitising invents
    an environment nobody sealed.
    """
    if not name or "\\" in name or ":" in name or name.startswith("/"):
        return None
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def _excluded(rel: str) -> bool:
    parts = rel.split("/")
    return bool(SKIP_DIRS.intersection(parts)) or parts[-1] in SKIP_NAMES


def capture(workdir: str | Path, *, exclude: tuple = ()) -> tuple[dict, list]:
    """Snapshot the text files an oracle will read, bounded, for the receipt.

    Returns the fixture set and, beside it, the entries withheld for looking
    like credentials: `[{"path", "reason"}]`, no matched text. They are handed
    back rather than dropped quietly because a withheld fixture is why an
    otherwise sound task later reads UNVERIFIABLE, and that is not something a
    reader can work out from the receipt alone.

    Call BEFORE the oracle runs, so the candidate and the run's own artefacts
    are not in the picture. `exclude` names paths to leave out regardless, and
    the caller passes the candidate path there: the candidate already travels
    in the envelope and a second stale copy could contradict it.
    """
    root = Path(workdir)
    if not root.is_dir():
        return {}, []
    skipped = {safe_relative(str(e)) for e in exclude}
    out: dict[str, str] = {}
    withheld: list[dict] = []
    total = 0
    for p in sorted(root.rglob("*")):
        if len(out) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            break
        rel = p.relative_to(root).as_posix()
        if rel in skipped or _excluded(rel) or not p.is_file():
            continue
        reason = withhold_reason(rel)
        if reason:      # settled by the name, so the file is never even read
            withheld.append({"path": rel, "reason": reason})
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue        # binary or unreadable: not our business to carry
        reason = withhold_reason(rel, text)
        if reason:
            withheld.append({"path": rel, "reason": reason})
            continue
        size = len(text.encode("utf-8"))
        if total + size > MAX_TOTAL_BYTES:
            continue
        out[rel] = text
        total += size
    return out, withheld


def restore(inputs: dict, dest: str | Path) -> int:
    """Write a receipt's captured inputs into `dest`. Returns files written.

    Every bound capture enforces is re-enforced here, on the argument that this
    input arrived in a file someone else wrote. An entry that fails any of them
    is dropped, which can only make the re-run fail closed.
    """
    root = Path(dest)
    written = 0
    total = 0
    for name in sorted(inputs or {}):
        if written >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            break
        text = inputs[name]
        rel = safe_relative(str(name))
        if rel is None or _excluded(rel) or not isinstance(text, str):
            continue
        if withhold_reason(rel, text):
            # Capture will not put a credential in a receipt, and this end will
            # not take one out of somebody else's. Writing it would spill a
            # leaked key onto our disk on the strength of a file we did not
            # write, to gain a fixture the sealer was never supposed to carry.
            continue
        size = len(text.encode("utf-8"))
        if size > MAX_FILE_BYTES or total + size > MAX_TOTAL_BYTES:
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written += 1
        total += size
    return written
