"""grounding.py — the transitive-witness closure ON the loop's critical path.

Until now every receipt was an island: run_loop witnessed its OWN envelope and
accepted, even when the task's `retrieved[]` cited prior envelopes that had
since been tampered or gone stale. transitive_witness holds the pure closure
algorithm; this module is the bridge that puts it in the accept path: resolve
the cited grounding from the envelope store (transitively), re-witness each
ancestor in its own oracle environment, fold the closure, and hand the loop a
single transitive verdict to gate acceptance on.

FAIL-CLOSED contract (both directions of honesty):
  - An ancestor that cannot be located, or whose oracle environment the caller
    cannot supply, is UNVERIFIABLE — never assumed MATCH. No re-run, no trust.
  - We never re-run an ancestor's oracle in the WRONG environment just to have
    run something: that manufactures a false DRIFT (the turbulence lesson —
    checking the wrong invariant is a false alarm, not rigor). No workdir ->
    UNVERIFIABLE with the reason recorded, not a fake re-check.

The closure semantics come from transitive_witness: a drifted ancestor turns
its dependents UNVERIFIABLE (gap, not glut) while independent nodes keep their
own verdict (localized degradation).
"""
from __future__ import annotations

from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .transitive_witness import DepNode, transitive_verdicts, UNVERIFIABLE
from .witness import witness_envelope

# envelope filenames are f"{task_id}-{content_hash}.json", hash = 16 hex chars
_HASH_GLOB = "-" + "?" * 16 + ".json"


def _cited_sources(env: ProofEnvelope) -> list[str]:
    return [str(r.get("source")) for r in (env.retrieved or [])
            if isinstance(r, dict) and r.get("source")]


def _stored_envelope(envelopes_dir: Path, source_id: str) -> Path | None:
    hits = list(envelopes_dir.glob(source_id + _HASH_GLOB))
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)   # newest sealing wins


def resolve_ancestors(envelopes_dir: str | Path,
                      sources: list[str]) -> dict[str, ProofEnvelope | None]:
    """Transitively load the cited grounding from the envelope store. A source
    with no stored envelope maps to None (fails closed downstream)."""
    envelopes_dir = Path(envelopes_dir)
    out: dict[str, ProofEnvelope | None] = {}
    frontier = list(dict.fromkeys(sources))
    while frontier:
        sid = frontier.pop()
        if sid in out:
            continue
        path = _stored_envelope(envelopes_dir, sid)
        env = load_envelope(path) if path else None
        out[sid] = env
        if env is not None:
            frontier.extend(s for s in _cited_sources(env) if s not in out)
    return out


def recheck_grounding(current: ProofEnvelope, local_verdict: str, *,
                      envelopes_dir: str | Path,
                      workdirs: dict[str, tuple[str, str]]) -> dict:
    """Re-witness the cited ancestors and fold the closure over the citation DAG.

    `workdirs` maps ancestor task_id -> (workdir, candidate_path): the oracle
    environment each ancestor re-runs in. Missing entry -> that ancestor is
    UNVERIFIABLE (fail closed, reason recorded — see module docstring).

    Returns {"verdict": <transitive verdict for `current`>,
             "verdicts": {node_id: verdict, ...}, "reasons": {ancestor_id: why}}.
    """
    sources = _cited_sources(current)
    ancestors = resolve_ancestors(envelopes_dir, sources)
    nodes: list[DepNode] = []
    reasons: dict[str, str] = {}
    for sid, env in ancestors.items():
        if env is None:
            nodes.append(DepNode(id=sid, local=UNVERIFIABLE, has_receipt=False))
            reasons[sid] = "cited grounding has no stored envelope"
            continue
        wd = workdirs.get(sid)
        if wd is None:
            local = UNVERIFIABLE
            reasons[sid] = ("no oracle environment supplied for re-run — "
                            "fail closed, not re-run in a wrong workdir")
        else:
            v = witness_envelope(env, workdir=wd[0], candidate_path=wd[1])
            local = v.verdict
            reasons[sid] = v.reason
        nodes.append(DepNode(id=sid, local=local, deps=_cited_sources(env),
                             has_receipt=bool(env.oracle_output_hash)))
    nodes.append(DepNode(id=current.task_id, local=local_verdict, deps=sources,
                         has_receipt=bool(current.oracle_output_hash)))
    verdicts = transitive_verdicts(nodes)
    return {"verdict": verdicts[current.task_id],
            "verdicts": verdicts, "reasons": reasons}
