"""grounding_corpus_strawmen.py: resolvers that are wrong in one named way each.

A corpus of attacks proves nothing on its own. If a deliberately broken resolver
also scored zero false accepts, the attacks would be scenery. Each resolver here
is the real resolution walk with exactly one discipline removed, and the corpus
asserts that each one gets caught.

The walk below is written out rather than imported from grounding.py, so a bug
in the real walk cannot hide inside its own strawman. The controls are what keep
that copy honest: a strawman that over-rejects a clean store is reported, and a
broken copy would.

Names map to the disciplines in grounding_signatures.py and to the two store
checks that predate it:

  no_intactness   a receipt may hash to something other than its filename
  no_pin          citation digests are ignored and the newest sealing wins
  sidecar_hash    discipline 1: the signed hash is read out of the sidecar
  sidecar_key     discipline 2: the sidecar decides which key is authoritative
  sidecar_only    the signed message is rebuilt from the sidecar's own fields
  optional_sig    a missing sidecar is read as nothing to check rather than a
                  refusal, which is discipline 4 collapsed into a shrug

One attack has no strawman and cannot have one. `absent_ancestor` is refused by
every resolver here because there is no file to load, so it measures the corpus
rather than the resolver. It is kept for that: a builder that quietly wrote
nothing would show up as an attack nobody can fail.
"""
from __future__ import annotations

import json
from pathlib import Path

from .ed25519_verify import verify as _ed_verify, Ed25519Error
from .envelope import ProofEnvelope, load_envelope
from .grounding_signatures import SCHEMA, sidecar_path, signed_bytes

_HASH_GLOB = "-" + "?" * 16 + ".json"

REFUSED = "refused by a weakened resolver"


def _pick(d: Path, sid: str, pin: str) -> Path | None:
    if pin:
        exact = d / ("%s-%s.json" % (sid, pin))
        return exact if exact.is_file() else None
    hits = list(d.glob(sid + _HASH_GLOB))
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def _cited(env: ProofEnvelope) -> list[str]:
    return [str(r.get("source")) for r in (env.retrieved or [])
            if isinstance(r, dict) and r.get("source")]


def _pins_of(env: ProofEnvelope) -> dict[str, str]:
    return {str(r["source"]): str(r["digest"]) for r in (env.retrieved or [])
            if isinstance(r, dict) and r.get("source") and r.get("digest")}


def _sidecar(path: Path) -> dict | None:
    p = sidecar_path(path)
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("schema") == SCHEMA else None


def _signed_ok(env: ProofEnvelope, path: Path, trusted: dict, *,
               hash_from_sidecar: bool, key_from_sidecar: bool,
               task_from_sidecar: bool, optional: bool) -> bool:
    """The signature check with one discipline switched off."""
    doc = _sidecar(path)
    if doc is None:
        return optional
    if doc.get("sig_alg") != "ed25519":
        return False
    from_sidecar = hash_from_sidecar or task_from_sidecar
    digest = (str(doc.get("content_hash", "")) if from_sidecar
              else env.content_hash())
    task = (str(doc.get("task_id", "")) if task_from_sidecar else env.task_id)
    if not from_sidecar and doc.get("content_hash") != digest:
        return False
    try:
        key = (bytes.fromhex(str(doc.get("public_key", ""))) if key_from_sidecar
               else trusted.get(str(doc.get("key_id", ""))))
        sig = bytes.fromhex(str(doc.get("sig", "")))
    except ValueError:
        return False
    if key is None or len(key) != 32 or len(sig) != 64:
        return False
    try:
        return _ed_verify(bytes(key), signed_bytes(task, digest), sig)
    except (Ed25519Error, ValueError):
        return False


def _walk(d, sources, pins, trusted, node, use_pins=True):
    """The resolution walk, shared by every strawman below."""
    d = Path(d)
    pins, forked = (dict(pins or {}) if use_pins else {}), set()
    out: dict[str, ProofEnvelope | None] = {}
    problems: dict[str, str] = {}
    frontier = list(dict.fromkeys(sources))
    while frontier:
        sid = frontier.pop()
        if sid in out:
            continue
        env = None if sid in forked else node(d, sid, pins.get(sid, ""), trusted)
        out[sid] = env
        if env is None:
            problems[sid] = REFUSED
            continue
        if use_pins:
            for dep, pin in _pins_of(env).items():
                if pins.setdefault(dep, pin) != pin:
                    forked.add(dep)
        frontier.extend(s for s in _cited(env) if s not in out)
    for sid, env in out.items():
        if env is not None and (sid in forked or
                                (pins.get(sid) and env.content_hash() != pins[sid])):
            out[sid], problems[sid] = None, REFUSED
    return out, problems


def _node(*, intact=True, hash_from_sidecar=False, key_from_sidecar=False,
          task_from_sidecar=False, optional=False, ignore_signatures=False):
    def node(d: Path, sid: str, pin: str, trusted):
        path = _pick(d, sid, pin)
        if path is None:
            return None
        env = load_envelope(path)
        if intact and env.content_hash() != path.stem.rsplit("-", 1)[-1]:
            return None
        if trusted is None or ignore_signatures:
            return env
        return env if _signed_ok(env, path, trusted,
                                 hash_from_sidecar=hash_from_sidecar,
                                 key_from_sidecar=key_from_sidecar,
                                 task_from_sidecar=task_from_sidecar,
                                 optional=optional) else None
    return node


def _resolver(node, *, use_pins=True):
    def resolve(envelopes_dir, sources, pins=None, trusted_keys=None):
        return _walk(envelopes_dir, sources, pins, trusted_keys, node, use_pins)
    return resolve


#: A receipt is loaded whether or not it hashes to the name it is filed under.
no_intactness = _resolver(_node(intact=False))

#: Citation digests are discarded entirely, so the newest sealing answers.
no_pin = _resolver(_node(), use_pins=False)

#: Discipline 1 removed: the signed hash comes from the sidecar.
sidecar_hash = _resolver(_node(hash_from_sidecar=True))

#: Discipline 2 removed: the sidecar's own public key is verified against.
sidecar_key = _resolver(_node(key_from_sidecar=True))

#: The signed message is rebuilt out of the sidecar, so it verifies itself.
sidecar_only = _resolver(_node(task_from_sidecar=True))

#: Discipline 4 collapsed: a receipt carrying no sidecar is waved through.
optional_sig = _resolver(_node(optional=True))

#: Not one discipline removed but all of them: a resolver that reuses whatever
#: the store happens to hold under a task id. This is the posture
#: accountability_bench.score_strawman models, and it is kept out of STRAWMEN
#: because it fails most of the corpus at once rather than isolating a check.
blind_reuse = _resolver(_node(intact=False, ignore_signatures=True),
                        use_pins=False)

STRAWMEN = {"no_intactness": no_intactness, "no_pin": no_pin,
            "sidecar_hash": sidecar_hash, "sidecar_key": sidecar_key,
            "sidecar_only": sidecar_only, "optional_sig": optional_sig}
