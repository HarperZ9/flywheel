"""Check submitted benchmark consistency, not evaluator authenticity.

No commands, model calls, files, or proposal payloads are executed or read.
The projection retains task identities and digests, never gate commands.
"""
from __future__ import annotations

import re

from .evidence_json import canonical_sha256
from .trace_bench import regression_report


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unique_list(values: object, kind: type) -> bool:
    return (isinstance(values, list) and bool(values)
            and all(type(v) is kind for v in values)
            and len(set(values)) == len(values))


def validate_projection(doc: dict) -> None:
    """Recheck counts and cell identities even if a binding was resealed."""
    require(isinstance(doc, dict), "benchmark projection must be an object")
    require(digest(doc.get("bench_sha256")) and digest(doc.get("source_sha256")),
            "benchmark source digests are malformed")
    tasks, endpoints, seeds = (doc.get(k) for k in ("tasks", "endpoints", "seeds"))
    for name, values in (("tasks", tasks), ("endpoints", endpoints)):
        require(_unique_list(values, str) and all(text(v) for v in values),
                f"benchmark {name} must be unique nonempty identities")
        require(values == sorted(values), f"benchmark {name} must be sorted")
    require(_unique_list(seeds, int), "benchmark seeds must be unique integers")
    attempts, denominator = doc.get("attempts"), doc.get("denominator")
    require(isinstance(attempts, list) and bool(attempts), "benchmark has no attempts")
    expected = {"tasks": len(tasks), "endpoints": len(endpoints),
                "replicates": len(seeds), "attempts": len(attempts)}
    require(isinstance(denominator, dict) and denominator == expected
            and all(type(v) is int for v in denominator.values()),
            "benchmark denominator disagrees with its identities")
    require(len(attempts) == len(tasks) * len(endpoints) * len(seeds),
            "benchmark does not cover the full task/endpoint/replicate scope")
    cells, gates, controls = set(), {}, {}
    for a in attempts:
        require(isinstance(a, dict), "benchmark attempt must be an object")
        task, endpoint, repetition = (a.get(k) for k in ("task_id", "endpoint", "repetition"))
        require(isinstance(task, str) and task in tasks
                and isinstance(endpoint, str) and endpoint in endpoints,
                "attempt identity is outside the benchmark scope")
        require(type(repetition) is int and 0 <= repetition < len(seeds),
                "attempt repetition is outside the benchmark scope")
        key = (task, endpoint, repetition)
        require(key not in cells, "duplicate benchmark attempt identity")
        cells.add(key)
        control, seed = a.get("randomness_control"), a.get("seed")
        require(control in ("seed", "unsupported"), "unknown randomness control")
        require((control == "seed" and type(seed) is int and seed == seeds[repetition])
                or (control == "unsupported" and seed is None),
                "attempt seed disagrees with its replicate/control")
        require(controls.setdefault(endpoint, control) == control,
                "endpoint randomness control changed within the benchmark")
        for field in ("proposed_sha256", "gate_cmd_sha256", "gate_ref_sha256"):
            require(digest(a.get(field)), f"attempt {field} is malformed")
        require(gates.setdefault(task, a["gate_cmd_sha256"]) == a["gate_cmd_sha256"],
                "one task identity names different gate commands")
        require(type(a.get("gate_pass")) is bool, "gate_pass must be a boolean")


def project_bench(bench: dict) -> dict:
    require(isinstance(bench, dict) and bench.get("schema") == "flywheel.verified-bench/v1",
            "source must be a verified-bench/v1 producer document")
    seal = bench.get("bench_sha256")
    require(digest(seal) and seal == canonical_sha256(
        {k: v for k, v in bench.items() if k != "bench_sha256"}),
        "benchmark seal does not reproduce")
    require(isinstance(bench.get("created_at"), str) and text(bench.get("does_not_prove")),
            "benchmark producer metadata is missing")
    attempts = bench.get("attempts")
    require(isinstance(attempts, list) and bool(attempts), "benchmark has no attempts")
    projected = []
    for a in attempts:
        require(isinstance(a, dict), "benchmark attempt must be an object")
        require(text(a.get("task_id")) and text(a.get("gate_cmd"))
                and text(a.get("gate_ref")), "attempt task/gate identity is missing")
        row = {k: a.get(k) for k in ("task_id", "endpoint", "seed", "repetition",
               "randomness_control", "proposed_sha256", "gate_pass")}
        row.update(gate_cmd_sha256=canonical_sha256(a["gate_cmd"]),
                   gate_ref_sha256=canonical_sha256(a["gate_ref"]))
        projected.append(row)
    projection = {"bench_sha256": seal, "source_sha256": canonical_sha256(bench),
                  "tasks": sorted({a["task_id"] for a in projected}),
                  "endpoints": bench.get("endpoints"), "seeds": bench.get("seeds"),
                  "denominator": bench.get("denominator"), "attempts": projected}
    validate_projection(projection)
    return projection


def validate_summary(summary: dict) -> None:
    require(isinstance(summary, dict), "evidence summary must be an object")
    current = summary.get("current")
    validate_projection(current)
    require(all(a["gate_pass"] for a in current["attempts"]),
            "skill evidence contains failing current attempts")
    kind = summary.get("kind")
    if kind == "verified_bench":
        require(summary.get("prior") is None, "a direct benchmark has no prior source")
    else:
        require(kind == "trace_regression", "unknown evidence kind")
        prior = summary.get("prior")
        validate_projection(prior)
        require(prior["denominator"]["replicates"] == current["denominator"]["replicates"] == 1,
                "trace reports collapse replicate identities; bind the current bench directly")
        for field in ("tasks", "endpoints", "seeds"):
            require(prior[field] == current[field], "trace benchmark scopes differ")
        def scope(p):
            return {(a["task_id"], a["endpoint"]):
                    (a["gate_cmd_sha256"], a["randomness_control"])
                    for a in p["attempts"]}
        require(scope(prior) == scope(current), "trace gate/control scope changed")


def summarize_evidence(evidence: dict, *, prior_bench=None, current_bench=None) -> dict:
    require(isinstance(evidence, dict), "evidence must be an object")
    schema = evidence.get("schema")
    if schema == "flywheel.verified-bench/v1":
        require(prior_bench is None and current_bench is None,
                "direct benchmark binding takes no extra source benches")
        summary = {"kind": "verified_bench", "current": project_bench(evidence), "prior": None}
    elif schema == "flywheel.trace-regression/v1":
        summary = {"kind": "trace_regression", "prior": project_bench(prior_bench),
                   "current": project_bench(current_bench)}
        validate_summary(summary)
        require(canonical_sha256(evidence) == canonical_sha256(
            regression_report(prior_bench, current_bench)),
            "trace report does not reproduce from its source benchmarks")
    else:
        raise ValueError("unsupported skill evidence schema")
    validate_summary(summary)
    return summary


def summary_source_digest(summary: dict) -> str:
    """The trace producer uses only task/endpoint/pass fields retained here."""
    if summary["kind"] == "verified_bench":
        return summary["current"]["source_sha256"]
    return canonical_sha256(regression_report(summary["prior"], summary["current"]))
