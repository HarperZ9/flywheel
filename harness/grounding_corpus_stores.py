"""grounding_corpus_stores.py: the stores each attack in the corpus resolves over.

Every builder writes real receipts to a real directory and returns what a caller
would hand `resolve_ancestors`: the sources it cites, the pins those citations
carry, the trusted keys if any, and which node is under test.

No oracle runs here. The layer under test is resolution, not re-execution, so a
receipt is constructed and filed directly. That keeps the whole corpus fast
enough to sit inside a benchmark dimension.

A signer is a duck: `.sign(bytes) -> 64 bytes`, `.public_key_bytes`, `.key_id`.
Builders that need one are marked, and the runner reports them as skipped by
name when none is available rather than quietly shortening the corpus.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .grounding_signatures import (sidecar_document, sidecar_path,
                                   signed_bytes)
from .task import cite

OPERATOR_KEY = "operator-1"

#: What a trusted mapping holds when the attack never needs a real signature.
#: Thirty-two bytes that verify nothing, which is the point in those cases.
UNUSED_KEY = bytes(32)


def _env(task_id: str, candidate: str = "def add(a, b): return a + b",
         cites: list | None = None) -> ProofEnvelope:
    return ProofEnvelope(
        task_id=task_id, candidate=candidate, oracle="pytest",
        oracle_cmd="pytest tests/", oracle_output_hash="93e4b6c6b7a05c82",
        verdict="PASS", model_ref="stub", seed=0, prompt_hash="p",
        budget_spent={}, retrieved=[asdict(c) for c in (cites or [])])


def _file(d: Path, env: ProofEnvelope) -> Path:
    """File a receipt where the store expects it: under its own content hash."""
    return env.write(d / ("%s-%s.json" % (env.task_id, env.content_hash())))


def _rewrite(path: Path, candidate: str) -> Path:
    """Edit a stored receipt in place. The filename is left alone."""
    d = json.loads(path.read_text(encoding="utf-8"))
    d["candidate"] = candidate
    path.write_text(json.dumps(d), encoding="utf-8")
    return path


def _refile(path: Path) -> Path:
    """Rename an edited receipt to the hash it now has, which is the move the
    filename check alone cannot see."""
    new = path.with_name("%s-%s.json" % (path.name.rsplit("-", 1)[0],
                                         load_envelope(path).content_hash()))
    path.rename(new)
    return new


def _sign(path: Path, signer, key_id: str = "") -> Path:
    """Write a sidecar covering the receipt at `path`, as its signer would."""
    env = load_envelope(path)
    digest = env.content_hash()
    doc = sidecar_document(
        task_id=env.task_id, content_hash=digest,
        signature=signer.sign(signed_bytes(env.task_id, digest)),
        public_key=signer.public_key_bytes, key_id=key_id or signer.key_id)
    out = sidecar_path(path)
    out.write_text(json.dumps(doc), encoding="utf-8")
    return out


def _case(target: str, sources: list[str] | None = None, pins: dict | None = None,
          trusted: dict | None = None) -> dict:
    return {"target": target, "sources": sources or [target],
            "pins": pins or {}, "trusted": trusted}


# --- false-accept stores -----------------------------------------------------

def edited_in_place(d: Path, signer) -> dict:
    """The receipt says something else and is still filed under the old hash."""
    a = _file(d, _env("A"))
    _rewrite(a, "def add(a, b): return a * b")
    return _case("A")


def refiled_rewrite(d: Path, signer) -> dict:
    """Rewritten and refiled, so the store is self-consistent. The citer read
    the receipt that used to be there and pinned it."""
    a = _file(d, _env("A"))
    pin = a.stem.rsplit("-", 1)[-1]
    _refile(_rewrite(a, "def add(a, b): return a * b"))
    return _case("A", pins={"A": pin})


def whole_cone_rewrite(d: Path, signer) -> dict:
    """Needs a signer. The editor rewrites, refiles, repoints the pin at the new
    hash, and carries the original sidecar across so a signature is present.
    Every hash agrees with every other hash. Only the signature disagrees."""
    a = _file(d, _env("A"))
    sig = _sign(a, signer)
    moved = _refile(_rewrite(a, "def add(a, b): return a * b"))
    sig.rename(sidecar_path(moved))
    return _case("A", pins={"A": moved.stem.rsplit("-", 1)[-1]},
                 trusted={signer.key_id: signer.public_key_bytes})


def absent_ancestor(d: Path, signer) -> dict:
    """Cited and never stored. Nothing to substitute, and nothing is."""
    return _case("A")


def pin_fork(d: Path, signer) -> dict:
    """Two citers reached the same source and read different sealings of it.
    No single receipt satisfies the cone, so the source resolves to nothing."""
    first = _env("A")
    second = _env("A", candidate="def add(a, b): return b + a")
    _file(d, first)
    _file(d, second)
    _file(d, _env("B", cites=[cite(first)]))
    _file(d, _env("C", cites=[cite(second)]))
    return _case("A", sources=["B", "C"])


def unsigned_ancestor(d: Path, signer) -> dict:
    """Signatures are required and this receipt carries none. Fails closed
    rather than passing, which is what an incomplete rollout looks like."""
    _file(d, _env("A"))
    return _case("A", trusted={OPERATOR_KEY: UNUSED_KEY})


def sidecar_names_the_trusted_key(d: Path, signer) -> dict:
    """Needs a signer. The forgery is invisible from inside the file: a real
    signature, a real public key, and a key_id the trusted set knows. What the
    sidecar cannot do is decide which key is authoritative."""
    a = _file(d, _env("A"))
    _sign(a, signer, key_id=OPERATOR_KEY)
    return _case("A", pins={"A": a.stem.rsplit("-", 1)[-1]},
                 trusted={OPERATOR_KEY: UNUSED_KEY})


def lifted_signature(d: Path, signer) -> dict:
    """Needs a signer. A valid signature over a different receipt, copied to sit
    beside this one."""
    other = _file(d, _env("B"))
    donor = _sign(other, signer)
    a = _file(d, _env("A"))
    sidecar_path(a).write_text(donor.read_text(encoding="utf-8"),
                               encoding="utf-8")
    return _case("A", trusted={signer.key_id: signer.public_key_bytes})


# --- controls: a sound resolver must return these ----------------------------

def clean_unsigned(d: Path, signer) -> dict:
    """An untouched store with no signatures anywhere, which is what every
    receipt sealed before signatures existed lives in."""
    _file(d, _env("A"))
    return _case("A")


def clean_pinned_chain(d: Path, signer) -> dict:
    """A citer that pinned what it read, over a store that still holds it."""
    a = _env("A")
    _file(d, a)
    _file(d, _env("B", cites=[cite(a)]))
    return _case("A", sources=["B"])


def clean_signed(d: Path, signer) -> dict:
    """Needs a signer. Signatures required, present, and valid."""
    a = _file(d, _env("A"))
    _sign(a, signer)
    return _case("A", pins={"A": a.stem.rsplit("-", 1)[-1]},
                 trusted={signer.key_id: signer.public_key_bytes})
