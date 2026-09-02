"""verified_bench.py -- private verified benchmarks and the verified
cost/quality frontier.

Run a task set across every endpoint in the ladder, dispose each
attempt through a real gate, and compute what no competitor can: the
verified pass rate per endpoint on gates you own, and the Pareto
frontier of verified quality per dollar. The model proposes; the gate
decides; every attempt is a receipt. Tasks are private -- they come
from your repo and never leak into anyone's training data.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_sha256
from .pool_arms import _wilson
from .statistics import MIN_REPLICATES, between_seed_sd

SCHEMA = "flywheel.verified-bench/v1"
FRONTIER_SCHEMA = "flywheel.verified-frontier/v1"
REPLICATE_SD_SCHEMA = "flywheel.replicate-sd/v1"


def wilson_95_fields(passes: int, attempts: int) -> dict:
    """Wilson 95% interval fields for a verified pass rate, reusing the
    pool_arms implementation. A zero denominator refuses the interval:
    with no attempts there is no rate to bracket, and printing [0, 0]
    would claim certainty where there is no data."""
    if attempts <= 0:
        return {"wilson_95": None,
                "wilson_95_refused": (
                    "ZERO_DENOMINATOR: no attempts, so no pass rate "
                    "exists to put an interval around")}
    lo, hi = _wilson(passes, attempts)
    return {"wilson_95": [round(lo, 6), round(hi, 6)]}


def load_task_set(path: Path | str) -> list[dict]:
    """A task set is JSONL: {task_id, prompt, gate_cmd}. Strict: a row
    missing any field is refused, duplicate ids are refused."""
    tasks: list[dict] = []
    seen: set[str] = set()
    for i, line in enumerate(Path(path).read_text(encoding="utf-8")
                             .splitlines()):
        if not line.strip():
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"task row {i} is not JSON") from exc
        if not isinstance(task, dict) or not all(
                isinstance(task.get(k), str) and task[k]
                for k in ("task_id", "prompt", "gate_cmd")):
            raise ValueError(f"task row {i} is missing a required field")
        if task["task_id"] in seen:
            raise ValueError(f"duplicate task id: {task['task_id']}")
        seen.add(task["task_id"])
        tasks.append(task)
    if not tasks:
        raise ValueError("the task set is empty")
    return tasks


def run_benchmark(
    *,
    tasks: list[dict],
    endpoints: list[str],
    propose,
    run_gate,
    created_at: str,
    seeds: list[int] | tuple[int, ...] = (0,),
    randomness_control: dict[str, str] | None = None,
) -> dict:
    """Task-major, endpoint-minor, replicate-inner deterministic order.
    `propose(endpoint, prompt, seed) -> str` is the model layer;
    `run_gate(gate_cmd, proposed) -> {"passed": bool, "gate_ref": str}`
    is the accept path -- and the gate is the only thing that decides.

    `seeds` runs one full replicate per seed for every task x endpoint
    pair; the default (0,) is the historical single-replicate pin.
    `randomness_control` maps an endpoint to "seed" (default: the seed
    is honored) or "unsupported" (subscription CLIs: replicates are
    temporal, the attempt records seed None, no seed claim is made)."""
    if not tasks or not endpoints:
        raise ValueError("a benchmark needs tasks and endpoints")
    seed_list = list(seeds)
    if not seed_list:
        raise ValueError("a benchmark needs at least one seed")
    if any(isinstance(s, bool) or not isinstance(s, int) for s in seed_list):
        raise ValueError("seeds must be integers")
    if len(set(seed_list)) != len(seed_list):
        raise ValueError("duplicate seeds would double-count a replicate")
    control = dict(randomness_control or {})
    if any(v not in ("seed", "unsupported") for v in control.values()):
        raise ValueError(
            'randomness_control values must be "seed" or "unsupported"')
    attempts = []
    for task in tasks:
        for endpoint in endpoints:
            honors = control.get(endpoint, "seed")
            for repetition, seed in enumerate(seed_list):
                proposed = propose(endpoint, task["prompt"], seed)
                outcome = run_gate(task["gate_cmd"], proposed)
                attempts.append({
                    "task_id": task["task_id"],
                    "endpoint": endpoint,
                    "seed": seed if honors == "seed" else None,
                    "repetition": repetition,
                    "randomness_control": honors,
                    "proposed_sha256": canonical_sha256(proposed),
                    "gate_cmd": task["gate_cmd"],
                    "gate_pass": bool(outcome["passed"]),
                    "gate_ref": str(outcome.get("gate_ref", "")),
                })
    bench = {
        "schema": SCHEMA,
        "created_at": created_at,
        "endpoints": sorted(endpoints),
        "seeds": seed_list,
        "attempts": attempts,
        "denominator": {"tasks": len(tasks), "endpoints": len(endpoints),
                        "replicates": len(seed_list),
                        "attempts": len(attempts)},
        "does_not_prove": (
            "a verified pass rate is over this task set and these gates "
            "only; it is not a general capability score"),
    }
    bench["bench_sha256"] = canonical_sha256(
        {k: v for k, v in bench.items() if k != "bench_sha256"})
    return bench


def verified_frontier(bench: dict,
                      cost_per_task: dict | None) -> dict:
    """Verified pass rate per endpoint; with costs, the Pareto frontier
    of verified quality per dollar. An endpoint is dominated when another
    passes at least as much for no more money."""
    totals: dict[str, dict] = {}
    for attempt in bench["attempts"]:
        row = totals.setdefault(attempt["endpoint"],
                                {"passes": 0, "attempts": 0})
        row["attempts"] += 1
        row["passes"] += 1 if attempt["gate_pass"] else 0
    rankings = []
    for endpoint in sorted(totals):
        row = totals[endpoint]
        rate = row["passes"] / row["attempts"]
        cost = (cost_per_task or {}).get(endpoint)
        rankings.append({
            "endpoint": endpoint,
            "verified_passes": row["passes"],
            "attempts": row["attempts"],
            "verified_pass_rate": rate,
            **wilson_95_fields(row["passes"], row["attempts"]),
            "cost_per_task": cost,
        })
    ranked = sorted(rankings,
                    key=lambda r: (-r["verified_pass_rate"],
                                   r["cost_per_task"]
                                   if r["cost_per_task"] is not None else 0))
    pareto: list[str] = []
    if cost_per_task:
        for r in rankings:
            dominated = any(
                other["verified_pass_rate"] >= r["verified_pass_rate"]
                and other["cost_per_task"] <= r["cost_per_task"]
                and (other["verified_pass_rate"] > r["verified_pass_rate"]
                     or other["cost_per_task"] < r["cost_per_task"])
                for other in rankings if other["endpoint"] != r["endpoint"])
            if not dominated:
                pareto.append(r["endpoint"])
    notes = ("the frontier is over this task set and these gates only; "
             "costs are inputs, not measurements")
    if bench.get("denominator", {}).get("replicates", 1) > 1:
        notes += ("; replicate attempts are pooled into each endpoint's "
                  "denominator, so the interval treats correlated "
                  "replicates as independent and reads tighter than it is")
    return {
        "schema": FRONTIER_SCHEMA,
        "bench_sha256": bench["bench_sha256"],
        "rankings": ranked,
        "pareto": pareto,
        "does_not_prove": notes,
    }


def replicate_sd(bench: dict) -> dict:
    """Between-replicate SD per endpoint, labelled by what was actually
    controlled: seed-honoring endpoints get between_seed_sd; an endpoint
    that cannot honor a seed yields temporal replicates and the label is
    between_attempt_sd, because a seed word there would overclaim. Fewer
    than MIN_REPLICATES replicates refuses the SD outright."""
    rows = []
    for endpoint in bench["endpoints"]:
        attempts = [a for a in bench["attempts"]
                    if a["endpoint"] == endpoint]
        honors = attempts[0].get("randomness_control", "seed")
        label = ("between_seed_sd" if honors == "seed"
                 else "between_attempt_sd")
        by_rep: dict[int, list[dict]] = {}
        for a in attempts:
            by_rep.setdefault(int(a.get("repetition", 0)), []).append(a)
        values = [sum(1 for a in by_rep[r] if a["gate_pass"])
                  / len(by_rep[r]) for r in sorted(by_rep)]
        row = {"endpoint": endpoint, "randomness_control": honors,
               "statistic": label, "n_replicates": len(values),
               "replicate_pass_rates": [round(v, 6) for v in values]}
        if len(values) < MIN_REPLICATES:
            row.update({"mean": None, "sd": None, "sd_refused": (
                f"MIN_REPLICATES: a between-replicate SD needs at least "
                f"{MIN_REPLICATES} replicates and got {len(values)}")})
        else:
            stat = between_seed_sd(values)
            notes = list(stat["does_not_prove"])
            if honors != "seed":
                notes.append(
                    "NOT_SEED_REPLICATES: this endpoint cannot honor a "
                    "seed; these are temporal replicates, so provider-"
                    "side drift sits inside the number.")
            row.update({"mean": stat["mean"], "sd": stat["sd"],
                        "does_not_prove": notes})
        rows.append(row)
    return {"schema": REPLICATE_SD_SCHEMA,
            "bench_sha256": bench["bench_sha256"], "rows": rows}


def subprocess_gate(gate_cmd: str, proposed: str, *,
                    workspace: Path,
                    timeout_s: float = 120.0) -> dict:
    """The production gate: write the proposal, run the gate command in
    a real working directory, and let its exit code decide. No shell, a
    hard timeout, and the run output is hashed into the gate ref so the
    attempt cites an exact run."""
    import hashlib
    import shlex
    import subprocess

    proposal_path = workspace / "PROPOSED.md"
    proposal_path.write_text(proposed, encoding="utf-8")
    argv = shlex.split(gate_cmd)
    if not argv:
        return {"passed": False, "gate_ref": ""}
    import os
    repo_root = str(Path(__file__).resolve().parent.parent)
    inherited_pythonpath = os.environ.get("PYTHONPATH", "")
    pythonpath = repo_root + (os.pathsep + inherited_pythonpath
                              if inherited_pythonpath else "")
    try:
        completed = subprocess.run(
            argv, cwd=workspace, capture_output=True,
            timeout=timeout_s,
            env={**os.environ, "PYTHONPATH": pythonpath,
                 "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
        passed = completed.returncode == 0
        output = (completed.stdout + completed.stderr).decode(
            "utf-8", "replace")[-4000:]
    except (subprocess.TimeoutExpired, OSError):
        return {"passed": False, "gate_ref": hashlib.sha256(
            gate_cmd.encode()).hexdigest()}
    return {"passed": passed,
            "gate_ref": hashlib.sha256(
                (gate_cmd + output).encode()).hexdigest()}


def run_private_benchmark(
    *,
    tasks: list[dict],
    ladder: list,
    workspace_root: Path,
    timeout_s: float = 120.0,
    created_at: str,
    seeds: list[int] | tuple[int, ...] = (0,),
    randomness_control: dict[str, str] | None = None,
) -> dict:
    """The real loop: propose through each ladder backend's chat, dispose
    through the subprocess gate in a fresh per-attempt workspace."""
    workspace_root = Path(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)

    def propose(endpoint: str, prompt: str, seed: int) -> str:
        for backend in ladder:
            if backend.name == endpoint:
                out = backend.chat(
                    [{"role": "user", "content": prompt}], system="",
                    max_tokens=2048, temperature=0, seed=seed)
                return out["text"]
        raise ValueError(f"endpoint {endpoint!r} is not on the ladder")

    def gate(gate_cmd: str, proposed: str) -> dict:
        import tempfile
        with tempfile.TemporaryDirectory(dir=workspace_root) as workdir:
            return subprocess_gate(gate_cmd, proposed,
                                   workspace=Path(workdir),
                                   timeout_s=timeout_s)

    return run_benchmark(tasks=tasks, endpoints=[b.name for b in ladder],
                         propose=propose, run_gate=gate,
                         created_at=created_at, seeds=seeds,
                         randomness_control=randomness_control)
