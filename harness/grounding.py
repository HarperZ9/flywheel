"""grounding.py — the transitive-witness closure ON the loop's critical path.

Until now every receipt was an island: run_loop witnessed its OWN envelope and
accepted, even when the task's `retrieved[]` cited prior envelopes that had
since been tampered or gone stale. transitive_witness holds the pure closure
algorithm; this module is the bridge that puts it in the accept path: resolve
the cited grounding from the envelope store (transitively), re-witness each
ancestor in its own oracle environment, fold the closure, and hand the loop a
single transitive verdict to gate acceptance on.

FAIL-CLOSED contract (both directions of honesty):
  - An ancestor that cannot be located, or whose oracle environment cannot be
    rebuilt, is UNVERIFIABLE — never assumed MATCH. No re-run, no trust.
  - We never re-run an ancestor's oracle in the WRONG environment just to have
    run something: that manufactures a false DRIFT (the turbulence lesson —
    checking the wrong invariant is a false alarm, not rigor). Nothing to run
    in -> UNVERIFIABLE with the reason recorded, not a fake re-check.
  - A stored receipt that no longer hashes to its own filename is dropped
    before anything runs. Reading the oracle environment out of a receipt is
    what makes that check load-bearing rather than tidy; _load_intact carries
    the measurement and the limit.

When the caller supplies no workdir for an ancestor, we try once more in a
fresh directory rebuilt from the envelope alone (its candidate, plus whatever
bounded fixture set it captured — see oracle_inputs.py), and we read the
outcome ASYMMETRICALLY. Reproducing the stored canonical hash with nothing but the
receipt is positive proof that the environment was sufficient, so MATCH is
earned. Failing to reproduce it proves nothing at all, because a missing
fixture and real drift look identical from here, so that outcome is
UNVERIFIABLE and is never reported as DRIFT. The asymmetry is the whole point:
it lets the common self-contained ancestor verify itself without weakening the
contract above by a single case.


The closure semantics come from transitive_witness: a drifted ancestor turns
its dependents UNVERIFIABLE (gap, not glut) while independent nodes keep their
own verdict (localized degradation).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .oracle_inputs import restore as restore_inputs, safe_relative as _safe_relative
from .transitive_witness import DepNode, transitive_verdicts, MATCH, UNVERIFIABLE
from .witness import witness_envelope

# envelope filenames are f"{task_id}-{content_hash}.json", hash = 16 hex chars
_HASH_GLOB = "-" + "?" * 16 + ".json"

_NO_ENV = ("no oracle environment supplied for re-run — "
           "fail closed, not re-run in a wrong workdir")

_NO_FILE = "cited grounding has no stored envelope"
_NOT_INTACT = ("stored receipt does not hash to the name it is filed under, "
               "so it was edited after sealing")


def _load_intact(path: Path) -> ProofEnvelope | None:
    """Load a stored receipt only if it still hashes to its own filename.

    Receipts are written as f"{task_id}-{content_hash()}.json", so editing any
    digest-covered field in place moves the hash off the name. The check is two
    lines and it is load-bearing: since the fresh-environment re-run rebuilds
    its oracle environment from `oracle_inputs`, an editor who rewrites the
    fixture set AND the candidate together hands that re-run a test file with
    the same test ids and weaker assertions. The canonical hash then reproduces
    against a tampered candidate and buys a MATCH. Measured, not assumed: with
    this check removed, that swap returns MATCH on tasks/example_pass.

    What it does not stop is an editor who also renames the file to the new
    hash. Closing that needs the citation to name the ancestor digest it meant,
    which `retrieved[]` does not carry today, or signature verification on this
    path. Both are recorded in PROJECT.md as open.
    """
    env = load_envelope(path)
    return env if env.content_hash() == path.stem.rsplit("-", 1)[-1] else None


def _cited_sources(env: ProofEnvelope) -> list[str]:
    return [str(r.get("source")) for r in (env.retrieved or [])
            if isinstance(r, dict) and r.get("source")]


def _stored_envelope(envelopes_dir: Path, source_id: str) -> Path | None:
    hits = list(envelopes_dir.glob(source_id + _HASH_GLOB))
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)   # newest sealing wins


def resolve_ancestors(
        envelopes_dir: str | Path, sources: list[str],
) -> tuple[dict[str, ProofEnvelope | None], dict[str, str]]:
    """Transitively load the cited grounding from the envelope store.

    Returns the envelopes and, alongside them, why each unusable source is
    unusable: absent from the store, or present but no longer matching its own
    content hash. Both map to None and fail closed downstream, and they are
    reported apart because they call for different responses. A receipt that
    fails the integrity check is dropped whole, so its own `retrieved[]` never
    steers this walk.
    """
    envelopes_dir = Path(envelopes_dir)
    out: dict[str, ProofEnvelope | None] = {}
    problems: dict[str, str] = {}
    frontier = list(dict.fromkeys(sources))
    while frontier:
        sid = frontier.pop()
        if sid in out:
            continue
        path = _stored_envelope(envelopes_dir, sid)
        env = _load_intact(path) if path else None
        out[sid] = env
        if env is not None:
            frontier.extend(s for s in _cited_sources(env) if s not in out)
        else:
            problems[sid] = _NO_FILE if path is None else _NOT_INTACT
    return out, problems


def _rewitness_in_fresh_env(env: ProofEnvelope) -> tuple[str, str]:
    """Re-run an ancestor in an empty directory built from its receipt alone.

    Only reproduction is believed. See the asymmetry in the module docstring:
    MATCH is evidence the environment sufficed, a mismatch is not evidence of
    drift, so a mismatch degrades to UNVERIFIABLE and keeps its reason.

    Strength depends on the oracle. For `pytest` the canonical hash folds every
    test id and outcome from the run, so reproducing it in a bare directory is
    a strong statement. For an oracle whose canonical form is empty the hash
    covers the return code only, and a fresh-environment MATCH there is worth
    no more than "it exited the same way".
    """
    rel = _safe_relative(env.candidate_path)
    if rel is None:
        return UNVERIFIABLE, (_NO_ENV + "; the envelope records no usable "
                              "candidate path to rebuild one from")
    with tempfile.TemporaryDirectory(prefix="fw-grounding-") as td:
        restore_inputs(env.oracle_inputs, td)
        v = witness_envelope(env, workdir=td, candidate_path=rel)
    if v.verdict == MATCH:
        return MATCH, ("no workdir supplied; reproduced the canonical hash in a "
                       "fresh environment built from the envelope alone")
    return UNVERIFIABLE, (
        f"{_NO_ENV}; a fresh-environment re-run did not reproduce ({v.reason}), "
        "which does not separate drift from a missing fixture")


def recheck_grounding(current: ProofEnvelope, local_verdict: str, *,
                      envelopes_dir: str | Path,
                      workdirs: dict[str, tuple[str, str]],
                      fresh_env_retry: bool = True) -> dict:
    """Re-witness the cited ancestors and fold the closure over the citation DAG.

    `workdirs` maps ancestor task_id -> (workdir, candidate_path): the oracle
    environment each ancestor re-runs in. A missing entry falls back to a fresh
    environment rebuilt from that ancestor's own receipt, which can only earn
    MATCH by reproducing the stored hash and otherwise stays UNVERIFIABLE (fail
    closed, reason recorded — see module docstring). Pass
    `fresh_env_retry=False` to skip the fallback and go straight to
    UNVERIFIABLE, which is the behaviour callers had before 2026-09-06.

    Returns {"verdict": <transitive verdict for `current`>,
             "verdicts": {node_id: verdict, ...}, "reasons": {ancestor_id: why}}.
    """
    sources = _cited_sources(current)
    ancestors, problems = resolve_ancestors(envelopes_dir, sources)
    nodes: list[DepNode] = []
    reasons: dict[str, str] = {}
    for sid, env in ancestors.items():
        if env is None:
            nodes.append(DepNode(id=sid, local=UNVERIFIABLE, has_receipt=False))
            reasons[sid] = problems[sid]
            continue
        wd = workdirs.get(sid)
        if wd is not None:
            v = witness_envelope(env, workdir=wd[0], candidate_path=wd[1])
            local, reasons[sid] = v.verdict, v.reason
        elif fresh_env_retry:
            local, reasons[sid] = _rewitness_in_fresh_env(env)
        else:
            local, reasons[sid] = UNVERIFIABLE, _NO_ENV
        nodes.append(DepNode(id=sid, local=local, deps=_cited_sources(env),
                             has_receipt=bool(env.oracle_output_hash)))
    nodes.append(DepNode(id=current.task_id, local=local_verdict, deps=sources,
                         has_receipt=bool(current.oracle_output_hash)))
    verdicts = transitive_verdicts(nodes)
    return {"verdict": verdicts[current.task_id],
            "verdicts": verdicts, "reasons": reasons}
