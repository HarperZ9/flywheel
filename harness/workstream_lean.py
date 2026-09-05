"""workstream_lean.py -- the lean checker, and what its environment string binds.

An obligation's environment is folded into the workstream identity, so the words
in it travel with every receipt above it. `lean4:v4.9.0+mathlib:2026-08-01` makes
two claims, and until now only the first one was ever confirmed. The Lean version
was compared against the toolchain that answered; the library revision beside it
was carried into the identity and silently believed.

That gap is the interesting one, because a formalization stack is not decided by
the Lean version. It is decided by the library it was written against. Two proofs
of the same statement under different Mathlib revisions are different results,
and a receipt that prints one revision while the kernel read another is a receipt
that says the wrong thing confidently.

So both halves bind here, by the same rule:

  the environment names it, the run confirms it        the note says so
  the environment names it, nothing reports it         unverifiable
  the environment names it, the run reports another    unverifiable
  the environment names neither                        nothing pins the result

A mismatch is never a refutation. The statement may well be true; what failed is
the claim that it was decided in the environment the obligation names, and
blaming the statement for that would teach a reader the wrong lesson.

Revisions come from a lake manifest, because the Lean receipt has no room for
them: `lean_check` reports `toolchain`, `axiom_footprint`, and `kernel_output`
and nothing about what was on the library path. Set FLYWHEEL_LEAN_MANIFEST to a
lake-manifest.json, or run where one sits in the working directory. With no
manifest anywhere, a library-pinned obligation settles unverifiable and the note
names the library that went unbound, which is the honest reading of a bare `lean`
invocation with no project around it.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from harness.workstream import Obligation

_LEAN_PIN = re.compile(r"lean4?[:/]v?(\d+(?:\.\d+)*)")
_LEAN_RUNNING = re.compile(r"version (\d+(?:\.\d+)*)")
_LIBRARY_PIN = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*):(\S+)$")
_NOT_A_LIBRARY = frozenset(("lean", "lean4"))
_MANIFEST = "lake-manifest.json"
_MAX_MANIFEST = 4_000_000
_SHORT_SHA = 7


def manifest_path() -> Path | None:
    """Where a lake manifest would be found, or None if there is none.

    FLYWHEEL_LEAN_MANIFEST names a file directly. Otherwise a manifest is only
    picked up from the working directory, and never from the declaration: a path
    read out of a document a stranger wrote is a file-read surface wearing the
    word environment.
    """
    named = os.environ.get("FLYWHEEL_LEAN_MANIFEST", "").strip()
    if named:
        candidate = Path(named)
        return candidate if candidate.is_file() else None
    candidate = Path.cwd() / _MANIFEST
    return candidate if candidate.is_file() else None


def manifest_revisions(path: Path | None = None) -> dict[str, tuple[str, ...]] | None:
    """Every library on the path and the revisions it answers to.

    Returns None when no manifest was found, which is different from an empty
    one: nothing to read against is unverifiable, and a manifest that lists no
    packages refutes a pin. A malformed manifest reads as no manifest, because a
    file we cannot parse tells us nothing about what was on the path.
    """
    source = manifest_path() if path is None else path
    if source is None or not source.is_file():
        return None
    try:
        if source.stat().st_size > _MAX_MANIFEST:
            return None
        body = json.loads(source.read_text(encoding="utf-8"))
        packages = body["packages"]
        if not isinstance(packages, list):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    found: dict[str, tuple[str, ...]] = {}
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        answers = tuple(str(entry[field]) for field in ("rev", "inputRev")
                        if isinstance(entry.get(field), str) and entry[field])
        found[name.lower()] = answers
    return found


def _pinned_libraries(environment: str) -> list[tuple[str, str]]:
    """The library revisions a composed environment pins, if it composes at all.

    Only a `+`-joined environment declares parts. A single segment is a label
    and not a pin, which is what keeps `prove2me:mission-7`, `cfr:2026-title21`
    and `mhs:plate-reader-3/driver-2.1.0` from being read as libraries nobody
    can find a manifest for. Reading every colon in every environment as a
    revision claim would make most of this repository's environments
    unverifiable for saying nothing about Lean at all.
    """
    segments = [part.strip() for part in (environment or "").split("+")]
    if len(segments) < 2:
        return []
    found: list[tuple[str, str]] = []
    for segment in segments:
        pinned = _LIBRARY_PIN.match(segment)
        if pinned and pinned.group(1).lower() not in _NOT_A_LIBRARY:
            found.append((pinned.group(1), pinned.group(2)))
    return found


def _one_library(name: str, revision: str,
                 revisions: dict[str, tuple[str, ...]] | None) -> tuple[bool, str]:
    """Whether one pinned library is the one that was on the path."""
    if revisions is None:
        return False, (f"the environment pins {name} {revision} and no lake manifest "
                       "was discoverable, so nothing here binds it")
    answers = revisions.get(name.lower())
    if answers is None:
        return False, (f"the environment pins {name} {revision} and the manifest "
                       "lists no such library")
    if revision in answers:
        return True, f"{name} {revision}"
    if len(revision) >= _SHORT_SHA and any(rev.startswith(revision) for rev in answers):
        return True, f"{name} {revision}"
    on_path = ", ".join(answers) or "nothing"
    return False, (f"the environment pins {name} {revision} and the manifest "
                   f"has {on_path}")


def _lean_version(environment: str, toolchain: str) -> tuple[bool, str]:
    """Whether the toolchain that answered is the one the obligation pinned."""
    pinned = _LEAN_PIN.search(environment or "")
    if pinned is None:
        return True, "the environment names no lean version, so nothing pins this result"
    running = _LEAN_RUNNING.search(toolchain or "")
    if running is None:
        return False, (f"the environment pins lean {pinned.group(1)} and the toolchain "
                       "that answered did not report a version")
    if running.group(1) != pinned.group(1):
        return False, (f"the environment pins lean {pinned.group(1)} and the check ran "
                       f"on {running.group(1)}")
    return True, f"lean {running.group(1)}, matching the pinned environment"


def _lean_environment(environment: str, toolchain: str,
                      revisions: dict[str, tuple[str, ...]] | None = None
                      ) -> tuple[bool, str]:
    """Whether the whole environment string is the one the check ran in.

    The version and every library revision bind by the same rule, and the note
    carries both halves so a passing row can be told from a row that passed
    because nothing was pinned.
    """
    matched, note = _lean_version(environment, toolchain)
    if not matched:
        return False, note
    libraries = _pinned_libraries(environment)
    if not libraries:
        return True, note
    confirmed: list[str] = []
    for name, revision in libraries:
        bound, said = _one_library(name, revision, revisions)
        if not bound:
            return False, said
        confirmed.append(said)
    return True, f"{note}, with {', '.join(confirmed)}"


def lean_checker(obligation: Obligation) -> tuple[str, str]:
    """Ask the Lean kernel. A missing toolchain is declared, never a pass."""
    from harness.lean_oracle import lean_check

    receipt = lean_check(obligation.statement)
    passed = receipt.get("passed")
    output = str(receipt.get("kernel_output", ""))[:400]
    toolchain = str(receipt.get("toolchain", ""))
    if passed is None:
        return "UNVERIFIABLE", output or "no lean toolchain installed"
    if passed is False and not toolchain:
        # An admitted hole is refused before the kernel runs, so there is no
        # toolchain to compare and nothing about the environment to settle.
        return "FAIL", output or "the kernel refused the statement"
    matched, note = _lean_environment(
        obligation.environment, toolchain, manifest_revisions())
    if not matched:
        return "UNVERIFIABLE", note
    return ("PASS", note) if passed is True else ("FAIL", output or note)
