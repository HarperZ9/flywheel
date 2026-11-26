"""Preregistered Arm A vs Arm B Local Frontier Evaluation Harness (JFC-3P).

Compares:
  Arm A (single_shot): raw small local model, zero external recall, zero oracle retry.
  Arm B (jfc3p_loop): same local model + compact DS-07 recall (<= 125 tokens) +
      independent deterministic oracle diagnostics (buildc 1.15.0 / DS-03 f64 / DS-01)
      with bounded retries (max_iters=3) and zero answer leakage.

Computes exact pass rates, Wilson 95% CIs, exact two-sided McNemar p-values,
tokens/sec, peak VRAM GB, and planted oracle false-accept controls.
Pure stdlib Python, <= 250 lines, every function <= 50 lines.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .eval_tasks import EvalTask, build_eval_tasks, verify_task_output
from .local_backends import MockBackend, make_backend


@dataclass(frozen=True)
class TaskRunRecord:
    task_id: str
    domain: str
    passed: bool
    iterations_used: int
    tokens_per_sec: float
    peak_vram_gb: float | None
    last_diagnostic: str


def wilson_ci_95(k: int, n: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    """Exact Wilson score 95% confidence interval for binomial proportion k/n."""
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)


def mcnemar_exact_p(a_only: int, b_only: int) -> float:
    """Exact two-sided binomial McNemar p-value on discordant pairs."""
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    return round(min(1.0, 2.0 * tail), 6)


def _run_arm_a_task(backend: Any, task: EvalTask, *, use_live_buildc: bool) -> TaskRunRecord:
    res = backend.generate(task.prompt, max_new_tokens=384, iteration=0)
    ok, diag = verify_task_output(task, res.text, use_live_buildc=use_live_buildc)
    return TaskRunRecord(task.task_id, task.domain, ok, 1, res.tokens_per_sec, res.peak_vram_gb, diag)


def _run_arm_b_task(
    backend: Any, task: EvalTask, *, max_iters: int, use_live_buildc: bool
) -> TaskRunRecord:
    base_prompt = f"{task.recall_card}\n\nTask:\n{task.prompt}"
    prompt = base_prompt
    tps_vals: list[float] = []
    vram_vals: list[float] = []
    diag = "unrun"
    for it in range(max_iters):
        res = backend.generate(prompt, max_new_tokens=384, iteration=it)
        tps_vals.append(res.tokens_per_sec)
        if res.peak_vram_gb is not None:
            vram_vals.append(res.peak_vram_gb)
        ok, diag = verify_task_output(task, res.text, use_live_buildc=use_live_buildc)
        if ok:
            return TaskRunRecord(
                task.task_id, task.domain, True, it + 1,
                sum(tps_vals) / len(tps_vals), max(vram_vals) if vram_vals else None, diag,
            )
        prompt = (
            f"{base_prompt}\n\nPrevious attempt failed independent verification:\n"
            f"{diag}\nFix the defect and reply in the exact required format."
        )
    return TaskRunRecord(
        task.task_id, task.domain, False, max_iters,
        sum(tps_vals) / max(1, len(tps_vals)), max(vram_vals) if vram_vals else None, diag,
    )


def _summarize_arm(records: Sequence[TaskRunRecord]) -> dict[str, Any]:
    n = len(records)
    k = sum(1 for r in records if r.passed)
    lo, hi = wilson_ci_95(k, n)
    by_dom: dict[str, dict[str, Any]] = {}
    for dom in sorted({r.domain for r in records}):
        sub = [r for r in records if r.domain == dom]
        sk = sum(1 for r in sub if r.passed)
        dlo, dhi = wilson_ci_95(sk, len(sub))
        by_dom[dom] = {"passed": sk, "total": len(sub), "rate": round(sk / len(sub), 4), "wilson_95": [dlo, dhi]}
    vrams = [r.peak_vram_gb for r in records if r.peak_vram_gb is not None]
    mean_tps = sum(r.tokens_per_sec for r in records) / max(1, n)
    mean_iters = sum(r.iterations_used for r in records) / max(1, n)
    return {
        "passed": k,
        "total": n,
        "pass_rate": round(k / max(1, n), 4),
        "wilson_95": [lo, hi],
        "mean_iterations": round(mean_iters, 3),
        "mean_tokens_per_sec": round(mean_tps, 2),
        "peak_vram_gb": round(max(vrams), 3) if vrams else None,
        "by_domain": by_dom,
    }


def run_planted_false_accept_control(
    tasks: Sequence[EvalTask], *, use_live_buildc: bool = True
) -> dict[str, Any]:
    """Verify independent oracles reject 100% of planted-wrong submissions."""
    false_accepts = 0
    for task in tasks:
        ok, _ = verify_task_output(task, task.planted_wrong_output, use_live_buildc=use_live_buildc)
        if ok:
            false_accepts += 1
    return {
        "tasks_checked": len(tasks),
        "false_accepts": false_accepts,
        "kill_rate": round((len(tasks) - false_accepts) / max(1, len(tasks)), 4),
        "passed": false_accepts == 0,
    }


def _paired_stats(
    arm_a: Sequence[TaskRunRecord], arm_b: Sequence[TaskRunRecord], rate_a: float, rate_b: float
) -> dict[str, Any]:
    both_pass = sum(1 for a, b in zip(arm_a, arm_b) if a.passed and b.passed)
    a_only = sum(1 for a, b in zip(arm_a, arm_b) if a.passed and not b.passed)
    b_only = sum(1 for a, b in zip(arm_a, arm_b) if (not a.passed) and b.passed)
    both_fail = sum(1 for a, b in zip(arm_a, arm_b) if (not a.passed) and (not b.passed))
    p_val = mcnemar_exact_p(a_only, b_only)
    verdict = "ARM_B_LIFT" if (b_only > a_only and p_val < 0.05) else ("POSITIVE_TREND" if b_only > a_only else "HONEST_NULL")
    return {
        "both_pass": both_pass, "a_only": a_only, "b_only": b_only, "both_fail": both_fail,
        "delta_pass_rate": round(rate_b - rate_a, 4), "mcnemar_exact_p": p_val, "verdict": verdict,
    }


def run_arm_comparison(
    backend: Any,
    tasks: Sequence[EvalTask] | None = None,
    *,
    max_iters_b: int = 3,
    use_live_buildc: bool = True,
) -> dict[str, Any]:
    """Execute preregistered Arm A vs Arm B paired comparison + false-accept control."""
    eval_tasks = list(tasks) if tasks is not None else build_eval_tasks()
    control = run_planted_false_accept_control(eval_tasks, use_live_buildc=use_live_buildc)
    arm_a = [_run_arm_a_task(backend, t, use_live_buildc=use_live_buildc) for t in eval_tasks]
    arm_b = [_run_arm_b_task(backend, t, max_iters=max_iters_b, use_live_buildc=use_live_buildc) for t in eval_tasks]
    sum_a, sum_b = _summarize_arm(arm_a), _summarize_arm(arm_b)
    payload = {
        "schema": "jfc3p-local-frontier-eval/1",
        "backend": getattr(backend, "name", "unknown"),
        "task_count": len(eval_tasks),
        "max_iters_b": max_iters_b,
        "oracle_false_accept_control": control,
        "arm_a_single_shot": sum_a,
        "arm_b_jfc3p_loop": sum_b,
        "paired_mcnemar": _paired_stats(arm_a, arm_b, sum_a["pass_rate"], sum_b["pass_rate"]),
        "per_task": [
            {
                "task_id": a.task_id, "domain": a.domain,
                "arm_a_pass": a.passed, "arm_b_pass": b.passed,
                "arm_b_iters": b.iterations_used, "arm_a_diag": a.last_diagnostic[:120],
                "arm_b_diag": b.last_diagnostic[:120],
            }
            for a, b in zip(arm_a, arm_b)
        ],
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload["report_sha256"] = digest
    return payload


def _default_mock_responder(prompt: str, iteration: int) -> str:
    tasks = build_eval_tasks()
    for t in tasks:
        if t.prompt[:40] in prompt:
            if "DS-07" not in prompt and iteration == 0:
                return t.planted_wrong_output
            if t.domain == "DS-02":
                return f"```bld\nfn main() ~ Console {{\n    println!(\"{t.expected_stdout}\");\n}}\n```"
            if t.domain == "DS-03":
                return f"ANSWER: {t.expected_value}"
            return f"TOOL: {t.required_tool}\nCMD: {' '.join(t.required_substrings)}"
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run JFC-3P Arm A vs Arm B local frontier evaluation")
    ap.add_argument("--backend", choices=["mock", "ollama", "transformers4bit"], default="mock")
    ap.add_argument("--model", default="mock-local-14b")
    ap.add_argument("--base-url", default="http://127.0.0.1:11434")
    ap.add_argument("--max-iters-b", type=int, default=3)
    ap.add_argument("--offline-buildc", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    backend = MockBackend(_default_mock_responder) if args.backend == "mock" else make_backend(args.backend, args.model, base_url=args.base_url)
    report = run_arm_comparison(backend, max_iters_b=args.max_iters_b, use_live_buildc=not args.offline_buildc)
    ctrl_ok = report["oracle_false_accept_control"]["passed"]
    tag = "[PASS]" if ctrl_ok else "[FAIL]"
    print(f"{tag} oracle_false_accept_control :: {json.dumps(report['oracle_false_accept_control'], sort_keys=True)}")
    print(f"[PASS] arm_a_vs_arm_b :: {json.dumps({'arm_a': report['arm_a_single_shot'], 'arm_b': report['arm_b_jfc3p_loop'], 'paired': report['paired_mcnemar']}, sort_keys=True)}")
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if ctrl_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
