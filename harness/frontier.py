"""frontier.py -- the RAM/compute frontier, measured on this machine.

The field's answer to trillion-parameter economics is architectural --
MoE active-parameter budgets, hybrid linear attention (Ling/Ring 2.6,
arXiv 2606.15079), disk-streamed experts (Colibri) -- and every one of
those claims arrives as someone else's number on someone else's hardware.
This module is the platform's answer: a model earns its roster place
through a CAPABILITY PROBE run here (tokens/sec, latency, output hash),
and the frontier table composes probes with the uplift bench's verified
rates into capability-per-GB -- so 'which model should this machine run'
is decided by receipts produced on this machine, never by imported
leaderboards. The verified loop is part of the economics: the bench
already showed a 1.8GB model's pass rate doubling under an external
check, which changes what 'enough model' means.
"""
from __future__ import annotations

import hashlib
import time

SCHEMA = "flywheel.capability-probe/v1"
_PROBE_PROMPT = ("Write a Python function fib(n) returning the nth "
                 "Fibonacci number iteratively.")


def capability_probe(endpoint: str, *, proposer=None,
                     max_new_tokens: int = 96) -> dict:
    """One measured generation on this machine. `proposer` injectable;
    live probes resolve the endpoint through the roster."""
    if proposer is None:
        from .endpoint_registry import make_endpoint_proposer
        base, _, sub = endpoint.partition(":")
        try:
            proposer = make_endpoint_proposer(base, model=sub or None)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "endpoint": endpoint}
    t0 = time.perf_counter()
    try:
        out = proposer.generate(_PROBE_PROMPT, seed=0, temperature=0.0,
                                max_new_tokens=max_new_tokens)
        text = out.text if isinstance(out.text, str) else str(out.text)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "endpoint": endpoint}
    latency = time.perf_counter() - t0
    # Whitespace token count: a deliberate, stated approximation.
    n_tokens = len(text.split())
    return {"schema": SCHEMA, "endpoint": endpoint,
            "latency_s": round(latency, 3),
            "tok_s": round(n_tokens / latency, 2) if latency > 0 else 0.0,
            "tokens_approx": n_tokens,
            "output_sha256": hashlib.sha256(
                text.encode("utf-8")).hexdigest(),
            "note": "measured on this machine (whitespace-token "
                    "approximation, stated); not a leaderboard import"}


def frontier_table(root, *, probes: "list | None" = None) -> dict:
    """Compose capability probes with the uplift bench's measured rates.
    capability_per_gb = verified pass rate / disk GB, only when the disk
    size is known -- an unknown is a null, never an estimate."""
    import json as _json
    from pathlib import Path as _Path
    # Merge across ALL bench artifacts, newest first, first-seen per
    # provider+arm -- a roster measured across several runs must not
    # vanish because the newest artifact covered one model.
    runs_dir = _Path(root) / "artifacts" / "uplift"
    docs = []
    if runs_dir.is_dir():
        for p in sorted(runs_dir.glob("*.json"),
                        key=lambda q: q.stat().st_mtime, reverse=True):
            try:
                doc = _json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if doc.get("schema") == "flywheel.uplift-bench/v1":
                docs.append(doc)
    rates: dict = {}
    separated: dict = {}
    sources: list = []
    for doc in docs:
        sources.append(doc.get("comparison_key", ""))
        for row in doc.get("rows", []):
            entry = rates.setdefault(row.get("provider", ""), {})
            entry.setdefault(row.get("arm", ""), row.get("pass_rate"))
        for d in doc.get("deltas", []):
            separated.setdefault(d.get("provider"),
                                 not d.get("includes_zero", True))
    rows = []
    for probe in probes or []:
        endpoint = probe.get("endpoint", "")
        r = rates.get(endpoint, {})
        disk = probe.get("disk_gb")
        verified = r.get("wrapped")
        rows.append({
            "endpoint": endpoint,
            "tok_s": probe.get("tok_s"),
            "disk_gb": disk,
            "bare_rate": r.get("bare"),
            "verified_rate": verified,
            "uplift_separated": separated.get(endpoint, False),
            "capability_per_gb": (round(verified / disk, 4)
                                  if isinstance(verified, (int, float))
                                  and isinstance(disk, (int, float))
                                  and disk > 0 else None),
        })
    return {"schema": "flywheel.frontier/v1", "rows": rows,
            "bench_sources": sources,
            "note": "every number measured here: probes on this machine, "
                    "rates from the paired-arm bench; unknowns are nulls"}
