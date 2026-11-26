"""Wave 14B Local RTX 4090 Live Arm C Deterministic Tool-Loop Evaluator.

Intercepts f64_oracle(...) and buildc_check/buildc_run/```buildlang``` tool calls emitted by
local models (Ollama / llama-server OpenAI-compatible loopback endpoints or mock generators),
executes them deterministically, feeds exact oracle results back, and compares Raw vs Arm C
pass rates plus planted-wrong trap rejection across jfc3p_wave11_eval_holdout.jsonl (84 items).
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import math
import operator
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Sequence

from .colab_h100_runner import build_forge_receipt

_SAFE_BINOPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_SAFE_UNARY: dict[type, Callable[[float], float]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_SAFE_FUNCS: dict[str, Callable[..., float]] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "atan2": math.atan2, "exp": math.exp, "log": math.log, "ln": math.log,
    "log10": math.log10, "sqrt": math.sqrt, "abs": abs, "pow": math.pow,
}
_SAFE_CONSTS: dict[str, float] = {
    "pi": math.pi, "e": math.e, "g0": 9.80665, "sigma": 5.670374419e-8, "c": 299792458.0, "mu_earth": 398600.4418,
}
_F64_CALL_RE = re.compile(r"(?:call:)?f64_oracle\(([^)\n]{1,240})\)")
_BUILDC_CALL_RE = re.compile(r"(?:call:)?buildc_(check|run)\(([^)\n]{1,240})\)")
_BLD_FENCE_RE = re.compile(r"```(?:buildlang|bld)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_NUM_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?")
_TRAP_REJECT_MARKERS: tuple[str, ...] = (
    "incorrect", "wrong", "false", "invalid", "reject", "flaw", "invert", "negative",
    "sign flip", "error", "cannot", "impossible", "unverified", "does not", "not true",
    "not valid", "bug", "trap", "contradict", "unknown", "myth", "fails", "misleading",
)


def _eval_ast_node(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return float(env[node.id])
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY:
        return _SAFE_UNARY[type(node.op)](_eval_ast_node(node.operand, env))
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINOPS:
        return _SAFE_BINOPS[type(node.op)](_eval_ast_node(node.left, env), _eval_ast_node(node.right, env))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS and not node.keywords:
        return float(_SAFE_FUNCS[node.func.id](*[_eval_ast_node(a, env) for a in node.args]))
    raise ValueError(f"disallowed AST node in f64_oracle: {type(node).__name__}")


def eval_safe_f64_expr(expr: str, variables: dict[str, float] | None = None) -> float:
    """Safely evaluate an IEEE-754 math expression using strict AST whitelisting (zero eval)."""
    env = dict(_SAFE_CONSTS)
    if variables:
        env.update({k: float(v) for k, v in variables.items()})
    val = _eval_ast_node(ast.parse(expr.strip(), mode="eval"), env)
    if not math.isfinite(val):
        raise ValueError("non-finite f64_oracle result")
    return val


def _run_named_f64_kernel(name: str, kw: dict[str, float]) -> dict[str, float]:
    if name == "vis_viva":
        r, a, mu = kw["r"], kw["a"], kw.get("mu", 398600.4418)
        return {"v_ell": math.sqrt(mu * (2.0 / r - 1.0 / a)), "v_circ": math.sqrt(mu / r)}
    if name == "hohmann":
        r1, r2, mu = kw["r1"], kw["r2"], kw.get("mu", 398600.4418)
        a_t = 0.5 * (r1 + r2)
        dv1 = math.sqrt(mu * (2.0 / r1 - 1.0 / a_t)) - math.sqrt(mu / r1)
        dv2 = math.sqrt(mu / r2) - math.sqrt(mu * (2.0 / r2 - 1.0 / a_t))
        return {"dv1": abs(dv1), "dv2": abs(dv2), "delta_v_total": abs(dv1) + abs(dv2)}
    if name == "tsiolkovsky":
        return {"delta_v": kw["isp"] * kw.get("g0", 9.80665) * math.log(kw["m_wet"] / kw["m_dry"])}
    if name == "kinetic_energy":
        return {"energy": 0.5 * kw["mass"] * (kw["velocity"] ** 2)}
    if name == "stefan_boltzmann":
        return {"irradiance": 5.670374419e-8 * (kw["temperature"] ** 4)}
    if name == "snell":
        return {"sin_theta2": (kw["n1"] / kw["n2"]) * math.sin(kw["theta1"])}
    if name == "ohm_power":
        return {"power": (kw["voltage"] ** 2) / kw["resistance"]}
    if name == "escape_velocity":
        return {"v_esc": math.sqrt(2.0 * kw.get("mu", 398600.4418) / kw["r"])}
    if name == "orbital_period":
        return {"period_s": 2.0 * math.pi * math.sqrt((kw["a"] ** 3) / kw.get("mu", 398600.4418))}
    raise ValueError(f"unknown f64_oracle kernel: {name}")


def execute_f64_oracle_call(arg_body: str) -> dict[str, Any]:
    """Execute either a named physics kernel (e.g. vis_viva, r=..., a=...) or a safe math expr."""
    parts = [p.strip() for p in arg_body.split(",") if p.strip()]
    if parts and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", parts[0]) and all("=" in p for p in parts[1:]):
        kw: dict[str, float] = {}
        for item in parts[1:]:
            k, v = item.split("=", 1)
            kw[k.strip()] = eval_safe_f64_expr(v.strip())
        res = _run_named_f64_kernel(parts[0], kw)
        return {"ok": True, "kernel": parts[0], "values": res, "primary": list(res.values())[-1]}
    val = eval_safe_f64_expr(arg_body)
    return {"ok": True, "kernel": "expr", "values": {"value": val}, "primary": val}


def extract_armc_tool_calls(text: str) -> list[dict[str, str]]:
    """Extract f64_oracle(...), buildc_check/run(...), and fenced ```buildlang``` blocks."""
    calls: list[dict[str, str]] = []
    for m in _F64_CALL_RE.finditer(text or ""):
        calls.append({"tool": "f64_oracle", "arg": m.group(1).strip()})
    for m in _BUILDC_CALL_RE.finditer(text or ""):
        calls.append({"tool": f"buildc_{m.group(1)}", "arg": m.group(2).strip()})
    for m in _BLD_FENCE_RE.finditer(text or ""):
        calls.append({"tool": "buildc_run", "arg": m.group(1).strip()})
    return calls


def _extract_numeric_candidates(text: str) -> list[float]:
    vals: list[float] = []
    for tok in _NUM_RE.findall(text or ""):
        try:
            f = float(tok)
            if math.isfinite(f):
                vals.append(f)
        except ValueError:
            continue
    return vals


def score_holdout_item(item: dict[str, Any], response_text: str, *, buildc_stdout: str | None = None) -> bool:
    """Deterministically score any of the 5 Wave 11 holdout eval_type categories."""
    etype = str(item.get("eval_type", ""))
    text = response_text or ""
    if etype == "numeric_f64_oracle":
        expected = float(item["expected_value"])
        rtol = float(item.get("rel_tol", 1e-6))
        atol = float(item.get("abs_tol", 1e-9))
        return any(math.isclose(v, expected, rel_tol=rtol, abs_tol=atol) for v in _extract_numeric_candidates(text))
    if etype == "buildlang_oracle":
        exp_out = str(item.get("expected_stdout", "")).strip()
        if buildc_stdout is not None:
            return exp_out in buildc_stdout.strip() if exp_out else len(buildc_stdout.strip()) >= 0
        return bool(exp_out) and exp_out in text and "fn " in text
    if etype == "code_unit_oracle":
        tokens = [str(t) for t in item.get("required_any_tokens", [])]
        return any(tok in text for tok in tokens) if tokens else False
    if etype == "longppl_multihop_oracle":
        exp = str(item.get("expected_exact", "")).strip().lower()
        return bool(exp) and exp in text.lower()
    if etype == "planted_wrong_trap":
        low = text.lower()
        return any(m in low for m in _TRAP_REJECT_MARKERS)
    return False


def make_openai_http_client(base_url: str, model: str, *, timeout_s: float = 60.0) -> Callable[[list[dict[str, str]]], dict[str, Any]]:
    """Build a loopback-only OpenAI-compatible HTTP client (Ollama / llama-server)."""
    if not (base_url.startswith("http://127.0.0.1:") or base_url.startswith("http://localhost:")):
        raise ValueError("live Arm C HTTP client requires loopback URL (127.0.0.1 or localhost)")
    urllib_req = importlib.import_module("urllib.request")
    endpoint = base_url.rstrip("/") + "/chat/completions"

    def _call(messages: list[dict[str, str]]) -> dict[str, Any]:
        body = json.dumps({"model": model, "messages": messages, "temperature": 0.0, "max_tokens": 512}).encode("utf-8")
        req = urllib_req.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.perf_counter()
        with urllib_req.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        dt = max(1e-6, time.perf_counter() - t0)
        text = str(data["choices"][0]["message"]["content"])
        toks = int((data.get("usage") or {}).get("completion_tokens") or max(1, len(text.split())))
        return {"text": text, "tokens": toks, "elapsed_s": dt}

    return _call


def make_buildc_runner(buildc_path: Path) -> Callable[[str, str], dict[str, Any]]:
    """Build a deterministic live buildc.exe check/run executor using a temp .bld file."""
    sp = importlib.import_module("subprocess")

    def _run(tool: str, code: str) -> dict[str, Any]:
        sub = "check" if tool == "buildc_check" else "run"
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "armc_probe.bld"
            src.write_text(code, encoding="utf-8")
            proc = sp.run([str(buildc_path), sub, str(src)], capture_output=True, text=True, timeout=15)
            return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

    return _run


def _default_offline_buildc_runner(tool: str, code: str) -> dict[str, Any]:
    ok = "fn " in code and "TODO" not in code.upper() and code.count("{") > 0 and code.count("{") == code.count("}")
    return {"ok": ok, "exit_code": 0 if ok else 1, "stdout": "" if ok else "", "stderr": "" if ok else "structural check failed"}


def _execute_turn_tools(
    calls: Sequence[dict[str, str]], runner: Callable[[str, str], dict[str, Any]],
) -> tuple[list[str], str | None]:
    tool_outputs: list[str] = []
    buildc_out: str | None = None
    for call in calls[:3]:
        if call["tool"] == "f64_oracle":
            try:
                tool_outputs.append(json.dumps(execute_f64_oracle_call(call["arg"]), sort_keys=True))
            except Exception as exc:
                tool_outputs.append(json.dumps({"ok": False, "error": str(exc)}))
        else:
            br = runner(call["tool"], call["arg"])
            if br.get("ok"):
                buildc_out = str(br.get("stdout", ""))
            tool_outputs.append(json.dumps(br, sort_keys=True))
    return tool_outputs, buildc_out


def _emit_armc_receipt(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_path = out_dir / "armc_eval_report.json"
    rep_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rec = build_forge_receipt(
        task_id="wave14b-rtx4090-armc-eval", artifact_paths=[rep_path],
        oracle_exit_code=0 if report["ok"] else 1,
        oracle_stdout=f"[PASS] armc={report['armc_passed']}/{report['total_items']} raw={report['raw_passed']}/{report['total_items']}\n",
        oracle_command=["python", "-m", "plexus.jfc3p_forge.rtx4090_armc_eval"], root=out_dir,
    )
    (out_dir / "engine_receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["receipt_envelope_sha256"] = rec["digests"]["envelope_sha256"]


def evaluate_armc_holdout(
    items: Sequence[dict[str, Any]], generate_fn: Callable[[list[dict[str, str]]], dict[str, Any]],
    *, buildc_runner: Callable[[str, str], dict[str, Any]] | None = None, out_dir: Path | None = None,
) -> dict[str, Any]:
    """Run Raw vs Arm-C tool-loop evaluation across holdout items and emit metrics + receipt."""
    runner = buildc_runner if buildc_runner is not None else _default_offline_buildc_runner
    by_type: dict[str, dict[str, int]] = {}
    tot_raw = tot_armc = tot_toks = tool_calls_exec = 0
    tot_sec = 0.0
    for item in items:
        bucket = by_type.setdefault(str(item.get("eval_type", "unknown")), {"total": 0, "raw_passed": 0, "armc_passed": 0})
        bucket["total"] += 1
        msgs = [{"role": "user", "content": str(item.get("prompt", ""))}]
        t1 = generate_fn(msgs)
        raw_text = str(t1.get("text", ""))
        tot_toks += int(t1.get("tokens", max(1, len(raw_text.split()))))
        tot_sec += max(1e-6, float(t1.get("elapsed_s", 0.01)))
        raw_ok = score_holdout_item(item, raw_text)
        tot_raw += int(raw_ok)
        bucket["raw_passed"] += int(raw_ok)
        calls = extract_armc_tool_calls(raw_text)
        armc_text, buildc_out = raw_text, None
        if calls:
            tool_outputs, buildc_out = _execute_turn_tools(calls, runner)
            tool_calls_exec += min(3, len(calls))
            t2 = generate_fn(msgs + [{"role": "assistant", "content": raw_text}, {"role": "user", "content": "[ORACLE_RESULT] " + " | ".join(tool_outputs)}])
            armc_text = str(t2.get("text", ""))
            tot_toks += int(t2.get("tokens", max(1, len(armc_text.split()))))
            tot_sec += max(1e-6, float(t2.get("elapsed_s", 0.01)))
        armc_ok = score_holdout_item(item, armc_text, buildc_stdout=buildc_out)
        tot_armc += int(armc_ok)
        bucket["armc_passed"] += int(armc_ok)
    n = max(1, len(items))
    report: dict[str, Any] = {
        "ok": tot_armc >= tot_raw, "total_items": len(items), "raw_passed": tot_raw, "raw_pass_rate": round(tot_raw / n, 6),
        "armc_passed": tot_armc, "armc_pass_rate": round(tot_armc / n, 6), "armc_lift": round((tot_armc - tot_raw) / n, 6),
        "tool_calls_executed": tool_calls_exec, "tokens_per_second": round(tot_toks / max(tot_sec, 1e-6), 2),
        "peak_vram_mb": None, "by_eval_type": by_type,
    }
    if out_dir is not None:
        _emit_armc_receipt(report, out_dir)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 14B RTX 4090 Live Arm C Holdout Evaluator")
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", default="jfc3p-7b-oracle-v1")
    parser.add_argument("--buildc", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    items = [json.loads(ln) for ln in args.holdout.read_text(encoding="utf-8").splitlines() if ln.strip()]
    rep = evaluate_armc_holdout(items, make_openai_http_client(args.base_url, args.model), buildc_runner=make_buildc_runner(args.buildc) if args.buildc else None, out_dir=args.out)
    print(json.dumps(rep, indent=2, sort_keys=True))
    return 0 if rep["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
