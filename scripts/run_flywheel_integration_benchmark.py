"""run_flywheel_integration_benchmark.py â€” all-flywheel benchmark harness.

Runs a deterministic, integration-focused benchmark pass that exercises:
- flywheel.spin (cold cache -> warm cache compounding trace)
- evolutionary_flywheel compounding
- inversion_flywheel acceleration + floor-preservation
- valve/backflow and frontier backflow mechanics
- data-flywheel token conservation
- accountability benchmark + strawman contrast
- loop-closure connectivity
- M7 scorecard comparisons for gpt-5.3-codex-spark and local flywheel arms
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.accountability_bench import score_harness, score_strawman
from harness.adversarial_corpus import naive_closure, run_corpus, transitive_verdicts
from harness.backflow import run_levels as run_frontier_levels
from harness.cache import ReceiptCache
from harness.data_flywheel import criterion_conservation, manufactured_yield
from harness.evolutionary_flywheel import ChainTask, measure_compounding
from harness.externalization_ablation import run_all_domains
from harness.flywheel import research_feed_from_catalog, spin
from harness.inversion_flywheel import run_acceleration, run_floor_preservation
from harness.loop_closure import measure_loop
from harness.oracle import PytestOracle
from harness.proposer import ProposerOutput
from harness.task import Task, load_task
from harness.valve_flywheel import externalization_contrast as valve_contrast
from harness.eval import ArmConfig
from harness.agent_recovery_bench import (
    RecoveryPolicy,
    default_scenarios,
    run_agent_recovery_benchmark,
    run_backend_recovery_benchmark,
)
from harness.source_mined_bench import run_source_mined_benchmark
from harness.endpoints import build_endpoints
from harness.local_agent import OllamaBackend, ServeBackend
from scripts.forum_context_shapes import (
    DEFAULT_DATASET as DEFAULT_FORUM_DATASET,
    benchmark_cases as forum_benchmark_cases,
    load_dataset as load_forum_dataset,
)
from scripts.model_card_benchmark_shapes import (
    DEFAULT_MODEL_DATASET,
    DEFAULT_PUBLIC_THINKER_DATASET,
    DEFAULT_RESEARCH_DATASET,
    DEFAULT_SOCIAL_DATASET,
    benchmark_cases as model_card_benchmark_cases,
    load_datasets as load_model_card_datasets,
)


CORRECT = """def add(a, b):\n    return a + b\n"""
INCORRECT = """def add(a, b):\n    return 0\n"""


def write_task_files(task_dir: Path, task_id: str, route: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "solution.py").write_text(CORRECT, encoding="utf-8")
    tests = task_dir / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_solution.py").write_text(
        "from solution import add\n\n"
        "def test_add_positives():\n"
        "    assert add(2, 3) == 5\n\n"
        "def test_add_negatives():\n"
        "    assert add(-1, -1) == -2\n\n"
        "def test_add_zero():\n"
        "    assert add(0, 5) == 5\n",
        encoding="utf-8",
    )
    payload = {
        "task_id": task_id,
        "prompt": (
            f"[route:{route}] Implement function add(a, b) so it behaves like + "
            "for integers. Return only executable code."
        ),
        "oracle": "pytest",
        "oracle_cmd": "python -m pytest tests/ -q",
        "candidate_path": "solution.py",
        "system": "",
        "max_new_tokens": 64,
        "temperature": 0.0,
        "seed": 0,
    }
    (task_dir / "task.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_bench_tasks(root: Path) -> tuple[list[Task], dict[str, str]]:
    specs = [
        ("fw_pass_a", "PASS_A", True),
        ("fw_pass_b", "PASS_B", True),
        ("fw_fail_a", "FAIL_A", False),
        ("fw_fail_b", "FAIL_B", False),
    ]
    mapping: dict[str, str] = {}
    tasks: list[Task] = []
    for task_id, route, passing in specs:
        task_dir = root / task_id
        write_task_files(task_dir, task_id, route)
        mapping[route] = CORRECT if passing else INCORRECT
        tasks.append(load_task(task_dir, workdir=task_dir))
    return tasks, mapping


class RouteStubProposer:
    def __init__(self, routes: dict[str, str], default: str = "pass\n"):
        self.routes = routes
        self.default = default
        self.model_ref = "integration/routed-stub"

    def generate(
        self,
        prompt: str,
        *,
        seed: int,
        temperature: float,
        max_new_tokens: int,
        system: str = "",
    ) -> ProposerOutput:
        selected = self.default
        for route, candidate in self.routes.items():
            if f"[route:{route}]" in prompt:
                selected = candidate
                break
        return ProposerOutput(
            text=selected,
            model_ref=self.model_ref,
            seed=seed,
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest()[:16],
            cache="stub",
        )


def run_spin_benchmark(root: Path, turns: int) -> dict[str, Any]:
    tasks, routes = build_bench_tasks(root / "spin")
    proposer = RouteStubProposer(routes)
    catalog = [
        {
            "id": "run-1",
            "title": "frontier flywheel benchmark integration",
            "abstract": "spin + telemetry + evolve",
            "summary": "measure cache reuse and candidate telemetry after turn1",
        }
    ]
    research_feed = research_feed_from_catalog(catalog, top_k=1)
    search = ArmConfig(name="verified_inference", n_candidates=2)
    previous_cwd = Path.cwd()
    with TemporaryDirectory() as tmp:
        os.chdir(root / "spin")
        try:
            traces = spin(
                tasks,
                proposer,
                PytestOracle(),
                cache=ReceiptCache(Path(tmp) / "cache"),
                search=search,
                turns=turns,
                research_feed=research_feed,
            )
        finally:
            os.chdir(previous_cwd)
    first, last = traces[0], traces[-1]
    return {
        "schema": "flywheel.spin/integration/v1",
        "n_tasks": len(tasks),
        "turns": turns,
        "first_turn": {
            "turn": first.turn,
            "pass_rate": first.pass_rate,
            "cache_hit_rate": first.cache_hit_rate,
            "avg_oracle_calls": first.avg_oracle_calls,
        },
        "last_turn": {
            "turn": last.turn,
            "pass_rate": last.pass_rate,
            "cache_hit_rate": last.cache_hit_rate,
            "avg_oracle_calls": last.avg_oracle_calls,
        },
        "deltas": {
            "pass_rate": round(last.pass_rate - first.pass_rate, 3),
            "cache_hit_rate": round(last.cache_hit_rate - first.cache_hit_rate, 3),
            "avg_oracle_calls": round(last.avg_oracle_calls - first.avg_oracle_calls, 3),
        },
        "auto_apply_candidates": len(last.auto_apply_candidates),
        "cycle_summary": last.cycle_summary,
    }


def run_core_benchmarks(root: Path) -> dict[str, Any]:
    chain = [
        ChainTask("seed", [], "p0"),
        ChainTask("step_1", ["p0"], "p1"),
        ChainTask("step_2", ["p1"], "p2"),
        ChainTask("step_3", ["p2"], "p3"),
    ]
    ev_open = measure_compounding(chain, closed=False)
    ev_closed = measure_compounding(chain, closed=True)
    inversion = run_acceleration()
    floor = run_floor_preservation()
    valve = valve_contrast([3, 5, -1, 9, 4, 8], threshold=4.0)
    frontier = run_frontier_levels([0.4, 0.2, 0.8, 1.0, 0.7], relax_under_adverse=True)
    externalization = run_all_domains(root / "externalization")
    accountability = score_harness()
    strawman = score_strawman()
    loop = measure_loop(root / "loop")
    data_specs = [
        {"task_id": "d1", "prompt": "p1", "solution": "s1", "hidden_tests": "t1"},
        {"task_id": "d2", "prompt": "p2", "solution": "s2", "hidden_tests": "t2"},
    ]
    data = {
        "criterion_conservation": criterion_conservation(data_specs),
        "manufactured_yield": manufactured_yield(data_specs, oracle_calls_per_task=1),
    }
    anti_theatre = run_corpus(naive_closure)
    return {
        "schema": "flywheel.core/integration/v1",
        "evolutionary": {"open": ev_open, "closed": ev_closed},
        "inversion": inversion,
        "floor_preservation": floor,
        "valve": valve,
        "frontier_backflow": frontier,
        "externalization_ablation": externalization,
        "accountability": accountability,
        "accountability_strawman": strawman,
        "loop_closure": loop,
        "data_flywheel": data,
        "adversarial_corpus_naive": anti_theatre,
    }


def _forum_case_quality(case: dict[str, Any]) -> dict[str, Any]:
    required = [
        "id",
        "objective",
        "task_prompt",
        "oracle_checks",
        "metrics",
        "source_ids",
        "source_pattern",
    ]
    missing = [field for field in required if not case.get(field)]
    counts = {
        "oracle_checks": len(case.get("oracle_checks", [])),
        "metrics": len(case.get("metrics", [])),
        "source_ids": len(case.get("source_ids", [])),
        "tool_implications": len(case.get("tool_implications", [])),
    }
    return {
        "case_id": case.get("id"),
        "ready": not missing and all(count > 0 for count in counts.values()),
        "missing": missing,
        "counts": counts,
        "metrics": list(case.get("metrics", [])),
    }


def run_forum_context_benchmarks(root: Path, dataset: Path) -> dict[str, Any]:
    """Materialize forum-derived benchmark cases into the integration artifact set.

    This is a source-shape benchmark lane, not a model scorecard. It measures
    whether the curated source context is complete enough to become executable
    agentic benchmark work: source traceability, oracle checks, metrics, and
    recovery-specific measurement hooks must all survive the transformation.
    """
    data = load_forum_dataset(dataset)
    cases = forum_benchmark_cases(data)
    case_set = {
        "schema": "forum.benchmark-case-set/v1",
        "generated_from": str(dataset),
        "cases": cases,
    }
    out_path = root / "forum_benchmark_cases.json"
    out_path.write_text(json.dumps(case_set, indent=2), encoding="utf-8")

    qualities = [_forum_case_quality(case) for case in cases]
    recovery_case = next(
        (case for case in cases if case["id"] == "forum_agent_recovery_faults_v1"),
        None,
    )
    metric_names = sorted({metric for case in cases for metric in case.get("metrics", [])})
    source_ids = sorted({sid for case in cases for sid in case.get("source_ids", [])})
    return {
        "schema": "forum.context-shape/integration/v1",
        "dataset": str(dataset),
        "artifact": str(out_path),
        "sources": len(data["sources"]),
        "source_ids": source_ids,
        "cases": len(cases),
        "ready_cases": sum(1 for quality in qualities if quality["ready"]),
        "case_quality": qualities,
        "metric_count": len(metric_names),
        "metrics": metric_names,
        "agent_recovery_case_present": recovery_case is not None,
        "agent_recovery_metrics": (
            list(recovery_case.get("metrics", [])) if recovery_case else []
        ),
        "closed_loop_role": (
            "forum context -> benchmark cases -> harness measurements -> "
            "model/router/tool uplift backlog -> smaller local model release evidence"
        ),
    }


def _source_case_quality(case: dict[str, Any]) -> dict[str, Any]:
    required = [
        "id",
        "category",
        "objective",
        "task_prompt",
        "oracle_checks",
        "metrics",
        "source_ids",
        "source_pattern",
        "variables",
    ]
    missing = [field for field in required if not case.get(field)]
    counts = {
        "oracle_checks": len(case.get("oracle_checks", [])),
        "metrics": len(case.get("metrics", [])),
        "source_ids": len(case.get("source_ids", [])),
        "variables": len(case.get("variables", [])),
    }
    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "ready": not missing and all(count > 0 for count in counts.values()),
        "missing": missing,
        "counts": counts,
        "metrics": list(case.get("metrics", [])),
    }


def run_model_card_context_benchmarks(
    root: Path,
    *,
    model_dataset: Path,
    social_dataset: Path,
    research_dataset: Path,
    public_thinker_dataset: Path,
) -> dict[str, Any]:
    """Materialize model-card and public-research signals into benchmark cases."""
    datasets = load_model_card_datasets(
        model_dataset,
        social_dataset,
        research_dataset,
        public_thinker_dataset,
    )
    cases = model_card_benchmark_cases(datasets)
    case_set = {
        "schema": "source-mined.benchmark-case-set/v1",
        "generated_from": {
            "model": str(model_dataset),
            "social": str(social_dataset),
            "research": str(research_dataset),
            "public_thinker": str(public_thinker_dataset),
        },
        "mission": datasets["model"]["mission"],
        "cases": cases,
    }
    out_path = root / "source_mined_benchmark_cases.json"
    out_path.write_text(json.dumps(case_set, indent=2), encoding="utf-8")
    executable = run_source_mined_benchmark(cases)
    exec_path = root / "source_mined_executable_benchmark.json"
    exec_path.write_text(json.dumps(executable, indent=2), encoding="utf-8")

    qualities = [_source_case_quality(case) for case in cases]
    metric_names = sorted({metric for case in cases for metric in case.get("metrics", [])})
    categories = sorted({case.get("category", "") for case in cases})
    source_ids = sorted({sid for case in cases for sid in case.get("source_ids", [])})
    variables = sorted({var for case in cases for var in case.get("variables", [])})
    return {
        "schema": "source-mined.context-shape/integration/v1",
        "artifact": str(out_path),
        "executable_artifact": str(exec_path),
        "executable_summary": {
            "case_count": executable["case_count"],
            "passed_cases": executable["passed_cases"],
            "failed_cases": executable["failed_cases"],
            "pass_rate": executable["pass_rate"],
            "metric_count": executable["metric_count"],
        },
        "model_dataset": str(model_dataset),
        "social_dataset": str(social_dataset),
        "research_dataset": str(research_dataset),
        "public_thinker_dataset": str(public_thinker_dataset),
        "frontier_sources": len(datasets["model"]["frontier_sources"]),
        "local_open_weight_sources": len(datasets["model"]["local_open_weight_sources"]),
        "social_sources": len(datasets["social"]["sources"]),
        "research_lanes": len(datasets["research"]["new_benchmark_lanes"]),
        "public_thinker_sources": len(datasets["public_thinker"]["sources"]),
        "public_thinker_lanes": len(datasets["public_thinker"]["benchmark_lanes"]),
        "source_ids": source_ids,
        "cases": len(cases),
        "ready_cases": sum(1 for quality in qualities if quality["ready"]),
        "case_quality": qualities,
        "categories": categories,
        "metric_count": len(metric_names),
        "metrics": metric_names,
        "variable_count": len(variables),
        "variables": variables,
        "latent_objective_case_present": any(
            case["id"] == "latent_objective_audience_dependence_v1" for case in cases
        ),
        "anti_scoreboard_case_present": any(
            case["id"] == "anti_scoreboard_truthfulness_v1" for case in cases
        ),
        "model_release_case_present": any(
            case["id"] == "local_model_release_evidence_v1" for case in cases
        ),
        "closed_loop_role": (
            "model/frontier cards + public research -> benchmark cases -> "
            "harness variables -> local model release gates -> recursive uplift evidence"
        ),
    }


def run_scorecard(cmd: list[str], out_path: Path) -> dict[str, Any] | None:
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-1200:],
            "stderr": proc.stderr[-1200:],
        }
    return json.loads(out_path.read_text(encoding="utf-8"))


def run_m7_benchmarks(
    root: Path,
    n_tasks: int,
    model: str,
    *,
    m7_live: bool = False,
    m7_provider: str = "codex",
    m7_mode: str = "plan",
) -> dict[str, Any]:
    runner = Path(__file__).resolve().parent / "run_m7_eval.py"
    codex_out = root / "m7_frontier_codex_dry.json"
    fly_out = root / "m7_flywheel_local_dry.json"
    if m7_live:
        codex_cmd = [
            sys.executable,
            str(runner),
            "--frontier",
            "--frontier-all",
            "--frontier-providers",
            m7_provider,
            "--frontier-modes",
            m7_mode,
            "--frontier-only",
            "--frontier-provider",
            m7_provider,
            "--frontier-model",
            model,
            "--baseline-provider",
            m7_provider,
            "--baseline-modes",
            m7_mode,
            "--n-tasks",
            str(n_tasks),
            "--out",
            str(codex_out),
        ]
        fly_cmd = [
            sys.executable,
            str(runner),
            "--baseline-provider",
            m7_provider,
            "--baseline-modes",
            m7_mode,
            "--baseline-model",
            model,
            "--n-tasks",
            str(n_tasks),
            "--out",
            str(fly_out),
        ]
        return {
            "codex": {
                "out": str(codex_out),
                "result": run_scorecard(codex_cmd, codex_out),
            },
            "flywheel": {
                "out": str(fly_out),
                "result": run_scorecard(fly_cmd, fly_out),
            },
        }

    codex_cmd = [
        sys.executable,
        str(runner),
        "--dry-run",
        "--frontier",
        "--frontier-provider",
        "codex",
        "--frontier-model",
        model,
        "--frontier-modes",
        "api",
        "--n-tasks",
        str(n_tasks),
        "--out",
        str(codex_out),
    ]
    fly_cmd = [
        sys.executable,
        str(runner),
        "--dry-run",
        "--local",
        "--local-provider",
        "serve",
        "--local-model",
        "14b-cpt-adapter",
        "--n-tasks",
        str(n_tasks),
        "--out",
        str(fly_out),
    ]
    return {
        "codex": {
            "out": str(codex_out),
            "result": run_scorecard(codex_cmd, codex_out),
        },
        "flywheel": {
            "out": str(fly_out),
            "result": run_scorecard(fly_cmd, fly_out),
        },
    }


def summarize_card(card: dict[str, Any], *, kind: str) -> dict[str, Any]:
    if not card or "arms" not in card:
        return {"kind": kind, "missing": True}
    arms = card["arms"]
    frontier = next((k for k in arms if k.startswith("frontier_")), "single_shot")
    verified = arms.get("verified_inference", {})
    single = arms.get("single_shot", {})
    return {
        "kind": kind,
        "frontier_or_single": frontier,
        "frontier_pass_rate": arms.get(frontier, {}).get("pass_rate"),
        "verified_inference": verified.get("pass_rate"),
        "single_shot": single.get("pass_rate"),
        "verified_vs_single": (
            round((verified["pass_rate"] - single["pass_rate"]), 3)
            if verified and single else None
        ),
        "n_tasks": card.get("meta", {}).get("n_tasks"),
    }


def compare_with_existing(
    new: dict[str, Any],
    existing_codex: dict[str, Any],
    existing_flywheel: dict[str, Any],
) -> dict[str, Any]:
    new_codex = summarize_card(new["codex"].get("result", {}), kind="new_codex")
    new_fly = summarize_card(new["flywheel"].get("result", {}), kind="new_flywheel")
    old_codex = summarize_card(existing_codex, kind="existing_codex")
    old_fly = summarize_card(existing_flywheel, kind="existing_flywheel")
    return {
        "new": {"codex": new_codex, "flywheel": new_fly},
        "existing": {"codex": old_codex, "flywheel": old_fly},
        "delta": {
            "codex_frontier_pass": (
                (new_codex.get("frontier_pass_rate") or 0.0)
                - (old_codex.get("frontier_pass_rate") or 0.0)
                if new_codex.get("frontier_pass_rate") is not None
                and old_codex.get("frontier_pass_rate") is not None
                else None
            ),
            "flywheel_verified_pass": (
                (new_fly.get("verified_inference") or 0.0)
                - (old_fly.get("verified_inference") or 0.0)
                if new_fly.get("verified_inference") is not None
                and old_fly.get("verified_inference") is not None
                else None
            ),
            "flywheel_vs_single_delta": (
                (new_fly.get("verified_vs_single") or 0.0)
                - (old_fly.get("verified_vs_single") or 0.0)
                if new_fly.get("verified_vs_single") is not None
                and old_fly.get("verified_vs_single") is not None
                else None
            ),
        },
    }


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _empty_backend_recovery(provider: str, reason: str) -> dict[str, Any]:
    return {
        "schema": "agent.backend-recovery-benchmark/v1",
        "adapter": "chat-backend",
        "provider": provider,
        "live": False,
        "operational": False,
        "skipped": True,
        "skip_reason": reason,
        "backend_name": "",
        "scenario_count": 0,
        "metrics": {
            "recovery_success_rate": 0.0,
            "silent_failure_rate": 0.0,
            "retry_budget_compliance": 0.0,
            "fallback_quality": 0.0,
            "receipt_completeness": 0.0,
            "p95_recovery_latency": 0,
        },
        "results": [],
    }


def run_selected_backend_recovery(
    *,
    provider: str,
    serve_url: str,
    ollama_url: str,
    model: str,
    modes: tuple[str, ...],
    max_scenarios: int,
    policy: RecoveryPolicy | None = None,
) -> dict[str, Any]:
    provider = provider.lower().strip()
    scenarios = default_scenarios()
    if max_scenarios > 0:
        scenarios = scenarios[:max_scenarios]

    if provider == "dry":
        report = run_backend_recovery_benchmark(scenarios=scenarios, policy=policy)
        report.update({
            "provider": "dry",
            "live": False,
            "operational": report["metrics"]["recovery_success_rate"] > 0,
            "skipped": False,
            "backend_name": "dry-echo",
        })
        return report

    if provider == "serve":
        probe = ServeBackend(base_url=serve_url, name="serve-probe")
        if not probe.health():
            return _empty_backend_recovery(provider, f"serve backend unhealthy at {serve_url}")

        def factory(role: str):
            return ServeBackend(base_url=serve_url, name=f"serve-{role}")

        report = run_backend_recovery_benchmark(
            scenarios=scenarios, backend_factory=factory, policy=policy)
        report.update({
            "provider": provider,
            "live": True,
            "operational": report["metrics"]["recovery_success_rate"] > 0,
            "skipped": False,
            "backend_name": "serve",
        })
        return report

    if provider == "ollama":
        probe = OllamaBackend(base_url=ollama_url, model=model, name="ollama-probe")
        if not probe.health():
            return _empty_backend_recovery(provider, f"ollama backend unhealthy at {ollama_url}")
        resolved = probe._resolved or model

        def factory(role: str):
            return OllamaBackend(base_url=ollama_url, model=resolved, name=f"ollama-{role}")

        report = run_backend_recovery_benchmark(
            scenarios=scenarios, backend_factory=factory, policy=policy)
        report.update({
            "provider": provider,
            "live": True,
            "operational": report["metrics"]["recovery_success_rate"] > 0,
            "skipped": False,
            "backend_name": f"ollama:{resolved}",
        })
        return report

    endpoint_provider = "opencode" if provider == "open-code" else provider
    backends = build_endpoints(providers=[endpoint_provider], modes=modes)
    if not backends:
        return _empty_backend_recovery(
            provider,
            f"no configured endpoint backend for provider={provider} modes={','.join(modes)}",
        )
    selected = backends[0]

    def factory(role: str):
        return selected

    report = run_backend_recovery_benchmark(
        scenarios=scenarios, backend_factory=factory, policy=policy)
    report.update({
        "provider": provider,
        "live": True,
        "operational": report["metrics"]["recovery_success_rate"] > 0,
        "skipped": False,
        "backend_name": selected.name,
    })
    return report


def build_markdown(report: dict[str, Any]) -> str:
    return (
        "# Flywheel Integration Benchmark Outcome\n\n"
        f"- timestamp_utc: {report['timestamp_utc']}\n"
        f"- run_root: {report['out_root']}\n\n"
        "## Flywheel core\n\n"
        f"- spin turns: {report['spin']['turns']} tasks: {report['spin']['n_tasks']}\n"
        f"- spin pass_rate delta: {report['spin']['deltas']['pass_rate']}\n"
        f"- spin cache_hit_rate delta: {report['spin']['deltas']['cache_hit_rate']}\n"
        f"- spin avg_oracle_calls delta: {report['spin']['deltas']['avg_oracle_calls']}\n"
        f"- evolutionary closed monotone: {report['core']['evolutionary']['closed']['monotone_rising']}\n"
        f"- evolutionary open monotone: {report['core']['evolutionary']['open']['monotone_rising']}\n"
        f"- inversion acceleration: {report['core']['inversion']['accelerated']}\n"
        f"- inversion floor preserved: {report['core']['inversion']['same_floor']}\n"
        f"- loop closure ratio: {report['core']['loop_closure'].get('closure_fraction')}\n"
        f"- accountability: {report['core']['accountability'].get('overall')} "
        f"(strawman {report['core']['accountability_strawman'].get('overall')})\n\n"
        "## M7 comparisons\n\n"
        f"- codex frontier pass_rate: {report['m7']['summary']['new']['codex'].get('frontier_pass_rate')}\n"
        f"- flywheel verified_inference pass_rate: {report['m7']['summary']['new']['flywheel'].get('verified_inference')}\n"
        f"- codex pass delta vs existing: {report['m7']['summary']['delta'].get('codex_frontier_pass')}\n"
        f"- flywheel pass delta vs existing: {report['m7']['summary']['delta'].get('flywheel_verified_pass')}\n"
        f"- flywheel verified-vs-single delta vs existing: {report['m7']['summary']['delta'].get('flywheel_vs_single_delta')}\n"
        "\n## Forum-derived custom benchmarks\n\n"
        f"- case artifact: {report['forum']['artifact']}\n"
        f"- sources: {report['forum']['sources']}\n"
        f"- benchmark cases: {report['forum']['cases']}\n"
        f"- ready cases: {report['forum']['ready_cases']}\n"
        f"- metric count: {report['forum']['metric_count']}\n"
        f"- agent recovery case present: {report['forum']['agent_recovery_case_present']}\n"
        f"- agent recovery metrics: {', '.join(report['forum']['agent_recovery_metrics'])}\n"
        f"- closed-loop role: {report['forum']['closed_loop_role']}\n"
        "\n## Source-mined model-card and social-divergence benchmarks\n\n"
        f"- case artifact: {report['model_card']['artifact']}\n"
        f"- executable artifact: {report['model_card'].get('executable_artifact', '')}\n"
        f"- executable pass_rate: {report['model_card'].get('executable_summary', {}).get('pass_rate')}\n"
        f"- executable passed_cases: {report['model_card'].get('executable_summary', {}).get('passed_cases')}\n"
        f"- executable failed_cases: {report['model_card'].get('executable_summary', {}).get('failed_cases')}\n"
        f"- frontier sources: {report['model_card']['frontier_sources']}\n"
        f"- local/open-weight sources: {report['model_card']['local_open_weight_sources']}\n"
        f"- social-divergence sources: {report['model_card']['social_sources']}\n"
        f"- public-research lanes: {report['model_card']['research_lanes']}\n"
        f"- public-thinker sources: {report['model_card'].get('public_thinker_sources', 0)}\n"
        f"- public-thinker lanes: {report['model_card'].get('public_thinker_lanes', 0)}\n"
        f"- benchmark cases: {report['model_card']['cases']}\n"
        f"- ready cases: {report['model_card']['ready_cases']}\n"
        f"- categories: {', '.join(report['model_card']['categories'])}\n"
        f"- metric count: {report['model_card']['metric_count']}\n"
        f"- variable count: {report['model_card']['variable_count']}\n"
        f"- latent objective case present: {report['model_card']['latent_objective_case_present']}\n"
        f"- anti-scoreboard case present: {report['model_card']['anti_scoreboard_case_present']}\n"
        f"- model release case present: {report['model_card']['model_release_case_present']}\n"
        f"- closed-loop role: {report['model_card']['closed_loop_role']}\n"
        "\n## Executable agent-recovery benchmark\n\n"
        f"- scenarios: {report['agent_recovery']['scenario_count']}\n"
        f"- recovery_success_rate: {report['agent_recovery']['metrics']['recovery_success_rate']}\n"
        f"- silent_failure_rate: {report['agent_recovery']['metrics']['silent_failure_rate']}\n"
        f"- retry_budget_compliance: {report['agent_recovery']['metrics']['retry_budget_compliance']}\n"
        f"- fallback_quality: {report['agent_recovery']['metrics']['fallback_quality']}\n"
        f"- receipt_completeness: {report['agent_recovery']['metrics']['receipt_completeness']}\n"
        f"- p95_recovery_latency: {report['agent_recovery']['metrics']['p95_recovery_latency']}\n"
        "\n## Backend-adapter recovery benchmark\n\n"
        f"- adapter: {report['backend_recovery']['adapter']}\n"
        f"- provider: {report['backend_recovery'].get('provider')}\n"
        f"- backend: {report['backend_recovery'].get('backend_name')}\n"
        f"- live: {report['backend_recovery'].get('live')}\n"
        f"- operational: {report['backend_recovery'].get('operational')}\n"
        f"- skipped: {report['backend_recovery'].get('skipped')}\n"
        f"- skip_reason: {report['backend_recovery'].get('skip_reason', '')}\n"
        f"- scenarios: {report['backend_recovery']['scenario_count']}\n"
        f"- recovery_success_rate: {report['backend_recovery']['metrics']['recovery_success_rate']}\n"
        f"- silent_failure_rate: {report['backend_recovery']['metrics']['silent_failure_rate']}\n"
        f"- retry_budget_compliance: {report['backend_recovery']['metrics']['retry_budget_compliance']}\n"
        f"- fallback_quality: {report['backend_recovery']['metrics']['fallback_quality']}\n"
        f"- receipt_completeness: {report['backend_recovery']['metrics']['receipt_completeness']}\n"
        f"- p95_recovery_latency: {report['backend_recovery']['metrics']['p95_recovery_latency']}\n"
        f"- retry_use_rate: {report['backend_recovery']['metrics'].get('retry_use_rate')}\n"
        f"- fallback_use_rate: {report['backend_recovery']['metrics'].get('fallback_use_rate')}\n"
        f"- typed_escalation_rate: {report['backend_recovery']['metrics'].get('typed_escalation_rate')}\n"
        f"- fault_coverage: {', '.join(report['backend_recovery']['metrics'].get('fault_coverage', []))}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spin-turns", type=int, default=3)
    ap.add_argument("--m7-n-tasks", type=int, default=2)
    ap.add_argument("--m7-model", default="gpt-5.3-codex-spark")
    ap.add_argument("--out-root", default="C:/tmp/flywheel_integration_bench")
    ap.add_argument("--existing-codex", default="C:/tmp/m7_frontier_dry_v2.json")
    ap.add_argument("--existing-flywheel", default="C:/tmp/m7_local_serve_dry2.json")
    ap.add_argument("--m7-live", action="store_true")
    ap.add_argument("--m7-provider", default="codex")
    ap.add_argument("--m7-mode", default="plan")
    ap.add_argument("--forum-dataset", default=str(DEFAULT_FORUM_DATASET))
    ap.add_argument("--skip-forum", action="store_true")
    ap.add_argument("--model-card-dataset", default=str(DEFAULT_MODEL_DATASET))
    ap.add_argument("--social-divergence-dataset", default=str(DEFAULT_SOCIAL_DATASET))
    ap.add_argument("--research-context-dataset", default=str(DEFAULT_RESEARCH_DATASET))
    ap.add_argument("--public-thinker-dataset", default=str(DEFAULT_PUBLIC_THINKER_DATASET))
    ap.add_argument("--skip-model-card-benchmarks", action="store_true")
    ap.add_argument("--backend-recovery-provider", default="dry",
                    help="dry, serve, ollama, codex, claude, opencode, or open-code")
    ap.add_argument("--backend-recovery-modes", default="plan,api,provider,cloud")
    ap.add_argument("--backend-recovery-serve-url", default="http://127.0.0.1:8765")
    ap.add_argument("--backend-recovery-ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--backend-recovery-model", default="")
    ap.add_argument("--backend-recovery-max-scenarios", type=int, default=0,
                    help="0 means all recovery scenarios")
    ap.add_argument("--backend-recovery-retry-budget", type=int, default=2)
    ap.add_argument("--backend-recovery-disable-fallback", action="store_true")
    ap.add_argument("--backend-recovery-disable-stale-recompute", action="store_true")
    ap.add_argument("--backend-recovery-disable-typed-escalation", action="store_true")
    a = ap.parse_args()

    out_root = Path(a.out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    run_root = out_root / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    spin = run_spin_benchmark(run_root, a.spin_turns)
    core = run_core_benchmarks(run_root)
    m7 = run_m7_benchmarks(
        run_root,
        a.m7_n_tasks,
        a.m7_model,
        m7_live=a.m7_live,
        m7_provider=a.m7_provider,
        m7_mode=a.m7_mode,
    )
    existing_codex = (
        json.loads(Path(a.existing_codex).read_text(encoding="utf-8"))
        if Path(a.existing_codex).exists()
        else {}
    )
    existing_flywheel = (
        json.loads(Path(a.existing_flywheel).read_text(encoding="utf-8"))
        if Path(a.existing_flywheel).exists()
        else {}
    )
    m7_compare = compare_with_existing(m7, existing_codex, existing_flywheel)
    forum = (
        {
            "schema": "forum.context-shape/integration/v1",
            "skipped": True,
            "artifact": "",
            "sources": 0,
            "cases": 0,
            "ready_cases": 0,
            "metric_count": 0,
            "agent_recovery_case_present": False,
            "agent_recovery_metrics": [],
            "closed_loop_role": "skipped",
        }
        if a.skip_forum
        else run_forum_context_benchmarks(run_root, Path(a.forum_dataset))
    )
    model_card = (
        {
            "schema": "source-mined.context-shape/integration/v1",
            "skipped": True,
            "artifact": "",
            "executable_artifact": "",
            "executable_summary": {
                "case_count": 0,
                "passed_cases": 0,
                "failed_cases": 0,
                "pass_rate": 0.0,
                "metric_count": 0,
            },
            "frontier_sources": 0,
            "local_open_weight_sources": 0,
            "social_sources": 0,
            "research_lanes": 0,
            "cases": 0,
            "ready_cases": 0,
            "categories": [],
            "metric_count": 0,
            "variable_count": 0,
            "latent_objective_case_present": False,
            "anti_scoreboard_case_present": False,
            "model_release_case_present": False,
            "closed_loop_role": "skipped",
        }
        if a.skip_model_card_benchmarks
        else run_model_card_context_benchmarks(
            run_root,
            model_dataset=Path(a.model_card_dataset),
            social_dataset=Path(a.social_divergence_dataset),
            research_dataset=Path(a.research_context_dataset),
            public_thinker_dataset=Path(a.public_thinker_dataset),
        )
    )
    agent_recovery = run_agent_recovery_benchmark()
    backend_recovery = run_selected_backend_recovery(
        provider=a.backend_recovery_provider,
        serve_url=a.backend_recovery_serve_url,
        ollama_url=a.backend_recovery_ollama_url,
        model=a.backend_recovery_model,
        modes=tuple(_split_csv(a.backend_recovery_modes)) or ("plan", "api", "provider", "cloud"),
        max_scenarios=a.backend_recovery_max_scenarios,
        policy=RecoveryPolicy(
            retry_budget=a.backend_recovery_retry_budget,
            fallback_enabled=not a.backend_recovery_disable_fallback,
            stale_recompute_enabled=not a.backend_recovery_disable_stale_recompute,
            typed_escalation_enabled=not a.backend_recovery_disable_typed_escalation,
        ),
    )

    report = {
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "out_root": str(run_root),
        "spin": spin,
        "core": core,
        "forum": forum,
        "model_card": model_card,
        "agent_recovery": agent_recovery,
        "backend_recovery": backend_recovery,
        "m7": {"summary": m7_compare, "raw": m7},
    }
    out_json = run_root / "report.json"
    out_md = run_root / "report.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(build_markdown(report), encoding="utf-8")
    print(f"out_json={out_json}")
    print(f"out_md={out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
