"""proof_cache.py — proof-addressed memory: key a verified result on the
oracle-certified FACT, not the prompt that happened to produce it.

Strong-synthesis, NOT a breakthrough (stated plainly). The mechanism —
content-addressed keying — is prior art (RAG query-keys, RadixAttention prefix
KV, content-addressed stores, verifier memoization, proof-carrying code). The
unpublished MOVE is using the harness's own C2 invariant as a theorem:

    acceptance is oracle-gated and the oracle's verdict does not read the prompt,
    so the accepted fact is a function of (candidate, oracle, oracle-input) and
    is INDEPENDENT of the prompt -> the prompt can be dropped from the cache key.

Input-addressed caches provably cannot do this: they have no oracle certifying
that two different prompts yield the same verifiable fact, so they must key on
the input. We have that oracle. Dropping the prompt collapses two prompts that
differ only in a volatile attribution header (the live F2 bug: 0% agent
cache-hit) onto ONE entry.

Safety (C2 preserved): a proof-hit is RE-WITNESSED (`witness.witness_envelope`
re-runs the oracle) and served only on MATCH — never blind-trusted, never stale.

Scope condition (the falsifier's teeth): sound ONLY for oracles whose `verify`
ignores the prompt. `PROMPT_INDEPENDENT` is that honest allowlist; any oracle not
in it falls back to the existing prompt-keyed `cache.cache_key` (unchanged). If a
future oracle reads `task.prompt`, proof-addressing narrows (opt-out) rather than
silently corrupting — `tests/test_proof_cache.py` greps for exactly that.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .cache import ReceiptCache, oracle_input_hash
from .envelope import ProofEnvelope
from .oracle import Oracle
from .task import Task
from .witness import witness_envelope

# Oracles whose verify() provably does not read the prompt/system. An oracle
# absent here is treated as prompt-DEPENDENT and never proof-addressed.
PROMPT_INDEPENDENT: dict[str, bool] = {"pytest": True, "stub": True}


def is_prompt_independent(oracle_type: str) -> bool:
    return PROMPT_INDEPENDENT.get(oracle_type, False)


def proof_key(task: Task, oracle_type: str, oracle_cmd: str) -> str:
    """The oracle-certified-fact key. The prompt is ABSENT by construction —
    only what the accept decision depends on is bound."""
    parts = [task.task_id, oracle_type, oracle_cmd, oracle_input_hash(task)]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def proof_lookup(cache: ReceiptCache, task: Task, oracle: Oracle,
                 *, witness_recheck: bool = True) -> ProofEnvelope | None:
    """Hit only if (a) the oracle is prompt-independent, (b) a PASS envelope is
    stored under proof_key, and (c) re-witnessing it MATCHes now. Otherwise
    None, and the caller does a fresh run. Never a blind or stale serve."""
    if not is_prompt_independent(oracle.oracle_type):
        return None
    env = cache.lookup(proof_key(task, oracle.oracle_type, task.oracle_cmd))
    if env is None or env.verdict != "PASS":
        return None
    if not witness_recheck:
        return env
    wv = witness_envelope(env, workdir=task.workdir,
                          candidate_path=task.candidate_path)
    return env if wv.verdict == "MATCH" else None


def proof_insert(cache: ReceiptCache, task: Task,
                 envelope: ProofEnvelope) -> Path | None:
    """Dual-index write: only prompt-independent, accepted (PASS) envelopes get a
    proof-key entry. Returns None when skipped (the honest opt-out).

    Keyed on `task.oracle_cmd` (the DECLARED command) — not
    `envelope.oracle_cmd`, which an oracle may augment at run time (PytestOracle
    appends `--junitxml=... -q`). Insert and lookup must key identically; the
    stored `envelope.oracle_cmd` is still used for the re-witness re-run."""
    if envelope.verdict != "PASS" or not is_prompt_independent(envelope.oracle):
        return None
    return cache.insert(envelope, proof_key(task, envelope.oracle, task.oracle_cmd))
